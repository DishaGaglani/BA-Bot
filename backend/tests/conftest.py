"""Shared, hermetic test fixtures.

The suite must never touch a developer's real data, so before the app is
imported this module points it at a throwaway database and upload directory,
and neutralises the startup migration. That last part matters:
utils.migrate.run_migration() opens backend/ba_bot.db directly with sqlite3 and
ignores DATABASE_URL, so letting it run would ALTER the real dev database.
"""
import atexit
import copy
import itertools
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

_TMP = Path(tempfile.mkdtemp(prefix="babot-tests-"))
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)
TEST_JWT_SECRET = "test-jwt-secret-" + "x" * 32
os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{_TMP / 'test.db'}",
        "UPLOAD_DIR": str(_TMP / "uploads"),
        "JWT_SECRET": TEST_JWT_SECRET,
        "ENV": "test",
        # Unroutable on purpose: any un-stubbed LLM call must fail, not leave the machine.
        "PREDICTION_URL": "http://127.0.0.1:9/never-reachable",
    }
)

import utils.migrate as _migrate  # noqa: E402

_migrate.run_migration = lambda: None  # see module docstring

import pytest  # noqa: E402
import requests  # noqa: E402
import uvicorn  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402

import app as backend_app  # noqa: E402
from auth.jwt import create_access_token, hash_password  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402
from models import (  # noqa: E402
    Project,
    ProjectMember,
    ProjectMemberRole,
    User,
    UserRole,
)

# bcrypt is deliberately slow, so hash once and share it across every seeded user.
DEFAULT_PASSWORD = "Passw0rd!"
_PASSWORD_HASH = hash_password(DEFAULT_PASSWORD)


# --------------------------------------------------------------------------- setup
@pytest.fixture(scope="session", autouse=True)
def _schema():
    # SQLite serialises writers. Without a busy timeout the concurrency tests would
    # measure "database is locked" errors rather than the application's own logic.
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    engine.dispose()
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(autouse=True)
def _clean_db(_schema):
    # Foreign keys aren't enforced by SQLite here, so table order doesn't matter (and
    # sorted_tables warns because users<->teams reference each other).
    with engine.begin() as conn:
        for table in Base.metadata.tables.values():
            conn.execute(table.delete())
    yield


@pytest.fixture(autouse=True)
def _restore_default_state():
    """get_structured_state() hands out a shallow copy of this module-level dict, so a
    test that mutates a nested list would otherwise leak into every later test."""
    import copy

    from services.project_state_manager import DEFAULT_STATE

    snapshot = copy.deepcopy(DEFAULT_STATE)
    yield
    DEFAULT_STATE.clear()
    DEFAULT_STATE.update(snapshot)


@pytest.fixture(autouse=True)
def _isolate_config_files(monkeypatch, tmp_path):
    """Admin endpoints persist settings/permissions to JSON files inside backend/."""
    import routes.admin as admin_routes
    import services.rbac_service as rbac

    monkeypatch.setattr(rbac, "PERMISSIONS_FILE", str(tmp_path / "role_permissions.json"))
    monkeypatch.setattr(admin_routes, "SETTINGS_FILE", str(tmp_path / "system_settings.json"))


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    def _blocked(self, method, url, *args, **kwargs):
        raise AssertionError(f"Test attempted a real outbound HTTP call: {method} {url}")

    monkeypatch.setattr(requests.sessions.Session, "request", _blocked)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    try:
        from utils.rate_limit import limiter
    except ImportError:  # rate limiting not present on this branch
        yield
        return
    limiter.reset()
    yield
    limiter.reset()


# --------------------------------------------------------------------------- clients
@pytest.fixture
def client():
    return TestClient(backend_app.app, raise_server_exceptions=False)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="module")
def live_url():
    """A real uvicorn server, for tests where threads and the event loop matter."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(backend_app.app, host="127.0.0.1", port=port, log_level="error", lifespan="off")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("live test server failed to start")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


# --------------------------------------------------------------------------- factories
@pytest.fixture
def make_user(db):
    counter = itertools.count(1)

    def _make(role=UserRole.BUSINESS_ANALYST, *, email=None, status="ACTIVE", team_id=None, name=None):
        n = next(counter)
        user = User(
            name=name or f"user{n}",
            email=email or f"user{n}-{uuid.uuid4().hex[:6]}@test.com",
            password_hash=_PASSWORD_HASH,
            role=role,
            status=status,
            team_id=team_id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


@pytest.fixture
def auth():
    def _headers(user):
        token = create_access_token({"sub": user.email, "role": user.role.value, "uid": user.id})
        return {"Authorization": f"Bearer {token}"}

    return _headers


@pytest.fixture
def make_project(db):
    def _make(owner, name="Project", *, status="DRAFT", locked=False, session_id=None, state=None, owner_is_member=True):
        project = Project(
            owner_id=owner.id,
            name=name,
            status=status,
            locked=locked,
            session_id=session_id or f"session-{uuid.uuid4()}",
            data="{}",
            structured_state=json.dumps(state) if state is not None else None,
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        if owner_is_member:
            db.add(ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectMemberRole.PROJECT_MANAGER))
            db.commit()
        return project

    return _make


@pytest.fixture
def add_member(db):
    def _add(project, user, role=ProjectMemberRole.VIEWER):
        member = ProjectMember(project_id=project.id, user_id=user.id, role=role)
        db.add(member)
        db.commit()
        return member

    return _add


# --------------------------------------------------------------------------- fake LLM
class FakeResponse:
    def __init__(self, status_code=200, lines=None, json_body=None, text=""):
        self.status_code = status_code
        self._lines = lines or []
        self._json = json_body
        self.text = text

    def iter_lines(self):
        return iter(self._lines)

    def json(self):
        if self._json is None:
            raise ValueError("no JSON body")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)


def sse(event, data=None, **extra):
    body = {"event": event}
    if data is not None:
        body["data"] = data
    body.update(extra)
    return f"data: {json.dumps(body)}".encode()


class FakeLLM:
    """Stands in for request_with_retry (the only path to the Forjinn API)."""

    def __init__(self):
        self.calls = []
        self._lock = threading.Lock()
        self.stream_tokens = ["Hello ", "from ", "the ", "AI. ", "What ", "is ", "your ", "budget?"]
        self.stream_delay = 0.0
        self.stream_script = []  # per-call overrides: an Exception, a FakeResponse, or a callable
        self.delta_text = "{}"
        self.summary_text = "A running summary."
        self.fdr_text = "{}"
        self.markdown_text = "# Requirements\n\n- First item\n- Second item\n"
        self.nonstream_error = None

    def stream_response(self, tokens=None, chat_id=None):
        chat_id = chat_id or f"session-{uuid.uuid4()}"
        lines = [sse("token", t) for t in (self.stream_tokens if tokens is None else tokens)]
        lines.append(sse("metadata", {"chatId": chat_id, "sessionId": chat_id}))
        return FakeResponse(200, lines=lines)

    def __call__(self, method, url, **kwargs):
        # Snapshot: the app reuses and mutates one payload dict across its retry attempts.
        payload = copy.deepcopy(kwargs.get("json") or {})
        streaming = bool(payload.get("streaming"))
        with self._lock:
            self.calls.append({"url": url, "streaming": streaming, "payload": payload, "prompt": payload.get("question", "")})
        if streaming:
            if self.stream_delay:
                time.sleep(self.stream_delay)
            if self.stream_script:
                behavior = self.stream_script.pop(0)
                if isinstance(behavior, Exception):
                    raise behavior
                return behavior(payload) if callable(behavior) else behavior
            return self.stream_response()
        if self.nonstream_error:
            raise self.nonstream_error
        prompt = payload.get("question", "").lower()
        if "precise data extraction agent" in prompt:
            text = self.delta_text
        elif "unified, and cohesive requirements summary" in prompt:
            text = self.summary_text
        elif "data extraction assistant" in prompt:
            text = self.fdr_text
        else:
            text = self.markdown_text
        return FakeResponse(200, json_body={"text": text})

    @property
    def streaming_calls(self):
        return [c for c in self.calls if c["streaming"]]


@pytest.fixture
def llm(monkeypatch):
    fake = FakeLLM()
    import services.fdr_summary as fdr_summary
    import services.project_state_manager as state_manager
    import utils.prod_ready as prod_ready

    # Each module binds request_with_retry by name at import; the lazy importers
    # (summary_manager, routes.projects) read it from utils.prod_ready at call time.
    for module in (backend_app, state_manager, fdr_summary, prod_ready):
        monkeypatch.setattr(module, "request_with_retry", fake)
    return fake
