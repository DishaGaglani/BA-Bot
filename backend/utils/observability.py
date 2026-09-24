"""Tracing, error tracking and log hygiene.

Everything here is opt-in through environment variables and degrades to a no-op when
the relevant SDK or backend isn't configured, so the app runs the same with or without
a collector. (Prometheus metrics live in utils/metrics.py.)

Trace correlation
  Every request gets a trace id: the W3C `traceparent` sent by the caller (the web app
  sends one), else the active OpenTelemetry span, else a fresh id. It is returned as the
  `X-Trace-Id` response header, included in error bodies, attached to every log line for
  that request (via a contextvar) and to Sentry events, so a browser request, the backend
  logs and the exported trace can all be joined on one id.

Environment
  OTEL_EXPORTER_OTLP_ENDPOINT   enables tracing and exports spans over OTLP/HTTP
  OTEL_TRACES_EXPORTER=console  print spans to stdout (local debugging)
  OTEL_SERVICE_NAME             service name (default "ba-bot-backend")
  SENTRY_DSN                    enables error tracking
  SENTRY_TRACES_SAMPLE_RATE     Sentry performance sampling, 0-1 (default 0)
  SENTRY_RELEASE                release identifier reported to Sentry
  LOG_FORMAT=json               one JSON object per log line (default: text)
  LOG_LEVEL                     default INFO
"""
import contextlib
import contextvars
import json
import logging
import os
import re
import threading
import uuid
from typing import Any, Iterator, Optional

try:  # OpenTelemetry is optional at import time so the app still boots without it
    from opentelemetry import trace as otel_trace

    _HAS_OTEL = True
except ImportError:  # pragma: no cover
    otel_trace = None  # type: ignore[assignment]
    _HAS_OTEL = False

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "ba-bot-backend")
ENVIRONMENT = os.getenv("ENV", "development")

# ---------------------------------------------------------------- trace correlation
trace_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("trace_id", default=None)

_TRACEPARENT = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_.-]{8,64}$")


def _active_otel_trace_id() -> Optional[str]:
    if not _HAS_OTEL:
        return None
    ctx = otel_trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None


def current_trace_id() -> Optional[str]:
    """The trace id of whatever is running now (request, background task), if any."""
    return trace_id_var.get() or _active_otel_trace_id()


def resolve_trace_id(headers) -> str:
    """Pick the trace id for an incoming request (see module docstring)."""
    active = _active_otel_trace_id()
    if active:
        return active
    match = _TRACEPARENT.match((headers.get("traceparent") or "").strip().lower())
    if match and match.group(1) != "0" * 32:
        return match.group(1)
    request_id = (headers.get("x-request-id") or "").strip()
    if _REQUEST_ID.match(request_id):
        return request_id
    return uuid.uuid4().hex


@contextlib.contextmanager
def trace_context(trace_id: str) -> Iterator[None]:
    """Bind a trace id to the current thread/task so its log lines carry it."""
    token = trace_id_var.set(trace_id)
    try:
        yield
    finally:
        trace_id_var.reset(token)


# ------------------------------------------------------------------------ scrubbing
REDACTED = "[REDACTED]"
FILTERED = "[Filtered]"
MAX_MESSAGE_CHARS = 2000  # long messages are usually echoed prompts/LLM output, not diagnostics

# Field names whose values are never exported. Matched as substrings, case-insensitively.
_SENSITIVE_KEYS = (
    "password", "passwd", "secret", "token", "authorization", "api_key", "apikey", "api-key",
    "cookie", "jwt", "credential", "private_key",
    # conversation content: prompts, transcripts and model output
    "question", "prompt", "transcript", "chat_history", "history", "reply", "answer", "structured_state",
)

_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_KEY_VALUE = re.compile(
    r"""(?ix)
    (\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|token|authorization|jwt[_-]?secret|question|prompt)\b
     ["']?\s*[:=]\s*)
    (?:"[^"]*"|'[^']*'|[^\s,;&}\]]+)
    """
)


def _secret_values() -> list:
    """Literal secrets from the environment, redacted wherever they show up."""
    values = []
    for name in ("JWT_SECRET", "METRICS_TOKEN"):
        value = os.getenv(name)
        if value and len(value) >= 8:
            values.append(value)
    return values


def scrub_text(text: str, *, truncate: bool = True) -> str:
    """Strip credentials and secrets from free text, and cap its length."""
    if not isinstance(text, str) or not text:
        return text
    for value in _secret_values():
        text = text.replace(value, REDACTED)
    text = _JWT.sub(REDACTED, text)
    text = _BEARER.sub(f"Bearer {REDACTED}", text)
    text = _KEY_VALUE.sub(lambda m: m.group(1) + REDACTED, text)
    if truncate and len(text) > MAX_MESSAGE_CHARS:
        text = f"{text[:MAX_MESSAGE_CHARS]}...[truncated {len(text) - MAX_MESSAGE_CHARS} chars]"
    return text


def _is_sensitive_key(key: Any) -> bool:
    lowered = str(key).lower()
    return any(marker in lowered for marker in _SENSITIVE_KEYS)


def scrub_data(value: Any, _depth: int = 0) -> Any:
    """Recursively scrub a structure (Sentry event, log extra): sensitive keys are
    replaced wholesale, every string is passed through scrub_text."""
    if _depth > 20:
        return FILTERED
    if isinstance(value, dict):
        return {k: (FILTERED if _is_sensitive_key(k) else scrub_data(v, _depth + 1)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(scrub_data(v, _depth + 1) for v in value)
    if isinstance(value, str):
        return scrub_text(value)
    return value


# ---------------------------------------------------------------------------- logging
TEXT_FORMAT = "%(asctime)s [%(levelname)s] traceId=%(traceId)s %(message)s"


class TraceContextFilter(logging.Filter):
    """Guarantees every record has a `traceId`, taken from the current request/task
    unless the caller passed one explicitly via `extra`."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "traceId", None):
            record.traceId = current_trace_id() or "-"
        return True


class RedactingFormatter(logging.Formatter):
    """Text formatter that scrubs the finished line, message and traceback alike. Only the
    message is length-capped: a traceback is cut off at the *end* if truncated, and the end
    is where the exception type and message are."""

    def format(self, record: logging.LogRecord) -> str:
        original = (record.msg, record.args)
        record.msg, record.args = scrub_text(record.getMessage()), ()
        try:
            return scrub_text(super().format(record), truncate=False)
        finally:
            record.msg, record.args = original


class JsonFormatter(logging.Formatter):
    """One JSON object per line, for log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "traceId": getattr(record, "traceId", None) or current_trace_id() or "-",
            "message": scrub_text(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = scrub_text(self.formatException(record.exc_info), truncate=False)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Attach trace correlation and redaction to every root log handler (idempotent)."""
    root = logging.getLogger()
    requested = os.getenv("LOG_LEVEL", "INFO").upper()
    try:
        root.setLevel(requested)
    except (ValueError, TypeError):
        root.setLevel(logging.INFO)
        logging.getLogger("ba-bot").warning(f"Ignoring invalid LOG_LEVEL={requested!r}; using INFO")
    use_json = os.getenv("LOG_FORMAT", "text").lower() == "json"
    for handler in root.handlers:
        if not any(isinstance(f, TraceContextFilter) for f in handler.filters):
            handler.addFilter(TraceContextFilter())
        handler.setFormatter(JsonFormatter() if use_json else RedactingFormatter(TEXT_FORMAT))


# ---------------------------------------------------------------------------- tracing
_provider = None
_global_instrumented = False  # SQLAlchemy and `requests` are patched once per process
_instrumented_apps: list = []  # FastAPI instrumentation is per app object


def _tracer():
    if not _HAS_OTEL:
        return None
    return _provider.get_tracer(SERVICE_NAME) if _provider is not None else otel_trace.get_tracer(SERVICE_NAME)


@contextlib.contextmanager
def span(name: str, **attributes: Any) -> Iterator[Any]:
    """A child span of whatever is active; a no-op when tracing is not enabled."""
    tracer = _tracer()
    if tracer is None:
        yield None
        return
    with tracer.start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, value)
        yield current


def tracing_requested() -> bool:
    return bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or os.getenv("OTEL_TRACES_EXPORTER", "").lower() == "console")


def setup_tracing(app, engine, *, tracer_provider=None, force: bool = False) -> bool:
    """Instrument incoming HTTP requests, SQLAlchemy queries and outgoing `requests`
    calls (the LLM) so they all land in one trace. Returns True if tracing is active.

    Enabled by OTEL_EXPORTER_OTLP_ENDPOINT (or OTEL_TRACES_EXPORTER=console). Pass
    `tracer_provider` (tests) or `force=True` to bypass the environment check. Safe to call
    for several app objects (`python app.py` builds two: the one run as __main__ and the one
    uvicorn imports), and a misconfiguration is logged and ignored, never fatal.
    """
    global _provider, _global_instrumented
    if not _HAS_OTEL or not (force or tracer_provider or _provider or tracing_requested()):
        return False
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        if tracer_provider is None:
            tracer_provider = _provider
        if tracer_provider is None:
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

            tracer_provider = TracerProvider(
                resource=Resource.create({"service.name": SERVICE_NAME, "deployment.environment": ENVIRONMENT})
            )
            if os.getenv("OTEL_TRACES_EXPORTER", "").lower() == "console":
                exporter = ConsoleSpanExporter()
            else:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

                exporter = OTLPSpanExporter()  # endpoint/headers come from the standard OTEL_* variables
            tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
            otel_trace.set_tracer_provider(tracer_provider)
        _provider = tracer_provider

        # Only requests that are not health checks or the metrics scrape are traced.
        FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider, excluded_urls="/health$,/metrics$")
        if app not in _instrumented_apps:
            _instrumented_apps.append(app)
        app.middleware_stack = None  # rebuilt on the next request so the tracing middleware is included, even if the app already served traffic
        if not _global_instrumented:
            SQLAlchemyInstrumentor().instrument(engine=engine, tracer_provider=tracer_provider)
            RequestsInstrumentor().instrument(tracer_provider=tracer_provider)
            _global_instrumented = True
        return True
    except Exception as exc:  # noqa: BLE001 - observability must never stop the API from starting
        logging.getLogger("ba-bot").warning(f"Tracing disabled: could not initialise OpenTelemetry ({exc})")
        return False


def shutdown_tracing(app=None) -> None:
    """Undo setup_tracing (used by tests) and flush any pending spans."""
    global _provider, _global_instrumented
    if _provider is None and not _instrumented_apps:
        return
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    for instrumented in [app] if app is not None else list(_instrumented_apps):
        with contextlib.suppress(Exception):
            FastAPIInstrumentor.uninstrument_app(instrumented)
        instrumented.middleware_stack = None
        if instrumented in _instrumented_apps:
            _instrumented_apps.remove(instrumented)
    if _instrumented_apps:
        return  # other apps are still traced
    if _global_instrumented:
        SQLAlchemyInstrumentor().uninstrument()
        RequestsInstrumentor().uninstrument()
    provider, _provider, _global_instrumented = _provider, None, False
    with contextlib.suppress(Exception):
        provider.shutdown()  # type: ignore[union-attr]


# ------------------------------------------------------------------- error tracking
try:
    import sentry_sdk

    _HAS_SENTRY = True
except ImportError:  # pragma: no cover
    sentry_sdk = None  # type: ignore[assignment]
    _HAS_SENTRY = False

_sentry_active = False


def scrub_sentry_event(event: dict, hint: Optional[dict] = None) -> dict:
    """before_send hook: nothing sensitive leaves the process."""
    for section in ("request", "extra", "contexts", "breadcrumbs", "tags"):
        if section in event:
            event[section] = scrub_data(event[section])
    for exc in (event.get("exception") or {}).get("values", []):
        if isinstance(exc.get("value"), str):
            exc["value"] = scrub_text(exc["value"])
        for frame in (exc.get("stacktrace") or {}).get("frames", []):
            if "vars" in frame:  # local variables routinely hold tokens, passwords and prompts
                frame["vars"] = scrub_data(frame["vars"])
            # Source lines shown next to each frame can contain literals too.
            for key in ("context_line", "pre_context", "post_context"):
                if key in frame:
                    frame[key] = scrub_data(frame[key])
    if isinstance(event.get("message"), str):
        event["message"] = scrub_text(event["message"])
    if "logentry" in event:
        event["logentry"] = scrub_data(event["logentry"])
    event.pop("user", None)
    return event


def _scrub_breadcrumb(crumb: dict, hint: Optional[dict] = None) -> dict:
    return scrub_data(crumb)


def setup_error_tracking(dsn: Optional[str] = None, *, transport=None) -> bool:
    """Initialise Sentry if a DSN is configured. Returns True if it is active."""
    global _sentry_active
    dsn = dsn or os.getenv("SENTRY_DSN")
    if not (_HAS_SENTRY and dsn):
        return False
    try:
        from sentry_sdk.integrations.logging import LoggingIntegration

        try:
            sample_rate = min(max(float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0") or 0), 0.0), 1.0)
        except ValueError:
            logging.getLogger("ba-bot").warning("Ignoring invalid SENTRY_TRACES_SAMPLE_RATE; performance tracing is off")
            sample_rate = 0.0
        sentry_sdk.init(
            dsn=dsn,
            environment=ENVIRONMENT,
            release=os.getenv("SENTRY_RELEASE"),
            traces_sample_rate=sample_rate,
            send_default_pii=False,
            max_request_body_size="never",  # request bodies carry passwords and prompts
            include_local_variables=False,
            before_send=scrub_sentry_event,
            before_breadcrumb=_scrub_breadcrumb,
            # Errors are captured explicitly; turning every logger.error (e.g. each 4xx) into a
            # Sentry event would bury the real failures.
            integrations=[LoggingIntegration(level=logging.INFO, event_level=None)],
            transport=transport,
        )
    except Exception as exc:  # noqa: BLE001 - e.g. a malformed DSN must not stop the API from starting
        logging.getLogger("ba-bot").warning(f"Error tracking disabled: could not initialise Sentry ({exc})")
        return False
    _sentry_active = True
    return True


def shutdown_error_tracking() -> None:
    global _sentry_active
    if _HAS_SENTRY and _sentry_active:
        sentry_sdk.flush(timeout=2)
        client = sentry_sdk.get_client()
        client.close(timeout=2)
    _sentry_active = False


def capture_exception(exc: BaseException, **context: Any) -> None:
    """Report an exception to Sentry (no-op if it isn't configured). `context` becomes
    scrubbed tags/extras, e.g. capture_exception(exc, task="export", project_id=3)."""
    if not (_HAS_SENTRY and _sentry_active):
        return
    with sentry_sdk.new_scope() as scope:
        trace_id = current_trace_id()
        if trace_id:
            scope.set_tag("trace_id", trace_id)
        for key, value in context.items():
            scope.set_tag(key, str(value))
        sentry_sdk.capture_exception(exc)


def tag_request(trace_id: str) -> None:
    if _HAS_SENTRY and _sentry_active:
        sentry_sdk.get_current_scope().set_tag("trace_id", trace_id)


def install_thread_excepthook() -> None:
    """Log, count and report exceptions that kill a background thread; they would otherwise
    only reach stderr. (If Sentry's threading integration already reported it, the duplicate
    is dropped by Sentry's de-duplication.)"""
    previous = threading.excepthook

    def hook(args):
        if args.exc_value is not None and not issubclass(args.exc_type, SystemExit):
            logging.getLogger("ba-bot").error(
                f"Uncaught exception in thread {getattr(args.thread, 'name', '?')}: {args.exc_value}",
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
            from utils.metrics import UNHANDLED_EXCEPTIONS

            UNHANDLED_EXCEPTIONS.labels(source="thread").inc()
            capture_exception(args.exc_value, source="thread", thread=getattr(args.thread, "name", "?"))
        previous(args)

    threading.excepthook = hook


@contextlib.contextmanager
def observe_task(name: str, **attributes: Any) -> Iterator[None]:
    """Wrap a unit of background work: gives it a trace id (so its logs are joinable),
    a span, timing/outcome metrics, and reports any exception before re-raising it.
    """
    from utils.metrics import track_task

    with trace_context(current_trace_id() or uuid.uuid4().hex):
        with span(f"task.{name}", **attributes), track_task(name):  # the span records the exception itself
            try:
                yield
            except Exception as exc:
                capture_exception(exc, task=name, **attributes)
                raise
