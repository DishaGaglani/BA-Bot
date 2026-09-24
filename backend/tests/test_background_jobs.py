"""Background job queue: status tracking, retries, idempotency, crash recovery, and the
endpoints/flows built on it (export jobs, deferred summarization, disconnect-safe chat).

Workers are not started in tests (startup events don't run under TestClient), so jobs are
executed deterministically with job_queue.run_one().
"""
import concurrent.futures as futures
import datetime
import json
import threading
import time

import httpx
import pytest
import requests

from models import AuditLog, Job, Message, Project, ProjectMemberRole
from services import job_handlers, job_queue
from services.job_queue import PermanentJobError
from tests.conftest import FakeResponse, sse
from tests.helpers import seed_messages, unwrap


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    monkeypatch.setenv("JOB_BACKOFF_BASE_SECONDS", "0")
    monkeypatch.setenv("JOB_MAX_ATTEMPTS", "3")


@pytest.fixture
def handlers():
    """Register throwaway handlers and restore the real ones afterwards."""
    saved = dict(job_queue._HANDLERS)
    yield job_queue._HANDLERS
    job_queue._HANDLERS.clear()
    job_queue._HANDLERS.update(saved)


def _job(db, job_id):
    db.expire_all()
    return db.get(Job, job_id)


# ------------------------------------------------------------------------ queue core
class TestQueueCore:
    def test_job_moves_queued_to_completed_and_stores_result(self, db, handlers):
        handlers["demo"] = lambda db_, job: {"answer": 42}
        job, created = job_queue.enqueue(db, "demo")
        assert created and job.status == "queued" and job.attempts == 0

        assert job_queue.run_one() is True

        done = _job(db, job.id)
        assert done.status == "completed" and done.attempts == 1
        assert json.loads(done.result) == {"answer": 42} and done.finished_at is not None

    def test_run_one_returns_false_when_idle(self, db):
        assert job_queue.run_one() is False

    def test_same_idempotency_key_returns_the_existing_job(self, db, handlers):
        first, created1 = job_queue.enqueue(db, "demo", idempotency_key="k1")
        second, created2 = job_queue.enqueue(db, "demo", idempotency_key="k1")
        other, created3 = job_queue.enqueue(db, "demo", idempotency_key="k2")
        assert (created1, created2, created3) == (True, False, True)
        assert second.id == first.id and other.id != first.id
        assert db.query(Job).count() == 2

    def test_failed_job_is_reset_when_the_same_key_is_enqueued_again(self, db, handlers):
        def boom(db_, job):
            raise PermanentJobError("nope")

        handlers["demo"] = boom
        first, _ = job_queue.enqueue(db, "demo", idempotency_key="k")
        job_queue.run_one()
        assert _job(db, first.id).status == "failed"

        again, created = job_queue.enqueue(db, "demo", idempotency_key="k")
        assert not created and again.id == first.id
        assert again.status == "queued" and again.attempts == 0 and again.error is None

    def test_failure_is_retried_with_exponential_backoff_then_fails(self, db, handlers, monkeypatch):
        monkeypatch.setenv("JOB_BACKOFF_BASE_SECONDS", "10")
        calls = []

        def flaky(db_, job):
            calls.append(job.attempts)
            raise RuntimeError("upstream down")

        handlers["demo"] = flaky
        job, _ = job_queue.enqueue(db, "demo")

        job_queue.run_one()
        after_first = _job(db, job.id)
        assert after_first.status == "queued" and after_first.attempts == 1
        assert "upstream down" in after_first.error
        delay = (after_first.next_run_at - datetime.datetime.utcnow()).total_seconds()
        assert 8 < delay <= 10  # base * 2**0
        assert job_queue.run_one() is False  # not due yet, so nothing runs

        for expected_delay in (20,):  # attempt 2 backs off twice as long
            db.query(Job).filter_by(id=job.id).update({"next_run_at": datetime.datetime.utcnow()})
            db.commit()
            job_queue.run_one()
            j = _job(db, job.id)
            assert j.status == "queued" and j.attempts == 2
            assert expected_delay - 2 < (j.next_run_at - datetime.datetime.utcnow()).total_seconds() <= expected_delay

        db.query(Job).filter_by(id=job.id).update({"next_run_at": datetime.datetime.utcnow()})
        db.commit()
        job_queue.run_one()
        final = _job(db, job.id)
        assert final.status == "failed" and final.attempts == 3 and "upstream down" in final.error
        assert calls == [1, 2, 3]
        assert job_queue.run_one() is False  # a failed job is never picked up again

    def test_backoff_is_capped(self, monkeypatch):
        monkeypatch.setenv("JOB_BACKOFF_BASE_SECONDS", "100")
        monkeypatch.setenv("JOB_BACKOFF_MAX_SECONDS", "250")
        assert [job_queue._backoff_seconds(n) for n in (1, 2, 3, 4)] == [100, 200, 250, 250]

    def test_permanent_error_skips_retries(self, db, handlers):
        def boom(db_, job):
            raise PermanentJobError("project deleted")

        handlers["demo"] = boom
        job, _ = job_queue.enqueue(db, "demo")
        job_queue.run_one()
        failed = _job(db, job.id)
        assert failed.status == "failed" and failed.attempts == 1 and "project deleted" in failed.error

    def test_unknown_job_type_fails_instead_of_looping(self, db):
        job, _ = job_queue.enqueue(db, "no-such-type")
        job_queue.run_one()
        assert _job(db, job.id).status == "failed"

    def test_job_with_a_future_run_time_is_not_claimed(self, db, handlers):
        handlers["demo"] = lambda db_, job: {}
        job, _ = job_queue.enqueue(db, "demo")
        db.query(Job).filter_by(id=job.id).update({"next_run_at": datetime.datetime.utcnow() + datetime.timedelta(hours=1)})
        db.commit()
        assert job_queue.run_one() is False

    def test_expired_lease_requeues_a_job_whose_worker_died(self, db, handlers):
        handlers["demo"] = lambda db_, job: {"ok": True}
        job, _ = job_queue.enqueue(db, "demo")
        past = datetime.datetime.utcnow() - datetime.timedelta(seconds=5)
        db.query(Job).filter_by(id=job.id).update({"status": "processing", "attempts": 1, "locked_until": past})
        db.commit()

        assert job_queue.run_one() is True  # recovered, then run

        done = _job(db, job.id)
        assert done.status == "completed" and done.attempts == 2

    def test_live_lease_is_left_alone(self, db, handlers):
        handlers["demo"] = lambda db_, job: {}
        job, _ = job_queue.enqueue(db, "demo")
        future = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
        db.query(Job).filter_by(id=job.id).update({"status": "processing", "attempts": 1, "locked_until": future})
        db.commit()
        assert job_queue.run_one() is False
        assert _job(db, job.id).status == "processing"

    def test_expired_lease_with_no_attempts_left_fails_the_job(self, db, handlers):
        handlers["demo"] = lambda db_, job: {}
        job, _ = job_queue.enqueue(db, "demo")
        past = datetime.datetime.utcnow() - datetime.timedelta(seconds=5)
        db.query(Job).filter_by(id=job.id).update({"status": "processing", "attempts": 3, "locked_until": past})
        db.commit()
        assert job_queue.run_one() is False
        assert _job(db, job.id).status == "failed"

    def test_concurrent_workers_never_run_the_same_job_twice(self, db, handlers):
        ran, lock = [], threading.Lock()

        def record(db_, job):
            with lock:
                ran.append(job.id)
            time.sleep(0.01)
            return {}

        handlers["demo"] = record
        ids = [job_queue.enqueue(db, "demo")[0].id for _ in range(12)]

        def drain(_):
            while job_queue.run_one():
                pass

        with futures.ThreadPoolExecutor(4) as pool:
            list(pool.map(drain, range(4)))

        assert sorted(ran) == sorted(ids)  # each job ran exactly once
        db.expire_all()
        assert {j.status for j in db.query(Job)} == {"completed"}

    def test_purge_removes_old_finished_jobs_and_their_files(self, db, handlers, tmp_path):
        f = tmp_path / "out.pdf"
        f.write_bytes(b"x")
        old = datetime.datetime.utcnow() - datetime.timedelta(days=30)
        keep, _ = job_queue.enqueue(db, "demo")
        gone, _ = job_queue.enqueue(db, "demo")
        db.query(Job).filter_by(id=gone.id).update(
            {"status": "completed", "finished_at": old, "result": json.dumps({"file_path": str(f)})}
        )
        db.commit()
        assert job_queue.purge_finished(db) == 1
        assert not f.exists() and db.get(Job, gone.id) is None and db.get(Job, keep.id) is not None


# --------------------------------------------------------------------- export jobs
@pytest.fixture
def owned(client, auth, make_user, make_project, llm):
    owner = make_user()
    project = make_project(owner, "Retail Portal", state={"project_name": "Retail Portal"})

    class Ctx:
        pass

    c = Ctx()
    c.owner, c.project, c.llm, c.headers = owner, project, llm, auth(owner)
    c.post = lambda fmt="pdf", headers=None: client.post(
        f"/api/projects/{project.id}/export-jobs?format={fmt}", headers=headers or c.headers
    )
    c.get = lambda job_id, headers=None: client.get(f"/api/jobs/{job_id}", headers=headers or c.headers)
    c.download = lambda job_id, headers=None: client.get(f"/api/jobs/{job_id}/download", headers=headers or c.headers)
    return c


class TestExportJobs:
    def test_request_returns_immediately_without_calling_the_llm(self, owned):
        r = owned.post("pdf")
        assert r.status_code == 202
        body = unwrap(r)
        assert body["status"] == "queued" and body["job_id"]
        assert owned.llm.calls == []  # generation has not run inside the request

    @pytest.mark.parametrize("fmt,magic", [("pdf", b"%PDF"), ("docx", b"PK"), ("word", b"PK")])
    def test_job_produces_a_downloadable_file(self, owned, db, fmt, magic):
        job_id = unwrap(owned.post(fmt))["job_id"]
        assert unwrap(owned.get(job_id))["status"] == "queued"

        job_queue.run_one()

        status = unwrap(owned.get(job_id))
        assert status["status"] == "completed" and status["download_url"] == f"/api/jobs/{job_id}/download"
        download = owned.download(job_id)
        assert download.status_code == 200 and download.content.startswith(magic)
        assert "attachment" in download.headers["content-disposition"]
        assert db.query(AuditLog).filter_by(action="document generation", project_id=owned.project.id).count() == 1

    def test_repeat_requests_share_one_job_and_one_llm_call(self, owned):
        ids = {unwrap(owned.post("pdf"))["job_id"] for _ in range(3)}
        assert len(ids) == 1
        job_queue.run_one()
        assert job_queue.run_one() is False
        assert len(owned.llm.calls) == 1
        assert unwrap(owned.post("pdf"))["job_id"] in ids  # still the finished job; no new generation
        assert job_queue.run_one() is False and len(owned.llm.calls) == 1

    def test_changed_project_gets_a_fresh_export(self, owned, db):
        first = unwrap(owned.post("pdf"))["job_id"]
        db.query(Project).filter_by(id=owned.project.id).update({"summary": "new information"})
        db.commit()
        assert unwrap(owned.post("pdf"))["job_id"] != first

    def test_formats_are_separate_jobs(self, owned):
        assert unwrap(owned.post("pdf"))["job_id"] != unwrap(owned.post("docx"))["job_id"]

    def test_retry_after_the_file_was_written_does_not_regenerate_or_audit_again(self, owned, db):
        job_id = unwrap(owned.post("pdf"))["job_id"]
        job_queue.run_one()
        calls = len(owned.llm.calls)
        # Simulate: the worker died after writing the file but before recording completion.
        db.query(Job).filter_by(id=job_id).update({"status": "queued", "result": None, "attempts": 0})
        db.commit()
        job_queue.run_one()
        assert unwrap(owned.get(job_id))["status"] == "completed"
        assert len(owned.llm.calls) == calls
        assert db.query(AuditLog).filter_by(action="document generation").count() == 1

    def test_llm_outage_is_retried_then_falls_back_on_the_final_attempt(self, owned, db):
        owned.llm.nonstream_error = requests.ConnectionError("llm down")
        job_id = unwrap(owned.post("pdf"))["job_id"]

        job_queue.run_one()
        job = _job(db, job_id)
        assert job.status == "queued" and job.attempts == 1  # scheduled for retry, not delivered
        assert owned.download(job_id).status_code == 409

        job_queue.run_one()
        assert _job(db, job_id).status == "queued"
        job_queue.run_one()  # last attempt uses the placeholder document, as the old endpoint did

        assert unwrap(owned.get(job_id))["status"] == "completed"
        assert owned.download(job_id).content.startswith(b"%PDF")

    def test_recovers_when_the_llm_comes_back_between_attempts(self, owned, db):
        owned.llm.nonstream_error = requests.ConnectionError("blip")
        job_id = unwrap(owned.post("pdf"))["job_id"]
        job_queue.run_one()
        owned.llm.nonstream_error = None
        owned.llm.markdown_text = "# Real document\n\n- generated by the model\n"
        job_queue.run_one()
        assert _job(db, job_id).status == "completed" and _job(db, job_id).attempts == 2

    def test_export_of_a_deleted_project_fails_permanently(self, owned, db):
        job_id = unwrap(owned.post("pdf"))["job_id"]
        db.query(Project).filter_by(id=owned.project.id).delete()
        db.commit()
        job_queue.run_one()
        job = _job(db, job_id)
        assert job.status == "failed" and job.attempts == 1

    def test_invalid_format_is_rejected(self, owned):
        assert owned.post("xls").status_code == 400

    def test_legacy_synchronous_endpoint_still_works(self, owned, client):
        r = client.get(f"/api/projects/{owned.project.id}/export?format=pdf", headers=owned.headers)
        assert r.status_code == 200 and r.content.startswith(b"%PDF")
        assert client.get(f"/api/projects/{owned.project.id}/export?format=xls", headers=owned.headers).status_code == 400


class TestJobAccessControl:
    def test_unauthenticated_requests_are_rejected(self, owned, client):
        job_id = unwrap(owned.post("pdf"))["job_id"]
        assert client.get(f"/api/jobs/{job_id}").status_code == 401
        assert client.get(f"/api/jobs/{job_id}/download").status_code == 401
        assert client.post(f"/api/projects/{owned.project.id}/export-jobs?format=pdf").status_code == 401

    def test_outsider_cannot_create_read_or_download(self, owned, make_user, auth):
        job_id = unwrap(owned.post("pdf"))["job_id"]
        job_queue.run_one()
        outsider = auth(make_user())
        assert owned.post("pdf", headers=outsider).status_code == 403
        assert owned.get(job_id, headers=outsider).status_code == 403
        assert owned.download(job_id, headers=outsider).status_code == 403

    def test_project_viewer_can_export_and_follow_the_job(self, owned, make_user, add_member, auth):
        viewer = make_user()
        add_member(owned.project, viewer, ProjectMemberRole.VIEWER)
        headers = auth(viewer)
        job_id = unwrap(owned.post("pdf", headers=headers))["job_id"]
        job_queue.run_one()
        assert unwrap(owned.get(job_id, headers=headers))["status"] == "completed"
        assert owned.download(job_id, headers=headers).status_code == 200

    def test_admin_can_read_any_job(self, owned, make_user, auth):
        from models import UserRole

        job_id = unwrap(owned.post("pdf"))["job_id"]
        assert owned.get(job_id, headers=auth(make_user(UserRole.ADMIN))).status_code == 200

    def test_unknown_job_is_404(self, owned):
        assert owned.get("does-not-exist").status_code == 404

    def test_download_before_completion_is_a_conflict(self, owned):
        job_id = unwrap(owned.post("pdf"))["job_id"]
        assert owned.download(job_id).status_code == 409

    def test_download_of_a_purged_file_is_gone(self, owned):
        import os

        job_id = unwrap(owned.post("pdf"))["job_id"]
        job_queue.run_one()
        os.remove(json.loads(job_queue.SessionLocal().get(Job, job_id).result)["file_path"])
        assert owned.download(job_id).status_code == 410

    def test_job_status_does_not_leak_internal_paths(self, owned):
        job_id = unwrap(owned.post("pdf"))["job_id"]
        job_queue.run_one()
        assert "file_path" not in json.dumps(owned.get(job_id).json())


# ------------------------------------------------------------ deferred summarization
class TestSummarizationJobs:
    @pytest.fixture
    def chat(self, client, auth, make_user, make_project, llm):
        owner = make_user()
        project = make_project(owner)
        return type("C", (), {
            "project": project, "llm": llm,
            "send": staticmethod(lambda q="Tell me more": client.post(
                "/api/predict", headers=auth(owner), json={"question": q, "projectId": project.id})),
        })

    def test_chat_request_does_not_summarize_inline(self, chat, db):
        seed_messages(db, chat.project, 10)
        chat.llm.summary_text = "compacted"
        assert chat.send().status_code == 200
        prompts = [c["prompt"].lower() for c in chat.llm.calls]
        assert not any("unified, and cohesive requirements summary" in p for p in prompts)
        assert db.query(Job).filter_by(type="summarize", status="queued").count() == 1

    def test_queued_job_summarizes_and_archives(self, chat, db):
        seed_messages(db, chat.project, 10)
        chat.llm.summary_text = "compacted"
        chat.send()
        job_queue.run_one()
        db.expire_all()
        assert db.get(Project, chat.project.id).summary == "compacted"
        assert db.query(Message).filter_by(project_id=chat.project.id, is_archived=True).count() > 0
        assert db.query(Job).filter_by(type="summarize").one().status == "completed"

    def test_below_threshold_enqueues_nothing(self, chat, db):
        seed_messages(db, chat.project, 4)
        chat.send()
        assert db.query(Job).count() == 0

    def test_many_messages_while_queued_produce_one_job(self, chat, db):
        seed_messages(db, chat.project, 10)
        for _ in range(3):
            chat.send()
        assert db.query(Job).filter_by(type="summarize").count() == 1

    def test_running_it_twice_summarizes_once(self, chat, db):
        seed_messages(db, chat.project, 12)
        job, _ = job_queue.enqueue(db, "summarize", project_id=chat.project.id, idempotency_key="s1")
        job_queue.run_one()
        summaries = [c for c in chat.llm.calls if "cohesive requirements summary" in c["prompt"].lower()]
        assert len(summaries) == 1
        # A duplicate delivery of the same work finds nothing left to summarize.
        again, _ = job_queue.enqueue(db, "summarize", project_id=chat.project.id, idempotency_key="s2")
        job_queue.run_one()
        summaries = [c for c in chat.llm.calls if "cohesive requirements summary" in c["prompt"].lower()]
        assert len(summaries) == 1 and _job(db, again.id).status == "completed"

    def test_llm_failure_is_retried_and_leaves_messages_unarchived(self, chat, db):
        seed_messages(db, chat.project, 12)
        chat.llm.nonstream_error = requests.ConnectionError("down")
        job, _ = job_queue.enqueue(db, "summarize", project_id=chat.project.id, idempotency_key="s")
        job_queue.run_one()
        assert _job(db, job.id).status == "queued"
        assert db.query(Message).filter_by(project_id=chat.project.id, is_archived=True).count() == 0
        chat.llm.nonstream_error = None
        job_queue.run_one()
        assert _job(db, job.id).status == "completed"
        assert db.query(Message).filter_by(project_id=chat.project.id, is_archived=True).count() > 0

    def test_key_is_released_so_later_conversation_can_be_summarized_again(self, chat, db):
        seed_messages(db, chat.project, 12)
        job_queue.enqueue(db, "summarize", project_id=chat.project.id, idempotency_key="summarize:x")
        job_queue.run_one()
        _, created = job_queue.enqueue(db, "summarize", project_id=chat.project.id, idempotency_key="summarize:x")
        assert created


# ------------------------------------------------------------- chat vs. disconnects
@pytest.mark.live
class TestChatSurvivesDisconnect:
    def test_reply_is_saved_even_if_the_client_hangs_up_mid_stream(self, live_url, db, llm, make_user, make_project, auth):
        owner = make_user()
        project = make_project(owner)
        headers, project_id = auth(owner), project.id

        class SlowResponse(FakeResponse):
            def iter_lines(self):
                for token in ("Partial ", "reply ", "that ", "finishes ", "server-side."):
                    time.sleep(0.15)
                    yield sse("token", token)
                yield sse("metadata", {"chatId": "session-x", "sessionId": "session-x"})

        llm.stream_script = [lambda payload: SlowResponse(200)]

        with httpx.Client(timeout=30) as c:
            with c.stream("POST", f"{live_url}/api/predict", headers=headers,
                          json={"question": "hello", "projectId": project_id}) as resp:
                first = next(resp.iter_lines())
                assert first.startswith("data:")
            # leaving the block closes the connection while most of the reply is still coming

        deadline = time.time() + 15
        while time.time() < deadline:
            db.expire_all()
            ai = db.query(Message).filter_by(project_id=project_id, role="ai").all()
            if ai:
                break
            time.sleep(0.2)
        assert [m.text for m in ai] == ["Partial reply that finishes server-side."]
