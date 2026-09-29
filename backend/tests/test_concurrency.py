"""Concurrency: real threads against a real uvicorn server (see the `live_url` fixture).

A SQLAlchemy Session is not thread-safe, so every ORM value (ids, emails, auth headers) is resolved
into plain data on the main thread BEFORE any worker thread starts; workers never touch the test session.
"""
import concurrent.futures as futures
import threading
import time

import httpx
import pytest

from models import Message, Project, ProjectMember, User
from tests.helpers import pending_fix, project_payload

pytestmark = pytest.mark.live


def _post(url, headers, body, timeout=30):
    with httpx.Client(timeout=timeout) as c:
        return c.post(url, headers=headers, json=body)


def _run_parallel(count, fn):
    barrier = threading.Barrier(count)

    def wrapped(i):
        barrier.wait(timeout=10)  # release every request at the same instant
        return fn(i)

    with futures.ThreadPoolExecutor(count) as pool:
        return list(pool.map(wrapped, range(count)))


def _sse_text(response):
    import json

    return "".join(
        json.loads(line[5:])["data"]
        for line in response.text.splitlines()
        if line.startswith("data:") and json.loads(line[5:]).get("event") == "token"
    )


class TestConcurrentChat:
    def test_parallel_conversations_do_not_bleed_into_each_other(self, live_url, db, llm, make_user, make_project, auth):
        count = 8
        owners = [make_user() for _ in range(count)]
        projects = [make_project(o, f"project-{i}") for i, o in enumerate(owners)]
        headers, project_ids = [auth(o) for o in owners], [p.id for p in projects]
        llm.stream_delay = 0.05

        responses = _run_parallel(
            count,
            lambda i: _post(f"{live_url}/api/predict", headers[i], {"question": f"question-{i}", "projectId": project_ids[i]}),
        )

        assert [r.status_code for r in responses] == [200] * count
        assert all(_sse_text(r) == "".join(llm.stream_tokens) for r in responses)
        db.expire_all()
        for i, project in enumerate(projects):
            rows = db.query(Message).filter_by(project_id=project.id).order_by(Message.id).all()
            assert [m.role for m in rows] == ["user", "ai"], f"project {i} has {[m.role for m in rows]}"
            assert rows[0].text == f"question-{i}"  # and never another conversation's question
        sessions = [db.get(Project, p.id).forjinn_session_id for p in projects]
        assert all(sessions) and len(set(sessions)) == count

    def test_many_messages_to_one_conversation_are_all_kept(self, live_url, db, llm, make_user, make_project, auth):
        owner = make_user()
        project = make_project(owner)
        headers, project_id = auth(owner), project.id
        count = 6
        responses = _run_parallel(
            count, lambda i: _post(f"{live_url}/api/predict", headers, {"question": f"msg-{i}", "projectId": project_id})
        )
        assert [r.status_code for r in responses] == [200] * count
        db.expire_all()
        users = {m.text for m in db.query(Message).filter_by(project_id=project.id, role="user")}
        assert users == {f"msg-{i}" for i in range(count)}  # nothing lost, nothing duplicated
        assert db.query(Message).filter_by(project_id=project.id, role="ai").count() == count

    def test_rejected_chats_leave_no_trace_under_concurrency(self, live_url, db, llm, make_user, make_project, auth):
        owner = make_user()
        project = make_project(owner, status="PUBLISHED", locked=True)
        headers, project_id = auth(owner), project.id
        responses = _run_parallel(
            5, lambda i: _post(f"{live_url}/api/predict", headers, {"question": "hi", "projectId": project_id})
        )
        assert [r.status_code for r in responses] == [403] * 5
        assert db.query(Message).filter_by(project_id=project.id).count() == 0
        assert llm.calls == []

    def test_slow_provider_calls_do_not_block_other_requests(self, live_url, llm, make_user, make_project, auth):
        """Guards against event-loop blocking / thread starvation: while several chats wait on a
        slow model, an unrelated cheap request must still be answered promptly."""
        slow_seconds, in_flight = 1.5, 8
        llm.stream_delay = slow_seconds
        owners = [make_user() for _ in range(in_flight)]
        projects = [make_project(o) for o in owners]
        headers, project_ids = [auth(o) for o in owners], [p.id for p in projects]
        probe_headers = auth(make_user())

        with futures.ThreadPoolExecutor(in_flight) as pool:
            pending = [
                pool.submit(_post, f"{live_url}/api/predict", headers[i], {"question": "slow", "projectId": project_ids[i]})
                for i in range(in_flight)
            ]
            time.sleep(0.4)  # let every slow request reach the provider
            started = time.time()
            with httpx.Client(timeout=10) as c:
                probe = c.get(f"{live_url}/api/auth/me", headers=probe_headers)
            elapsed = time.time() - started
            still_running = sum(not f.done() for f in pending)
            results = [f.result() for f in pending]

        assert probe.status_code == 200
        assert still_running == in_flight, "the probe must overlap with the slow requests to prove anything"
        assert elapsed < slow_seconds / 2, f"probe took {elapsed:.2f}s while chats were in flight"
        assert [r.status_code for r in results] == [200] * in_flight


class TestConcurrentWrites:
    def test_racing_registrations_create_exactly_one_account(self, live_url, db):
        body = {"name": "Racer", "email": "race@test.com", "password": "S3cret!pass"}
        responses = _run_parallel(5, lambda i: _post(f"{live_url}/api/auth/register", {}, body))
        assert sum(r.status_code == 200 for r in responses) == 1
        assert db.query(User).filter_by(email="race@test.com").count() == 1

    @pending_fix(
        "finding E",
        "the loser of a registration race hits the unique index, and the resulting IntegrityError is "
        "reported as a 500 instead of the 400 a sequential duplicate gets",
    )
    def test_racing_registrations_lose_with_a_client_error_not_a_server_error(self, live_url, db):
        body = {"name": "Racer", "email": "race2@test.com", "password": "S3cret!pass"}
        responses = _run_parallel(5, lambda i: _post(f"{live_url}/api/auth/register", {}, body))
        assert {r.status_code for r in responses} <= {200, 400}

    @pytest.mark.xfail(
        strict=False,
        reason="[issue 6] duplicate memberships can appear when invites race (no unique constraint); "
        "timing dependent, so this is non-strict",
    )
    def test_racing_invites_produce_one_membership_and_no_errors(self, live_url, db, make_user, make_project, auth):
        owner, guest = make_user(), make_user()
        project = make_project(owner)
        headers, url, guest_email, project_id, guest_id = auth(owner), f"{live_url}/api/projects/{project.id}/invite", guest.email, project.id, guest.id
        responses = _run_parallel(5, lambda i: _post(url, headers, {"email": guest_email, "role": "VIEWER"}))
        assert all(r.status_code == 200 for r in responses), [r.status_code for r in responses]
        db.expire_all()
        assert db.query(ProjectMember).filter_by(project_id=project_id, user_id=guest_id).count() == 1

    def test_racing_edits_leave_the_project_internally_consistent(self, live_url, db, make_user, make_project, auth):
        owner = make_user()
        project = make_project(owner)
        headers, project_id = auth(owner), project.id
        names = [f"Name-{i}" for i in range(6)]

        def edit(i):
            with httpx.Client(timeout=30) as c:
                return c.put(f"{live_url}/api/projects/{project_id}", headers=headers, json=project_payload(names[i]))

        responses = _run_parallel(6, edit)
        assert [r.status_code for r in responses] == [200] * 6
        db.expire_all()
        final = db.get(Project, project_id)
        import json

        assert final.name in names
        assert json.loads(final.structured_state)["project_name"] == final.name  # one winner, not a blend
