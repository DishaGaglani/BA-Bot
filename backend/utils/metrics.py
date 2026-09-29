"""Prometheus metrics, exposed at GET /metrics (see app.py).

Latency is exported as histograms; compute quantiles in Prometheus, e.g.
  histogram_quantile(0.95, sum by (le, route) (rate(ba_http_request_duration_seconds_bucket[5m])))

Label values are deliberately bounded: HTTP routes use the route *template*
(/api/projects/{project_id}, never /api/projects/42) and unmatched paths collapse
into "unmatched", so scanners can't inflate the number of time series.

Token counts are estimates (characters / 4, the same heuristic prompt_builder uses); the
upstream LLM API does not report usage. This registry is per process, so a deployment
with several uvicorn workers needs prometheus_client's multiprocess mode.
"""
import contextlib
import os
import threading
import time
from typing import Iterator, Optional

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.gc_collector import GCCollector
from prometheus_client.platform_collector import PlatformCollector
from prometheus_client.process_collector import ProcessCollector

REGISTRY = CollectorRegistry()
GCCollector(registry=REGISTRY)
PlatformCollector(registry=REGISTRY)
ProcessCollector(registry=REGISTRY)

_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120)
_DB_BUCKETS = (0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 5)

HTTP_REQUESTS = Counter(
    "ba_http_requests_total", "HTTP requests by method, route template and status code.",
    ["method", "route", "status"], registry=REGISTRY,
)
HTTP_DURATION = Histogram(
    "ba_http_request_duration_seconds",
    "Time until the response starts (for streamed replies: until the first byte).",
    ["method", "route"], buckets=_LATENCY_BUCKETS, registry=REGISTRY,
)
HTTP_IN_PROGRESS = Gauge("ba_http_requests_in_progress", "Requests currently being handled.", registry=REGISTRY)

LLM_REQUESTS = Counter(
    "ba_llm_requests_total", "Calls to the LLM API by operation and outcome.",
    ["operation", "outcome"], registry=REGISTRY,
)
LLM_DURATION = Histogram(
    "ba_llm_request_duration_seconds",
    "LLM call latency. operation: completion (whole call), stream_connect (until headers), chat_stream (whole streamed reply).",
    ["operation"], buckets=_LATENCY_BUCKETS, registry=REGISTRY,
)
LLM_RETRIES = Counter("ba_llm_retries_total", "Retried LLM calls after a transient failure.", ["operation"], registry=REGISTRY)
LLM_TOKENS = Counter(
    "ba_llm_tokens_total", "Estimated LLM tokens (chars/4) by operation and direction.",
    ["operation", "direction"], registry=REGISTRY,
)

CHAT_STREAMS_ACTIVE = Gauge("ba_chat_streams_active", "Chat replies currently being generated.", registry=REGISTRY)
DB_DURATION = Histogram(
    "ba_db_query_duration_seconds", "SQL statement latency by statement type.",
    ["operation"], buckets=_DB_BUCKETS, registry=REGISTRY,
)
UNHANDLED_EXCEPTIONS = Counter(
    "ba_unhandled_exceptions_total", "Exceptions that escaped their handler.", ["source"], registry=REGISTRY,
)
TASK_DURATION = Histogram(
    "ba_task_duration_seconds", "Background task run time.", ["task"], buckets=_LATENCY_BUCKETS, registry=REGISTRY,
)
TASKS = Counter("ba_tasks_total", "Background task runs by outcome.", ["task", "outcome"], registry=REGISTRY)
APP_INFO = Gauge("ba_app_info", "Static build/runtime information.", ["version", "environment"], registry=REGISTRY)

# ---------------------------------------------------------------- active users gauge
ACTIVE_WINDOW_SECONDS = int(os.getenv("ACTIVE_USER_WINDOW_SECONDS", "300"))
_recent_users: dict = {}
_recent_lock = threading.Lock()


def mark_user_active(user_key: str) -> None:
    """Remember that this (authenticated) user just made a request. Only a count is exported."""
    now = time.monotonic()
    with _recent_lock:
        _recent_users[user_key] = now
        if len(_recent_users) > 10_000:  # nobody is scraping; don't let the dict grow without bound
            for key in [k for k, t in _recent_users.items() if t < now - ACTIVE_WINDOW_SECONDS]:
                del _recent_users[key]


class _RuntimeCollector:
    """Gauges that are computed at scrape time rather than maintained incrementally."""

    def __init__(self, engine=None):
        self.engine = engine

    def collect(self):
        cutoff = time.monotonic() - ACTIVE_WINDOW_SECONDS
        with _recent_lock:
            for key in [k for k, t in _recent_users.items() if t < cutoff]:
                del _recent_users[key]
            active = len(_recent_users)
        yield _gauge("ba_active_users", f"Distinct authenticated users seen in the last {ACTIVE_WINDOW_SECONDS}s.", active)
        pool = getattr(self.engine, "pool", None)
        for attr, name, doc in (
            ("checkedout", "ba_db_pool_connections_in_use", "Database connections currently checked out."),
            ("size", "ba_db_pool_size", "Configured database pool size."),
        ):
            with contextlib.suppress(Exception):
                yield _gauge(name, doc, getattr(pool, attr)())


def _gauge(name: str, doc: str, value: float) -> GaugeMetricFamily:
    family = GaugeMetricFamily(name, doc)
    family.add_metric([], value)
    return family


_runtime_collector: Optional[_RuntimeCollector] = None


def init_metrics(engine=None, *, version: str = "", environment: str = "") -> None:
    """Register scrape-time collectors and DB timing (idempotent)."""
    global _runtime_collector
    APP_INFO.labels(version=version, environment=environment).set(1)
    if _runtime_collector is None:
        _runtime_collector = _RuntimeCollector(engine)
        REGISTRY.register(_runtime_collector)
    elif engine is not None:
        _runtime_collector.engine = engine
    if engine is not None:
        instrument_engine(engine)


# --------------------------------------------------------------------------- database
_instrumented_engines: set = set()


def _statement_type(statement: str) -> str:
    head = statement.lstrip()[:12].split(None, 1)
    word = head[0].lower() if head else ""
    return word if word in {"select", "insert", "update", "delete", "pragma", "begin", "commit", "rollback"} else "other"


def instrument_engine(engine) -> None:
    from sqlalchemy import event

    if id(engine) in _instrumented_engines:
        return
    _instrumented_engines.add(id(engine))

    @event.listens_for(engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):
        context._ba_query_start = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):
        started = getattr(context, "_ba_query_start", None)
        if started is not None:
            DB_DURATION.labels(operation=_statement_type(statement)).observe(time.perf_counter() - started)


# ------------------------------------------------------------------------------- HTTP
def route_label(scope: dict) -> str:
    """Route template for the request, or "unmatched" (404s, scanners)."""
    route = scope.get("route")
    return getattr(route, "path", None) or "unmatched"


_KNOWN_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})


def record_http(method: str, route: str, status: int, duration: float) -> None:
    # HTTP allows any token as a method; without this a client could mint unlimited label values.
    method = method.upper() if method.upper() in _KNOWN_METHODS else "OTHER"
    HTTP_REQUESTS.labels(method=method, route=route, status=str(status)).inc()
    HTTP_DURATION.labels(method=method, route=route).observe(duration)


# --------------------------------------------------------------------------------- LLM
def estimate_tokens(text: str) -> int:
    return len(text) // 4


def record_llm_call(operation: str, duration: float, outcome: str) -> None:
    LLM_REQUESTS.labels(operation=operation, outcome=outcome).inc()
    LLM_DURATION.labels(operation=operation).observe(duration)


def record_llm_tokens(operation: str, *, input_tokens: int = 0, output_tokens: int = 0) -> None:
    if input_tokens:
        LLM_TOKENS.labels(operation=operation, direction="input").inc(input_tokens)
    if output_tokens:
        LLM_TOKENS.labels(operation=operation, direction="output").inc(output_tokens)


# ----------------------------------------------------------------------- background tasks
@contextlib.contextmanager
def track_task(name: str) -> Iterator[None]:
    """Time a background task and count its outcome; re-raises whatever the task raises."""
    started = time.perf_counter()
    try:
        yield
    except BaseException:
        TASKS.labels(task=name, outcome="error").inc()
        raise
    else:
        TASKS.labels(task=name, outcome="success").inc()
    finally:
        TASK_DURATION.labels(task=name).observe(time.perf_counter() - started)


def render() -> tuple:
    """(body, content_type) for the /metrics endpoint."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
