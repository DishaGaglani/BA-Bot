"""A small database-backed background job queue.

Long-running work (LLM summarization, document export) runs on worker threads
instead of inside HTTP request handlers. The `jobs` table is the queue, so it needs
no extra infrastructure (no Redis/broker) and jobs survive a restart.

Guarantees:
  * Status tracking:   queued -> processing -> completed | failed
  * Retries:           exponential backoff, up to `max_attempts`
  * Idempotent enqueue: a unique `idempotency_key` makes duplicate requests return
                        the existing job rather than creating another
  * Crash recovery:    a claimed job holds a lease; if its worker dies the lease
                        expires and the job is re-queued (or failed after max attempts)
  * Safe across processes: claiming is one atomic conditional UPDATE, so several
                        uvicorn workers can share the same table

Handlers must be idempotent (a retry, or a re-run after a lease expiry, must not
duplicate side effects); see services/job_handlers.py.

Configuration (environment):
  JOB_WORKERS                 worker threads per process, 0 disables (default 2)
  JOB_POLL_INTERVAL_SECONDS   idle polling interval (default 1)
  JOB_MAX_ATTEMPTS            attempts before a job is failed (default 3)
  JOB_BACKOFF_BASE_SECONDS    first retry delay, doubles each attempt (default 5)
  JOB_BACKOFF_MAX_SECONDS     retry delay cap (default 300)
  JOB_LEASE_SECONDS           how long a claimed job may run before it is presumed
                              dead and re-queued (default 600)
  JOB_RETENTION_DAYS          finished jobs and their files are purged after this (default 7)
"""
import datetime
import json
import os
import sys
import threading
import time
import uuid
from typing import Callable, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal
from models import Job
from utils.prod_ready import logger

QUEUED = "queued"
PROCESSING = "processing"
COMPLETED = "completed"
FAILED = "failed"
ACTIVE_STATUSES = (QUEUED, PROCESSING)

# Job types whose idempotency key only guards against *concurrent* duplicates; the
# key is released when the job finishes so the same work can be scheduled again later.
# (An export keeps its key: re-requesting an unchanged export returns the finished file.)
RELEASE_KEY_WHEN_DONE = {"summarize"}

Handler = Callable[[Session, Job], Optional[dict]]
_HANDLERS: dict[str, Handler] = {}


class PermanentJobError(Exception):
    """Raise from a handler when retrying cannot help (e.g. the project was deleted)."""


def register_handler(job_type: str, handler: Handler) -> None:
    _HANDLERS[job_type] = handler


def _now() -> datetime.datetime:
    return datetime.datetime.utcnow()


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _log(job: Job, message: str, level: str = "info") -> None:
    getattr(logger, level)(f"job={job.id} type={job.type} {message}", extra={"traceId": f"job-{job.id[:8]}"})


# ----------------------------------------------------------------------- enqueue
def enqueue(
    db: Session,
    job_type: str,
    *,
    project_id: Optional[int] = None,
    user_id: Optional[int] = None,
    payload: Optional[dict] = None,
    idempotency_key: Optional[str] = None,
    max_attempts: Optional[int] = None,
) -> tuple[Job, bool]:
    """Queue a job. Returns (job, created).

    If `idempotency_key` is already in use, no new job is created and the existing
    one is returned with created=False. A previously *failed* job under that key is
    reset and re-queued, so the caller can simply retry the request.
    """
    now = _now()
    job = Job(
        id=uuid.uuid4().hex,
        type=job_type,
        status=QUEUED,
        project_id=project_id,
        user_id=user_id,
        idempotency_key=idempotency_key,
        payload=json.dumps(payload) if payload is not None else None,
        attempts=0,
        max_attempts=max_attempts or _int_env("JOB_MAX_ATTEMPTS", 3),
        next_run_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(Job).filter(Job.idempotency_key == idempotency_key).first() if idempotency_key else None
        if existing is None:
            raise
        if existing.status == FAILED:
            existing.status = QUEUED
            existing.attempts = 0
            existing.error = None
            existing.result = None
            existing.finished_at = None
            existing.locked_until = None
            existing.next_run_at = now
            existing.updated_at = now
            existing.payload = job.payload
            existing.user_id = user_id
            db.commit()
        return existing, False
    db.refresh(job)
    return job, True


# ------------------------------------------------------------------------ claim
def _recover_stale(db: Session, now: datetime.datetime) -> None:
    """Re-queue (or fail) jobs whose worker vanished without finishing them."""
    stale = db.query(Job).filter(Job.status == PROCESSING, Job.locked_until < now).all()
    for job in stale:
        exhausted = job.attempts >= job.max_attempts
        values = {
            "status": FAILED if exhausted else QUEUED,
            "locked_until": None,
            "next_run_at": now,
            "updated_at": now,
        }
        if exhausted:
            values["error"] = "Worker lease expired; attempts exhausted"
            values["finished_at"] = now
            if job.type in RELEASE_KEY_WHEN_DONE:
                values["idempotency_key"] = None
        # Conditional on the lease still being expired, so two processes can't both recover it.
        db.query(Job).filter(Job.id == job.id, Job.status == PROCESSING, Job.locked_until < now).update(
            values, synchronize_session=False
        )
    db.commit()


def claim_next(db: Session) -> Optional[Job]:
    """Atomically claim the oldest runnable job, or return None."""
    now = _now()
    _recover_stale(db, now)
    lease = now + datetime.timedelta(seconds=_int_env("JOB_LEASE_SECONDS", 600))
    for _ in range(5):  # another worker may win the race for a candidate; try the next one
        candidate = (
            db.query(Job.id)
            .filter(Job.status == QUEUED, Job.next_run_at <= now)
            .order_by(Job.next_run_at, Job.created_at)
            .first()
        )
        if candidate is None:
            return None
        claimed = (
            db.query(Job)
            .filter(Job.id == candidate.id, Job.status == QUEUED)
            .update(
                {Job.status: PROCESSING, Job.attempts: Job.attempts + 1, Job.locked_until: lease, Job.updated_at: now},
                synchronize_session=False,
            )
        )
        db.commit()
        if claimed == 1:
            db.expire_all()
            return db.get(Job, candidate.id)
    return None


# ---------------------------------------------------------------------- execute
def _backoff_seconds(attempt: int) -> int:
    base = _int_env("JOB_BACKOFF_BASE_SECONDS", 5)
    cap = _int_env("JOB_BACKOFF_MAX_SECONDS", 300)
    return min(cap, base * (2 ** max(attempt - 1, 0)))


def _finish(db: Session, job_id: str, status: str, *, result: Optional[dict] = None, error: Optional[str] = None) -> None:
    job = db.get(Job, job_id)
    if job is None:  # purged while running; nothing left to record
        return
    now = _now()
    job.status = status
    job.locked_until = None
    job.updated_at = now
    job.finished_at = now
    job.error = error
    if result is not None:
        job.result = json.dumps(result)
    if str(job.type) in RELEASE_KEY_WHEN_DONE:
        job.idempotency_key = None
    db.commit()


def process_job(db: Session, job: Job) -> str:
    """Run a claimed job and record the outcome. Returns the resulting status."""
    job_id, attempt, max_attempts = job.id, job.attempts, job.max_attempts
    handler = _HANDLERS.get(str(job.type))
    try:
        if handler is None:
            raise PermanentJobError(f"No handler registered for job type '{job.type}'")
        _log(job, f"started attempt={attempt}/{max_attempts}")
        result = handler(db, job)
        _finish(db, job_id, COMPLETED, result=result or {})
        _log(job, "completed")
        return COMPLETED
    except Exception as exc:  # noqa: BLE001 - every handler failure goes through retry/fail accounting
        db.rollback()
        message = f"{type(exc).__name__}: {exc}"
        job = db.get(Job, job_id)
        if job is None:  # purged while running
            return FAILED
        if isinstance(exc, PermanentJobError) or attempt >= max_attempts:
            _finish(db, job_id, FAILED, error=message)
            _log(job, f"failed permanently after attempt {attempt}/{max_attempts}: {message}", "error")
            return FAILED
        delay = _backoff_seconds(attempt)
        now = _now()
        job.status = QUEUED
        job.locked_until = None
        job.error = message
        job.next_run_at = now + datetime.timedelta(seconds=delay)
        job.updated_at = now
        db.commit()
        _log(job, f"attempt {attempt}/{max_attempts} failed, retrying in {delay}s: {message}", "warning")
        return QUEUED


def run_one() -> bool:
    """Claim and run a single job on a fresh session. Returns False if nothing was runnable."""
    db = SessionLocal()
    try:
        job = claim_next(db)
        if job is None:
            return False
        process_job(db, job)
        return True
    finally:
        db.close()


# ------------------------------------------------------------------ housekeeping
def purge_finished(db: Session, retention_days: Optional[int] = None) -> int:
    """Delete finished jobs older than the retention window, and any file they produced."""
    days = retention_days if retention_days is not None else _int_env("JOB_RETENTION_DAYS", 7)
    cutoff = _now() - datetime.timedelta(days=days)
    old = db.query(Job).filter(Job.status.in_([COMPLETED, FAILED]), Job.finished_at < cutoff).all()
    for job in old:
        try:
            path = (json.loads(job.result) if job.result else {}).get("file_path")
            if path and os.path.isfile(path):
                os.remove(path)
        except Exception:
            pass
        db.delete(job)
    db.commit()
    return len(old)


# ---------------------------------------------------------------------- workers
_threads: list[threading.Thread] = []
_stop = threading.Event()
_PURGE_EVERY_SECONDS = 3600


def _worker_loop(worker_index: int) -> None:
    poll = max(_int_env("JOB_POLL_INTERVAL_SECONDS", 1), 1)
    last_purge = 0.0
    while not _stop.is_set():
        try:
            if worker_index == 0 and time.monotonic() - last_purge > _PURGE_EVERY_SECONDS:
                last_purge = time.monotonic()
                db = SessionLocal()
                try:
                    purge_finished(db)
                finally:
                    db.close()
            if run_one():
                continue  # more work may be waiting; don't sleep
        except Exception as exc:  # noqa: BLE001 - a worker must survive any single failure
            logger.error(f"job worker error: {exc}", extra={"traceId": "job-worker"})
        _stop.wait(poll)


def start_workers() -> int:
    """Start the worker threads (idempotent). Returns how many are running."""
    count = _int_env("JOB_WORKERS", 2)
    if count <= 0 or any(t.is_alive() for t in _threads):
        return len([t for t in _threads if t.is_alive()])
    _stop.clear()
    _threads.clear()
    for i in range(count):
        t = threading.Thread(target=_worker_loop, args=(i,), name=f"job-worker-{i}", daemon=True)
        t.start()
        _threads.append(t)
    logger.info(f"Started {count} background job worker(s)", extra={"traceId": "startup"})
    return count


def stop_workers(timeout: float = 5.0) -> None:
    _stop.set()
    for t in _threads:
        t.join(timeout=timeout)
    _threads.clear()
