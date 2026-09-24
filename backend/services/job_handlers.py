"""Handlers for background jobs. Each one is idempotent: a retry, or a re-run after a
worker died mid-job, must not repeat side effects (extra LLM summaries, duplicate files
or duplicate audit entries)."""
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import Job, Project
from services.audit import log_action
from services.export_service import export_filename, generate_export, media_type_for, normalize_format
from services.job_queue import PermanentJobError, register_handler
from services.summary_manager import check_and_summarize

SUMMARIZE = "summarize"
EXPORT = "export"


def exports_dir() -> str:
    path = os.path.abspath(os.path.join(os.getenv("UPLOAD_DIR", "uploads"), "exports"))
    os.makedirs(path, exist_ok=True)
    return path


def handle_summarize(db, job: Job) -> dict:
    project = db.get(Project, job.project_id)
    if project is None:
        raise PermanentJobError("Project no longer exists")
    # The summary update and message archiving commit together, and once the messages are
    # archived this becomes a no-op, so a retry cannot summarize the same messages twice.
    summarized = check_and_summarize(db, project, raise_on_error=True)
    return {"summarized": summarized}


def handle_export(db, job: Job) -> dict:
    params = json.loads(job.payload or "{}")
    try:
        fmt = normalize_format(params.get("format", ""))
    except ValueError as exc:
        raise PermanentJobError(str(exc))
    project = db.get(Project, job.project_id)
    if project is None:
        raise PermanentJobError("Project no longer exists")

    # The file name is derived from the job id, so a retry after a crash that happened
    # after the file was written reuses it instead of generating (and auditing) it again.
    path = os.path.join(exports_dir(), f"{job.id}.{fmt}")
    filename = export_filename(project.name, fmt)
    if not os.path.isfile(path):
        # Only the last attempt may fall back to a placeholder document; earlier attempts
        # raise on an LLM failure so the queue retries with backoff.
        stream, filename, _ = generate_export(project, fmt, allow_fallback=job.attempts >= job.max_attempts)
        tmp = f"{path}.tmp"
        with open(tmp, "wb") as fh:
            fh.write(stream.getvalue())
        os.replace(tmp, path)  # atomic: a reader never sees a half-written file
        log_action(
            db=db,
            user_id=job.user_id,
            action="document generation",
            project_id=job.project_id,
            metadata={"format": fmt, "job_id": job.id},
        )
    return {"file_path": path, "filename": filename, "media_type": media_type_for(fmt)}


def register_all() -> None:
    register_handler(SUMMARIZE, handle_summarize)
    register_handler(EXPORT, handle_export)


register_all()
