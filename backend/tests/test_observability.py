"""Observability: trace correlation, log/Sentry scrubbing, OpenTelemetry spans, Prometheus metrics."""
import io
import json
import logging
import re
import threading
import time
import uuid

import pytest
import requests
from prometheus_client.parser import text_string_to_metric_families

import app as backend_app
from database import engine
from tests.conftest import FakeResponse
from utils import metrics, observability
from utils.metrics import REGISTRY

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
TRACEPARENT = f"00-{TRACE_ID}-00f067aa0ba902b7-01"
SECRET = "super-secret-jwt-signing-key-123456"


def sample(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0


@pytest.fixture
def boom_route():
    """A temporary route that raises, to exercise the unhandled-exception path."""

    def boom(password: str = ""):
        raise RuntimeError(f"db exploded while using password={SECRET} and token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.c2lnbmF0dXJl")

    backend_app.app.add_api_route("/__boom", boom, methods=["GET", "POST"])
    yield "/__boom"
    backend_app.app.router.routes[:] = [r for r in backend_app.app.router.routes if getattr(r, "path", "") != "/__boom"]


@pytest.fixture
def jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)


# ---------------------------------------------------------------------- scrubbing
class TestScrubbing:
    def test_jwts_and_bearer_tokens_are_removed(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyQHguY29tIn0.c2lnbmF0dXJlMTIz"
        text = observability.scrub_text(f"auth failed for Bearer {jwt} and again {jwt}")
        assert jwt not in text and "eyJ" not in text and observability.REDACTED in text

    @pytest.mark.parametrize(
        "raw",
        [
            "login password=hunter2 failed",
            'payload {"password": "hunter2", "email": "a@b.c"}',
            "password: 'hunter2'",
            "api_key=hunter2&x=1",
            "Authorization: Bearer hunter2token",
            "JWT_SECRET=hunter2",
        ],
    )
    def test_credential_assignments_are_removed(self, raw):
        assert "hunter2" not in observability.scrub_text(raw)

    def test_configured_secret_is_removed_even_without_a_label(self, jwt_secret):
        assert SECRET not in observability.scrub_text(f"the key was {SECRET} apparently")

    def test_ordinary_text_is_untouched(self):
        line = "prompt built: project=3 section=budget est_tokens=120"
        assert observability.scrub_text(line) == line

    def test_long_messages_are_truncated(self):
        out = observability.scrub_text("x" * 5000)
        assert len(out) < 2100 and out.endswith("chars]")

    def test_sensitive_keys_are_filtered_recursively(self):
        data = {
            "user": "u",
            "Authorization": "Bearer abc",
            "nested": {"password": "p", "question": "what is our budget?", "ok": 1},
            "items": [{"jwt_token": "t"}, "fine"],
        }
        out = observability.scrub_data(data)
        assert out["Authorization"] == observability.FILTERED
        assert out["nested"] == {"password": observability.FILTERED, "question": observability.FILTERED, "ok": 1}
        assert out["items"][0] == {"jwt_token": observability.FILTERED} and out["items"][1] == "fine"

    def test_text_formatter_scrubs_message_and_traceback(self, jwt_secret):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(observability.RedactingFormatter(observability.TEXT_FORMAT))
        handler.addFilter(observability.TraceContextFilter())
        log = logging.getLogger("test-scrub-text")
        log.propagate, log.handlers = False, [handler]
        try:
            raise ValueError(f"bad password=hunter2 secret {SECRET}")
        except ValueError:
            log.error("request failed Bearer abc.def.ghi", exc_info=True)
        out = stream.getvalue()
        assert "hunter2" not in out and SECRET not in out and "abc.def.ghi" not in out
        assert "ValueError" in out  # the diagnosis survives

    def test_json_formatter_emits_parseable_scrubbed_lines_with_trace_id(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(observability.JsonFormatter())
        handler.addFilter(observability.TraceContextFilter())
        log = logging.getLogger("test-scrub-json")
        log.propagate, log.handlers = False, [handler]
        with observability.trace_context("abc123"):
            log.warning("token=hunter2 rejected")
        record = json.loads(stream.getvalue())
        assert record["traceId"] == "abc123" and record["level"] == "WARNING"
        assert "hunter2" not in record["message"]


# ------------------------------------------------------------------ trace correlation
class TestTraceCorrelation:
    def test_incoming_traceparent_becomes_the_trace_id(self, client):
        r = client.get("/api/auth/me", headers={"traceparent": TRACEPARENT})
        assert r.status_code == 401
        assert r.headers["X-Trace-Id"] == TRACE_ID
        assert r.json()["traceId"] == TRACE_ID  # the error body carries the same id

    def test_success_responses_carry_the_header_too(self, client, make_user, auth):
        r = client.get("/api/auth/me", headers={**auth(make_user()), "traceparent": TRACEPARENT})
        assert r.status_code == 200 and r.headers["X-Trace-Id"] == TRACE_ID

    @pytest.mark.parametrize(
        "headers",
        [
            {},
            {"traceparent": "garbage"},
            {"traceparent": "00-" + "0" * 32 + "-00f067aa0ba902b7-01"},  # all-zero id is invalid
            {"x-request-id": "no spaces allowed here!"},
        ],
    )
    def test_missing_or_invalid_context_gets_a_fresh_id(self, client, headers):
        trace_id = client.get("/api/auth/me", headers=headers).headers["X-Trace-Id"]
        assert re.fullmatch(r"[0-9a-f]{32}", trace_id)
        assert trace_id != "0" * 32

    def test_each_request_gets_its_own_id(self, client):
        assert client.get("/health").headers["X-Trace-Id"] != client.get("/health").headers["X-Trace-Id"]

    def test_valid_request_id_header_is_adopted(self, client):
        assert client.get("/api/auth/me", headers={"x-request-id": "req-12345678"}).headers["X-Trace-Id"] == "req-12345678"

    def test_log_lines_from_deep_inside_a_request_carry_its_trace_id(self, client, auth, make_user, make_project, llm):
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler = Capture()
        logging.getLogger().addHandler(handler)
        observability.configure_logging()  # attaches the trace filter to every root handler, as at startup
        try:
            owner = make_user()
            project = make_project(owner)
            client.post(
                "/api/predict",
                headers={**auth(owner), "traceparent": TRACEPARENT},
                json={"question": "hi", "projectId": project.id},
            )
        finally:
            logging.getLogger().removeHandler(handler)
        prompt_lines = [r for r in records if "prompt built" in r.getMessage()]
        assert prompt_lines, "expected the prompt-size log line"
        assert all(getattr(r, "traceId", None) == TRACE_ID for r in prompt_lines)  # set with no explicit `extra`

    def test_cors_exposes_the_trace_header_to_browsers(self, client):
        r = client.get("/health", headers={"Origin": "http://localhost:5173"})
        exposed = r.headers.get("access-control-expose-headers", "")
        assert "X-Trace-Id" in exposed and "Content-Disposition" in exposed

    def test_unhandled_error_still_returns_the_trace_id(self, client, boom_route):
        r = client.get(boom_route, headers={"traceparent": TRACEPARENT})
        assert r.status_code == 500
        assert r.headers["X-Trace-Id"] == TRACE_ID and r.json()["traceId"] == TRACE_ID
        assert SECRET not in r.text  # internals are never sent to the client


# -------------------------------------------------------------------------- Sentry
@pytest.fixture
def sentry(monkeypatch):
    import sentry_sdk
    from sentry_sdk.transport import Transport

    events = []

    class Sink(Transport):
        def __init__(self, options=None):
            super().__init__(options)

        def capture_envelope(self, envelope):
            event = envelope.get_event()
            if event is not None:
                events.append(event)

    assert observability.setup_error_tracking("https://public@o0.ingest.sentry.io/1", transport=Sink())
    yield events
    sentry_sdk.flush(timeout=1)
    observability.shutdown_error_tracking()
    sentry_sdk.init()  # leave the SDK disabled for later tests


class TestErrorTracking:
    def test_disabled_without_a_dsn(self, monkeypatch):
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        assert observability.setup_error_tracking() is False
        observability.capture_exception(RuntimeError("no-op"))  # must not raise

    def test_unhandled_exception_is_reported_scrubbed_and_tagged(self, client, boom_route, sentry, jwt_secret):
        r = client.post(
            boom_route,
            headers={"traceparent": TRACEPARENT, "Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.c2ln"},
            json={"password": "hunter2", "question": "our confidential budget is 5M"},
        )
        assert r.status_code == 500
        assert sentry, "the failure never reached Sentry"
        blob = json.dumps(sentry, default=str)
        for leaked in ("hunter2", SECRET, "confidential budget", "eyJhbGci", "c2ln"):
            assert leaked not in blob, f"{leaked!r} leaked into the Sentry event"
        event = sentry[0]
        assert event["tags"]["trace_id"] == TRACE_ID
        assert any(v["type"] == "RuntimeError" for v in event["exception"]["values"])
        assert "user" not in event

    def test_client_errors_are_not_reported(self, client, sentry):
        client.get("/api/auth/me")  # 401
        client.get("/api/nope")  # 404
        assert sentry == []

    def test_explicit_capture_carries_context_tags(self, sentry):
        with observability.trace_context("t-123"):
            observability.capture_exception(ValueError("bad"), task="export", project_id=7)
        assert sentry[0]["tags"]["task"] == "export" and sentry[0]["tags"]["project_id"] == "7"
        assert sentry[0]["tags"]["trace_id"] == "t-123"

    def test_thread_crash_is_logged_counted_and_reported(self, sentry, caplog):
        original = threading.excepthook
        observability.install_thread_excepthook()
        before = sample("ba_unhandled_exceptions_total", source="thread")
        try:
            def die():
                raise RuntimeError("worker died")

            t = threading.Thread(target=die, name="job-worker-9")
            t.start()
            t.join()
        finally:
            threading.excepthook = original
        assert sample("ba_unhandled_exceptions_total", source="thread") == before + 1
        assert "job-worker-9" in caplog.text
        values = [v.get("value") for e in sentry for v in e.get("exception", {}).get("values", [])]
        assert "worker died" in values

    def test_failed_post_chat_update_is_reported(self, client, auth, make_user, make_project, llm, sentry, monkeypatch):
        import app as app_module

        def explode(*a, **k):
            raise RuntimeError("state merge failed")

        monkeypatch.setattr(app_module, "update_project_state", explode)
        owner = make_user()
        project = make_project(owner)
        r = client.post("/api/predict", headers=auth(owner), json={"question": "hi", "projectId": project.id})
        assert r.status_code == 200  # the user still gets their reply
        assert any(e.get("tags", {}).get("source") == "post_chat_update" for e in sentry)

    def test_scrub_hook_removes_locals_request_bodies_and_users(self):
        event = {
            "request": {"data": {"password": "p"}, "headers": {"Authorization": "Bearer x"}},
            "user": {"email": "a@b.c"},
            "exception": {"values": [{"value": "password=hunter2", "stacktrace": {"frames": [{"vars": {"token": "t", "n": 1}}]}}]},
        }
        out = observability.scrub_sentry_event(event)
        blob = json.dumps(out)
        assert "hunter2" not in blob and '"p"' not in blob and "a@b.c" not in blob
        assert out["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]["n"] == 1


# ------------------------------------------------------------------ OpenTelemetry
@pytest.fixture
def tracing():
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    assert observability.setup_tracing(backend_app.app, engine, tracer_provider=provider)
    yield exporter
    observability.shutdown_tracing(backend_app.app)


def _spans(exporter):
    return exporter.get_finished_spans()


class TestTracing:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        monkeypatch.delenv("OTEL_TRACES_EXPORTER", raising=False)
        assert observability.tracing_requested() is False
        assert observability.setup_tracing(backend_app.app, engine) is False

    def test_requested_by_environment(self, monkeypatch):
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
        assert observability.tracing_requested() is True

    def test_request_and_database_spans_share_the_callers_trace(self, client, tracing, make_user, auth):
        headers = {**auth(make_user()), "traceparent": TRACEPARENT}
        tracing.clear()  # discard spans from test setup, which ran outside any request
        client.get("/api/auth/me", headers=headers)
        spans = _spans(tracing)
        server = [s for s in spans if s.kind.name == "SERVER"]
        assert server and format(server[0].context.trace_id, "032x") == TRACE_ID
        db_spans = [s for s in spans if s.attributes.get("db.system")]
        assert db_spans, "no SQLAlchemy spans were recorded"
        assert {format(s.context.trace_id, "032x") for s in db_spans} == {TRACE_ID}

    def test_trace_id_in_response_matches_the_span(self, client, tracing):
        r = client.get("/api/auth/me")
        server = [s for s in _spans(tracing) if s.kind.name == "SERVER"][0]
        assert r.headers["X-Trace-Id"] == format(server.context.trace_id, "032x")

    def test_llm_call_span_is_a_child_of_the_active_span(self, tracing, monkeypatch):
        from utils.prod_ready import request_with_retry

        monkeypatch.setattr(requests, "request", lambda *a, **k: FakeResponse(200, json_body={"text": "hello world"}))
        with observability.span("parent"):
            request_with_retry("POST", "http://llm.local/predict", json={"question": "hi there", "streaming": False})
        by_name = {s.name: s for s in _spans(tracing)}
        assert by_name["llm.call"].parent.span_id == by_name["parent"].context.span_id
        assert by_name["llm.call"].attributes["llm.operation"] == "completion"

    def test_trace_context_is_propagated_to_the_llm_request(self, tracing):
        seen = {}

        class Capture(requests.adapters.HTTPAdapter):
            def send(self, request, **kwargs):
                seen.update(request.headers)
                resp = requests.Response()
                resp.status_code = 200
                resp._content = b"{}"
                return resp

        session = requests.Session()
        session.mount("http://", Capture())
        with observability.span("outer") as outer:
            session.send(session.prepare_request(requests.Request("POST", "http://llm.local/x")))
        assert TRACE_ID != "" and "traceparent" in seen
        assert seen["traceparent"].split("-")[1] == format(outer.get_span_context().trace_id, "032x")

    def test_health_and_metrics_are_not_traced(self, client, tracing):
        client.get("/metrics")
        assert not [s for s in _spans(tracing) if s.kind.name == "SERVER"]

    def test_observe_task_makes_a_span_and_records_the_error(self, tracing, sentry):
        with pytest.raises(RuntimeError):
            with observability.observe_task("export", project_id=3):
                raise RuntimeError("generation failed")
        span = [s for s in _spans(tracing) if s.name == "task.export"][0]
        assert span.status.status_code.name == "ERROR" and span.attributes["project_id"] == 3
        assert any(e.get("tags", {}).get("task") == "export" for e in sentry)


# --------------------------------------------------------------------------- metrics
class TestHttpMetrics:
    def test_requests_are_counted_by_route_template_and_status(self, client, make_user, auth, make_project):
        owner = make_user()
        p1, p2 = make_project(owner), make_project(owner)
        headers = auth(owner)
        labels = dict(method="GET", route="/api/projects/{project_id}")
        before = sample("ba_http_requests_total", status="200", **labels)
        client.get(f"/api/projects/{p1.id}", headers=headers)
        client.get(f"/api/projects/{p2.id}", headers=headers)
        assert sample("ba_http_requests_total", status="200", **labels) == before + 2

    def test_unknown_paths_do_not_create_new_series(self, client):
        before = sample("ba_http_requests_total", method="GET", route="unmatched", status="404")
        for i in range(5):
            client.get(f"/scanner/{uuid.uuid4()}")
        assert sample("ba_http_requests_total", method="GET", route="unmatched", status="404") == before + 5
        exposed = client.get("/metrics").text
        assert "/scanner/" not in exposed

    def test_status_codes_and_latency_histogram(self, client):
        before_401 = sample("ba_http_requests_total", method="GET", route="/api/auth/me", status="401")
        before_count = sample("ba_http_request_duration_seconds_count", method="GET", route="/api/auth/me")
        client.get("/api/auth/me")
        assert sample("ba_http_requests_total", method="GET", route="/api/auth/me", status="401") == before_401 + 1
        assert sample("ba_http_request_duration_seconds_count", method="GET", route="/api/auth/me") == before_count + 1

    def test_unhandled_exceptions_are_counted_as_500s(self, client, boom_route):
        before = sample("ba_http_requests_total", method="GET", route=boom_route, status="500")
        before_exc = sample("ba_unhandled_exceptions_total", source="http")
        client.get(boom_route)
        assert sample("ba_http_requests_total", method="GET", route=boom_route, status="500") == before + 1
        assert sample("ba_unhandled_exceptions_total", source="http") == before_exc + 1

    def test_in_progress_gauge_returns_to_zero(self, client):
        client.get("/health")
        assert sample("ba_http_requests_in_progress") == 0

    def test_metrics_endpoint_is_prometheus_text_and_not_self_counting(self, client):
        client.get("/metrics")
        r = client.get("/metrics")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
        families = {f.name for f in text_string_to_metric_families(r.text)}
        assert {"ba_http_requests", "ba_http_request_duration_seconds", "ba_llm_tokens", "ba_active_users"} <= families
        assert 'route="/metrics"' not in r.text

    def test_metrics_token_is_enforced_when_configured(self, client, monkeypatch):
        monkeypatch.setenv("METRICS_TOKEN", "scrape-token-123")
        assert client.get("/metrics").status_code == 401
        assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.get("/metrics", headers={"Authorization": "Bearer scrape-token-123"}).status_code == 200

    def test_active_users_gauge_counts_distinct_recent_users(self, client, make_user, auth, monkeypatch):
        with metrics._recent_lock:
            metrics._recent_users.clear()
        a, b = make_user(), make_user()
        for user in (a, b, b):
            client.get("/api/auth/me", headers=auth(user))
        client.get("/api/auth/me")  # anonymous requests don't count
        assert sample("ba_active_users") == 2
        monkeypatch.setattr(metrics, "ACTIVE_WINDOW_SECONDS", 0)
        time.sleep(0.01)
        assert sample("ba_active_users") == 0

    def test_database_latency_is_recorded_with_bounded_labels(self, client, make_user, auth):
        before = sample("ba_db_query_duration_seconds_count", operation="select")
        client.get("/api/auth/me", headers=auth(make_user()))
        assert sample("ba_db_query_duration_seconds_count", operation="select") > before
        ops = {s.labels["operation"] for f in REGISTRY.collect() if f.name == "ba_db_query_duration_seconds" for s in f.samples if "operation" in s.labels}
        assert ops <= {"select", "insert", "update", "delete", "pragma", "begin", "commit", "rollback", "other"}


class TestLlmMetrics:
    def test_successful_call_records_outcome_latency_and_tokens(self, monkeypatch):
        from utils.prod_ready import request_with_retry

        monkeypatch.setattr(requests, "request", lambda *a, **k: FakeResponse(200, json_body={"text": "y" * 400}, text="y" * 400))
        ok = sample("ba_llm_requests_total", operation="completion", outcome="success")
        tin = sample("ba_llm_tokens_total", operation="completion", direction="input")
        tout = sample("ba_llm_tokens_total", operation="completion", direction="output")
        request_with_retry("POST", "http://llm.local/x", json={"question": "q" * 80, "streaming": False})
        assert sample("ba_llm_requests_total", operation="completion", outcome="success") == ok + 1
        assert sample("ba_llm_tokens_total", operation="completion", direction="input") == tin + 20
        assert sample("ba_llm_tokens_total", operation="completion", direction="output") == tout + 100

    def test_failures_count_retries_then_an_error_outcome(self, monkeypatch):
        from utils import prod_ready

        def down(*a, **k):
            raise requests.ConnectionError("llm down")

        monkeypatch.setattr(requests, "request", down)
        monkeypatch.setattr(prod_ready.time, "sleep", lambda s: None)
        err = sample("ba_llm_requests_total", operation="completion", outcome="error")
        retries = sample("ba_llm_retries_total", operation="completion")
        with pytest.raises(requests.ConnectionError):
            prod_ready.request_with_retry("POST", "http://llm.local/x", json={"question": "q", "streaming": False})
        assert sample("ba_llm_requests_total", operation="completion", outcome="error") == err + 1
        assert sample("ba_llm_retries_total", operation="completion") == retries + 2

    def test_streaming_call_is_labelled_separately(self, monkeypatch):
        from utils.prod_ready import request_with_retry

        monkeypatch.setattr(requests, "request", lambda *a, **k: FakeResponse(200))
        before = sample("ba_llm_requests_total", operation="stream_connect", outcome="success")
        request_with_retry("POST", "http://llm.local/x", json={"question": "hi", "streaming": True}, stream=True)
        assert sample("ba_llm_requests_total", operation="stream_connect", outcome="success") == before + 1

    def test_chat_reply_records_stream_duration_and_output_tokens(self, client, auth, make_user, make_project, llm):
        owner = make_user()
        project = make_project(owner)
        done = sample("ba_llm_request_duration_seconds_count", operation="chat_stream")
        out = sample("ba_llm_tokens_total", operation="chat", direction="output")
        r = client.post("/api/predict", headers=auth(owner), json={"question": "hello", "projectId": project.id})
        assert r.status_code == 200
        assert sample("ba_llm_request_duration_seconds_count", operation="chat_stream") == done + 1
        assert sample("ba_llm_requests_total", operation="chat_stream", outcome="success") >= 1
        assert sample("ba_llm_tokens_total", operation="chat", direction="output") == out + len("".join(llm.stream_tokens).strip()) // 4
        assert sample("ba_chat_streams_active") == 0

    def test_failed_stream_is_counted_as_an_error(self, client, auth, make_user, make_project, llm):
        llm.stream_script = [requests.ConnectionError("down"), requests.ConnectionError("still down")]
        owner = make_user()
        project = make_project(owner)
        before = sample("ba_llm_requests_total", operation="chat_stream", outcome="error")
        try:
            client.post("/api/predict", headers=auth(owner), json={"question": "hello", "projectId": project.id})
        except Exception:
            pass
        assert sample("ba_llm_requests_total", operation="chat_stream", outcome="error") == before + 1
        assert sample("ba_chat_streams_active") == 0


class TestTaskMetrics:
    def test_track_task_counts_outcomes_and_duration(self):
        ok = sample("ba_tasks_total", task="t1", outcome="success")
        err = sample("ba_tasks_total", task="t1", outcome="error")
        with metrics.track_task("t1"):
            pass
        with pytest.raises(ValueError):
            with metrics.track_task("t1"):
                raise ValueError("x")
        assert sample("ba_tasks_total", task="t1", outcome="success") == ok + 1
        assert sample("ba_tasks_total", task="t1", outcome="error") == err + 1
        assert sample("ba_task_duration_seconds_count", task="t1") >= 2


# --------------------------------------------------------------------- hygiene guard
def test_no_stray_print_statements_in_request_paths():
    """Diagnostics must go through logging so they carry a trace id and are scrubbed."""
    from pathlib import Path

    root = Path(backend_app.__file__).parent
    offenders = []
    for path in [root / "app.py", *root.glob("services/*.py"), *root.glob("routes/*.py"), *root.glob("utils/*.py")]:
        if path.name == "migrate.py":  # one-shot startup migration, runs before logging exists
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if re.match(r"\s*print\(", line):
                offenders.append(f"{path.relative_to(root)}:{n}")
    assert offenders == []


# --------------------------------------------------------- regressions found in review
class TestReviewRegressions:
    def test_long_tracebacks_keep_the_exception_at_the_bottom(self, tmp_path, monkeypatch):
        """Truncating the whole formatted line would chop the exception type and message off."""
        module = tmp_path / "deepmod.py"
        module.write_text(
            "def f0():\n    raise ValueError('ROOT-CAUSE password=hunter2')\n"
            + "".join(f"def f{i}():\n    f{i - 1}()\n" for i in range(1, 40))
        )
        monkeypatch.syspath_prepend(str(tmp_path))
        import deepmod

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(observability.RedactingFormatter(observability.TEXT_FORMAT))
        handler.addFilter(observability.TraceContextFilter())
        log = logging.getLogger("test-long-tb")
        log.propagate, log.handlers = False, [handler]
        try:
            deepmod.f39()
        except ValueError:
            log.error("failed", exc_info=True)
        out = stream.getvalue()
        assert len(out) > observability.MAX_MESSAGE_CHARS  # this really is a long traceback
        assert "ValueError: ROOT-CAUSE" in out and "hunter2" not in out and "truncated" not in out

    def test_long_messages_are_still_capped_in_text_logs(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(observability.RedactingFormatter(observability.TEXT_FORMAT))
        handler.addFilter(observability.TraceContextFilter())
        log = logging.getLogger("test-long-msg")
        log.propagate, log.handlers = False, [handler]
        log.error("x" * 9000)
        assert len(stream.getvalue()) < 2200 and "truncated" in stream.getvalue()

    def test_formatting_does_not_mutate_the_record_for_other_handlers(self):
        record = logging.LogRecord("n", logging.INFO, "f", 1, "value=%s token=abc", ("v",), None)
        observability.RedactingFormatter("%(message)s").format(record)
        assert record.msg == "value=%s token=abc" and record.args == ("v",)

    def test_preflight_with_traceparent_and_authorization_is_allowed(self, client):
        r = client.options(
            "/api/auth/me",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "traceparent,authorization",
            },
        )
        assert r.status_code == 200
        allowed = r.headers["access-control-allow-headers"].lower()
        assert "traceparent" in allowed and "authorization" in allowed

    def test_logs_emitted_while_a_reply_streams_keep_the_request_trace_id(self, client, auth, make_user, make_project, llm):
        """The chat generator runs in a worker thread after the middleware returned."""
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler = Capture()
        logging.getLogger().addHandler(handler)
        observability.configure_logging()
        try:
            owner = make_user()
            project = make_project(owner)
            client.post(
                "/api/predict",
                headers={**auth(owner), "traceparent": TRACEPARENT},
                json={"question": "hi", "projectId": project.id},
            )
        finally:
            logging.getLogger().removeHandler(handler)
        after_stream = [r for r in records if "State updates completed" in r.getMessage()]
        assert after_stream and all(getattr(r, "traceId", None) == TRACE_ID for r in after_stream)


# ------------------------------------- misconfiguration must never take the API down
class TestSafeConfiguration:
    def test_malformed_sentry_dsn_is_ignored(self, monkeypatch, caplog):
        monkeypatch.setenv("SENTRY_DSN", "not a dsn")
        assert observability.setup_error_tracking() is False
        assert "Error tracking disabled" in caplog.text

    def test_invalid_sample_rate_falls_back_to_off(self, monkeypatch, sentry):
        # `sentry` already initialised with a valid DSN; re-run setup with a junk rate.
        monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "abc")
        assert observability.setup_error_tracking("https://public@o0.ingest.sentry.io/1") is True

    def test_out_of_range_sample_rate_is_clamped(self, monkeypatch, sentry):
        import sentry_sdk

        monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "7")
        observability.setup_error_tracking("https://public@o0.ingest.sentry.io/1")
        assert sentry_sdk.get_client().options["traces_sample_rate"] == 1.0

    def test_invalid_log_level_falls_back_to_info(self, monkeypatch):
        root = logging.getLogger()
        previous = root.level
        monkeypatch.setenv("LOG_LEVEL", "VERBOSE")
        try:
            observability.configure_logging()
            assert root.level == logging.INFO
        finally:
            root.setLevel(previous)

    def test_tracing_setup_failure_is_swallowed(self, monkeypatch, caplog):
        import opentelemetry.instrumentation.fastapi as fastapi_instr

        def broken(*a, **k):
            raise RuntimeError("collector config is broken")

        monkeypatch.setattr(fastapi_instr.FastAPIInstrumentor, "instrument_app", staticmethod(broken))
        monkeypatch.setenv("OTEL_TRACES_EXPORTER", "console")
        try:
            assert observability.setup_tracing(backend_app.app, engine) is False
        finally:
            observability.shutdown_tracing(backend_app.app)
        assert "Tracing disabled" in caplog.text

    def test_app_boots_with_every_observability_setting_broken(self, tmp_path):
        """End to end: a fresh interpreter importing the app with garbage in every knob."""
        import os
        import subprocess
        import sys

        env = {
            **os.environ,
            "SENTRY_DSN": "not a dsn",
            "SENTRY_TRACES_SAMPLE_RATE": "abc",
            "LOG_LEVEL": "VERBOSE",
            "LOG_FORMAT": "yaml",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "not a url",
            "DATABASE_URL": f"sqlite:///{tmp_path / 'boot.db'}",
            "UPLOAD_DIR": str(tmp_path / "up"),
        }
        code = (
            "import sys; sys.path.insert(0, %r);"
            "import utils.migrate as m; m.run_migration = lambda: None;"
            "import app; print('BOOT-OK')" % str(__import__("pathlib").Path(backend_app.__file__).parent)
        )
        out = subprocess.run([sys.executable, "-W", "ignore", "-c", code], env=env, capture_output=True, text=True, timeout=60)
        assert "BOOT-OK" in out.stdout, out.stderr[-1500:]


class TestMetricCardinality:
    def test_arbitrary_http_methods_share_one_label(self, client):
        for verb in ("FOO", "BAR", "BAZ"):
            try:
                client.request(verb, "/health")
            except Exception:
                pass
        methods = {s.labels["method"] for f in REGISTRY.collect() if f.name == "ba_http_requests" for s in f.samples if "method" in s.labels}
        assert methods <= {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "OTHER"}
        assert sample("ba_http_requests_total", method="OTHER", route="unmatched", status="405") + sample(
            "ba_http_requests_total", method="OTHER", route="/health", status="405"
        ) >= 3

    def test_active_user_table_cannot_grow_without_bound(self, monkeypatch):
        with metrics._recent_lock:
            metrics._recent_users.clear()
        monkeypatch.setattr(metrics, "ACTIVE_WINDOW_SECONDS", 0)
        for i in range(10_050):
            metrics.mark_user_active(f"user{i}")
        assert len(metrics._recent_users) < 10_050  # expired entries were pruned along the way
        with metrics._recent_lock:
            metrics._recent_users.clear()


class TestMultipleApps:
    def test_a_second_app_object_is_traced_too(self, tracing):
        """`python app.py` builds two app objects; the one uvicorn serves must be instrumented."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        second = FastAPI()

        @second.get("/ping")
        def ping():
            return {"ok": True}

        try:
            assert observability.setup_tracing(second, engine) is True
            TestClient(second).get("/ping", headers={"traceparent": TRACEPARENT})
            server = [s for s in _spans(tracing) if s.kind.name == "SERVER"]
            assert server and format(server[0].context.trace_id, "032x") == TRACE_ID
        finally:
            observability.shutdown_tracing(second)


class TestBreadcrumbs:
    def test_log_breadcrumbs_are_scrubbed_before_being_attached_to_events(self, sentry, jwt_secret):
        logging.getLogger("ba-bot").info("refreshing with token=hunter2 and secret %s", SECRET)
        observability.capture_exception(RuntimeError("boom"))
        blob = json.dumps(sentry, default=str)
        assert "hunter2" not in blob and SECRET not in blob
        assert "breadcrumbs" in sentry[0]  # the log line really was recorded, just scrubbed
