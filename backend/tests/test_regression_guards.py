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
from tests.helpers import pending_fix, unwrap


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
        assert self._engine_kwargs("sqlite:///x.db")["connect_args"] == {"check_same_thread": False}

    @pending_fix("issue 3", "SQLite-only connect_args are passed to every database, which crashes PostgreSQL/MySQL drivers")
    def test_sqlite_only_options_are_not_sent_to_other_databases(self):
        assert "check_same_thread" not in self._engine_kwargs("postgresql://u:p@db/app").get("connect_args", {})

    @pending_fix("issue 3", "no connection-pool health checks are configured for server databases")
    def test_server_databases_get_connection_health_checks(self):
        assert self._engine_kwargs("postgresql://u:p@db/app").get("pool_pre_ping") is True


# ------------------------------------------------------------------ issue 5: reads must not write
class TestReadsAreSideEffectFree:
    @pending_fix("issue 5", "GET /api/projects assigns a missing session_id and commits inside the read loop")
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
    @pending_fix("issue 8", "login has no rate limit, so passwords can be guessed without restriction")
    def test_repeated_failed_logins_are_throttled(self, client, make_user):
        user = make_user()
        codes = [client.post("/api/auth/login", json={"email": user.email, "password": "wrong"}).status_code for _ in range(12)]
        assert 429 in codes

    @pending_fix("issue 8", "there is no request body size limit")
    def test_oversized_request_bodies_are_rejected(self, client):
        big = {"name": "x" * (3 * 1024 * 1024), "email": "a@b.com", "password": "p"}
        assert client.post("/api/auth/register", json=big).status_code == 413

    def test_a_normal_request_is_not_affected_by_limits(self, client, make_user, auth):
        assert client.get("/api/auth/me", headers=auth(make_user())).status_code == 200


# ------------------------------------------------------------------ issue 9: logging must never drop a record
class TestLogging:
    @pending_fix("issue 9", "the log format requires a traceId on every record, so any record without one raises inside the handler")
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
    @pending_fix("issue 10", "datetime.utcnow() is used throughout models, auth and services")
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
