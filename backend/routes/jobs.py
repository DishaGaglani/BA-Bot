import hashlib
import json
import os
import sys

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import Job, Message, Project, ProjectMemberRole, User
from dependencies.auth import get_current_user, get_db, require_project_access
from services import job_handlers, job_queue
from services.export_service import UnsupportedFormat, normalize_format

router = APIRouter(tags=["jobs"])


def _serialize(job: Job) -> dict:
    result = json.loads(job.result) if job.result else None
    data = {
        "job_id": job.id,
        "type": job.type,
        "status": job.status,
        "project_id": job.project_id,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "error": job.error if job.status == job_queue.FAILED else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
    if job.status == job_queue.COMPLETED and job.type == job_handlers.EXPORT and result:
        data["download_url"] = f"/api/jobs/{job.id}/download"
        data["filename"] = result.get("filename")
    return data


def _export_fingerprint(db: Session, project: Project, fmt: str) -> str:
    """Identifies the exact inputs of an export. Re-requesting an export while the
    project is unchanged maps to the same idempotency key and returns the same job."""
    last_message_id = db.query(func.max(Message.id)).filter(Message.project_id == project.id).scalar() or 0
    digest = hashlib.sha256(
        json.dumps(
            [project.name, project.structured_state, project.summary, project.data, last_message_id],
            default=str,
        ).encode()
    ).hexdigest()[:16]
    return f"export:{project.id}:{fmt}:{digest}"


@router.post("/api/projects/{project_id}/export-jobs", status_code=status.HTTP_202_ACCEPTED)
def create_export_job(
    project_id: int,
    format: str,
    project: Project = Depends(require_project_access(ProjectMemberRole.VIEWER)),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Queue a document export. Poll GET /api/jobs/{job_id} until it is completed, then
    download it from GET /api/jobs/{job_id}/download."""
    try:
        fmt = normalize_format(format)
    except UnsupportedFormat as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    job, _created = job_queue.enqueue(
        db,
        job_handlers.EXPORT,
        project_id=project.id,
        user_id=current_user.id,
        payload={"format": fmt},
        idempotency_key=_export_fingerprint(db, project, fmt),
    )
    return _serialize(job)


def _load_authorized_job(job_id: str, current_user: User, db: Session) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.project_id is not None:
        # Same rule as reading the project itself (owner, member, team or admin).
        require_project_access(ProjectMemberRole.VIEWER)(project_id=job.project_id, current_user=current_user, db=db)
    elif job.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You do not have access to this job")
    return job


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _serialize(_load_authorized_job(job_id, current_user, db))


@router.get("/api/jobs/{job_id}/download")
def download_job_result(job_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = _load_authorized_job(job_id, current_user, db)
    if job.type != job_handlers.EXPORT:
        raise HTTPException(status_code=400, detail="This job has no downloadable file")
    if job.status != job_queue.COMPLETED:
        raise HTTPException(status_code=409, detail=f"Job is {job.status}, not completed")
    result = json.loads(job.result or "{}")
    path = result.get("file_path")
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=410, detail="The exported file is no longer available; request a new export")
    return FileResponse(
        path,
        media_type=result.get("media_type"),
        headers={
            "Content-Disposition": f"attachment; filename={result.get('filename')}",
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
