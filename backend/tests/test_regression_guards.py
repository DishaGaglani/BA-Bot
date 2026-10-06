"""One guard per previously-reported issue. Each asserts the *fixed* behavior, so it is
marked pending_fix until that fix is merged, and becomes a permanent regression test after."""
import json
import os
import subprocess
import sys
import warnings

import pytest
from sqlalchemy import event

from auth.jwt import create_access_token
from database import engine
from services.audit import log_action
from services.conversation_manager import save_message
from tests.conftest import BACKEND_DIR
from tests.helpers import unwrap


def _python(code, env_overrides=None, *args):
    env = dict(os.environ)
    env.update(env_overrides or {})
    return subprocess.run([sys.executable, "-c", code, str(BACKEND_DIR), *args], env=env, capture_output=True, text=True)


# ------------------------------------------------------------------ issue 3: database engine configuration
_ENGINE_PROBE = """
import sys, json
sys.path.insert(0, sys.argv[1])
import sqlalchemy
captured = {}
def fake_create_engine(url, **kwargs):
    captured.update(url=url, kwargs=kwargs)
    return object()
sqlalchemy.create_engine = fake_create_engine
import database
print(json.dumps(captured, default=str))
"""


class TestEngineConfiguration:
    def _engine_kwargs(self, url):
        out = _python(_ENGINE_PROBE, {"DATABASE_URL": url})
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout.strip().splitlines()[-1])["kwargs"]

    def test_sqlite_allows_use_across_request_threads(self):
        # timeout=15 is the SQLite busy_timeout (issue 6): how long a connection waits for
        # another writer's lock before raising "database is locked".
        assert self._engine_kwargs("sqlite:///x.db")["connect_args"] == {"check_same_thread": False, "timeout": 15}

    def test_sqlite_only_options_are_not_sent_to_other_databases(self):
        assert "check_same_thread" not in self._engine_kwargs("postgresql://u:p@db/app").get("connect_args", {})

    def test_server_databases_get_connection_health_checks(self):
        assert self._engine_kwargs("postgresql://u:p@db/app").get("pool_pre_ping") is True


# ------------------------------------------------------------------ issue 5: reads must not write
class TestReadsAreSideEffectFree:
    def test_listing_projects_issues_no_writes(self, client, db, make_user, make_project, auth):
        owner = make_user()
        project = make_project(owner)
        project.session_id = None  # a legacy row
        db.commit()

        statements = []
        listener = lambda conn, cursor, statement, *a: statements.append(statement)
        event.listen(engine, "before_cursor_execute", listener)
        try:
            r = client.get("/api/projects", headers=auth(owner))
        finally:
            event.remove(engine, "before_cursor_execute", listener)

        assert r.status_code == 200 and project.id in {p["id"] for p in unwrap(r)}
        writes = [s for s in statements if s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))]
        assert writes == []


# ------------------------------------------------------------------ issue 8: abuse protection
class TestAbuseProtection:
    def test_repeated_failed_logins_are_throttled(self, client, make_user):
        user = make_user()
        codes = [client.post("/api/auth/login", json={"email": user.email, "password": "wrong"}).status_code for _ in range(12)]
        assert 429 in codes

    def test_oversized_request_bodies_are_rejected(self, client):
        # MAX_REQUEST_BODY_BYTES defaults to 4MB (issue 8 review: 2x this app's largest
        # legitimate payload, for header/framing headroom) — must exceed that, not the
        # smaller ad-hoc size an earlier version of this limit used.
        big = {"name": "x" * (5 * 1024 * 1024), "email": "a@b.com", "password": "p"}
        assert client.post("/api/auth/register", json=big).status_code == 413

    def test_a_normal_request_is_not_affected_by_limits(self, client, make_user, auth):
        assert client.get("/api/auth/me", headers=auth(make_user())).status_code == 200


# ------------------------------------------------------------------ issue 9: logging must never drop a record
class TestLogging:
    def test_records_without_a_trace_id_are_still_logged(self):
        code = (
            "import sys, logging; sys.path.insert(0, sys.argv[1]);"
            "import utils.prod_ready;"
            "logging.getLogger('third.party').warning('THIRD-PARTY-LINE')"
        )
        out = _python(code)
        assert "Logging error" not in out.stderr and "THIRD-PARTY-LINE" in out.stderr

    def test_records_with_a_trace_id_keep_it(self):
        code = (
            "import sys; sys.path.insert(0, sys.argv[1]);"
            "from utils.prod_ready import logger;"
            "logger.info('hello', extra={'traceId': 'abc-123'})"
        )
        assert "traceId=abc-123 hello" in _python(code).stderr


# ------------------------------------------------------------------ issue 10: deprecated datetime.utcnow
class TestTimestamps:
    @pytest.mark.skipif(sys.version_info < (3, 12), reason="utcnow() is only deprecated from Python 3.12")
    def test_no_deprecated_utcnow_calls_on_common_paths(self, db, make_user, make_project):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            user = make_user()
            project = make_project(user)
            save_message(db, project.id, "user", "hi")
            log_action(db, user.id, "x")
            create_access_token({"sub": user.email})
        assert [str(w.message) for w in caught if "utcnow" in str(w.message)] == []

    def test_stored_timestamps_are_naive_utc(self, db, make_user):
        import datetime

        created = make_user().created_at
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        assert created.tzinfo is None and abs((now - created).total_seconds()) < 10


# ------------------------------------------------------------------ /api/predict must not block the shared threadpool
class TestPredictStreamDoesNotBlockTheSharedThreadpool:
    """predict() is a plain sync `def`, so its generator used to get driven via
    Starlette's iterate_in_threadpool — anyio's *shared default* thread limiter, the
    same one every other sync endpoint in the app relies on. app.py's
    _stream_with_dedicated_limiter bridges it through _predict_limiter instead.

    This is verified directly against the limiters rather than via real concurrent HTTP
    requests: this branch predates issue #33's SQLite WAL/busy_timeout fix, and SQLite's
    single-writer lock contention dominates at a concurrency level far below the shared
    limiter's own 40-token capacity (confirmed experimentally: a live-server test with as
    few as 20 concurrent /api/predict calls times out on DB contention alone, well before
    the shared threadpool itself would ever be the bottleneck) — so an HTTP-level test
    can't isolate this property without also porting that fix.
    """

    def test_fixed_path_consumes_none_of_the_shared_default_limiter(self):
        import time as time_mod

        import anyio
        import anyio.to_thread

        import app as backend_app

        def _slow_gen():
            for i in range(2):
                time_mod.sleep(0.2)
                yield f"chunk-{i}"

        async def _main():
            shared_limiter = anyio.to_thread.current_default_thread_limiter()
            peak_shared = 0
            peak_predict = 0

            async def _consume():
                nonlocal peak_shared, peak_predict
                async for _ in backend_app._stream_with_dedicated_limiter(_slow_gen()):
                    peak_shared = max(peak_shared, shared_limiter.borrowed_tokens)
                    peak_predict = max(peak_predict, backend_app._predict_limiter.borrowed_tokens)

            async with anyio.create_task_group() as tg:
                for _ in range(50):
                    tg.start_soon(_consume)

            return peak_shared, peak_predict

        peak_shared, peak_predict = anyio.run(_main)
        assert peak_shared == 0, f"expected zero shared-limiter usage, got {peak_shared} borrowed tokens"
        assert peak_predict > 0, "the dedicated limiter never got used; the test isn't exercising anything"

    def test_the_old_unfixed_path_would_have_consumed_the_shared_default_limiter(self):
        """Non-vacuousness check: confirms the comparison above is meaningful by showing
        what the *old* code path (Starlette's own iterate_in_threadpool, what a plain
        returned sync generator gets wrapped in) actually does to the same shared
        limiter under the same load."""
        import time as time_mod

        import anyio
        import anyio.to_thread
        from starlette.concurrency import iterate_in_threadpool

        def _slow_gen():
            for i in range(2):
                time_mod.sleep(0.2)
                yield f"chunk-{i}"

        async def _main():
            shared_limiter = anyio.to_thread.current_default_thread_limiter()
            peak_shared = 0

            async def _consume():
                nonlocal peak_shared
                async for _ in iterate_in_threadpool(_slow_gen()):
                    peak_shared = max(peak_shared, shared_limiter.borrowed_tokens)

            async with anyio.create_task_group() as tg:
                for _ in range(50):
                    tg.start_soon(_consume)

            return peak_shared

        peak_shared = anyio.run(_main)
        assert peak_shared > 0, "the old path should have drawn from the shared limiter"


# ------------------------------------------------------------------ deployment review: health probe separation
class TestHealthCheckSeparation:
    def test_liveness_touches_neither_the_database_nor_storage(self, client, monkeypatch):
        import app as backend_app

        def _boom():
            raise RuntimeError("a liveness check must never touch a dependency")

        monkeypatch.setattr(backend_app, "_check_storage_writable", _boom)

        statements = []
        listener = lambda conn, cursor, statement, *a: statements.append(statement)
        event.listen(engine, "before_cursor_execute", listener)
        try:
            r = client.get("/health/live")
        finally:
            event.remove(engine, "before_cursor_execute", listener)

        assert r.status_code == 200
        assert r.json()["status"] == "alive"
        assert statements == [], f"/health/live queried the database: {statements}"

    def test_readiness_succeeds_when_db_and_storage_are_both_fine(self, client):
        r = client.get("/health/ready")
        assert r.status_code == 200
        assert r.json()["status"] == "ready"

    def test_readiness_fails_when_the_database_is_down(self, client):
        import app as backend_app
        from dependencies.auth import get_db

        class _BrokenSession:
            def execute(self, *a, **k):
                raise RuntimeError("db is down")

        def _broken_get_db():
            yield _BrokenSession()

        backend_app.app.dependency_overrides[get_db] = _broken_get_db
        try:
            r = client.get("/health/ready")
        finally:
            backend_app.app.dependency_overrides.pop(get_db, None)

        assert r.status_code == 503
        assert "Database" in r.json()["message"]

    def test_readiness_fails_when_storage_is_not_writable(self, client, monkeypatch):
        import app as backend_app

        monkeypatch.setattr(backend_app, "_check_storage_writable", lambda: False)
        r = client.get("/health/ready")
        assert r.status_code == 503
        assert "Storage" in r.json()["message"]

    def test_combined_health_endpoint_still_works_for_backward_compatibility(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert set(r.json().keys()) >= {"status", "database", "aiService"}
