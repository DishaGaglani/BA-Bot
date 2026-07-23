import json
import requests
import urllib3
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session, joinedload
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import User, UserRole, Project, ProjectMember, ProjectMemberRole
from services.audit import log_action
from dependencies.auth import (
    get_current_user,
    get_db,
    require_role,
    require_project_access,
    require_project_owner
)
from utils.export import parse_markdown_to_docx, parse_markdown_to_pdf
from services.project_state_manager import get_legacy_payload, get_structured_state, DEFAULT_STATE

router = APIRouter(prefix="/api/projects", tags=["projects"])

# Disable SSL Warnings for self-signed certificates or proxy contexts
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PREDICTION_URL = "https://forjinn.com/api/v1/prediction/249fc96e-5b62-4208-8787-0d77367e9eaf"

class RequirementPayload(BaseModel):
    title: str
    priority: str
    confidence: float

class ProjectDetailsPayload(BaseModel):
    name: str
    department: str
    sponsor: str
    business_unit: str
    expected_completion: str

class ProjectPayload(BaseModel):
    id: int | None = None
    sessionId: str | None = None
    pdfGenerated: bool | None = False
    messages: list[dict] | None = None
    project: ProjectDetailsPayload
    overview: dict
    discovery: dict
    functional_requirements: list[RequirementPayload]
    missing_fields: list[str]
    next_question: str

class ReviewRequest(BaseModel):
    approved: bool
    feedback: str | None = None

class InviteRequest(BaseModel):
    email: EmailStr
    role: ProjectMemberRole

@router.get("", response_model=list[dict])
def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role in [UserRole.SUPER_ADMIN, UserRole.ADMIN]:
        db_projects = db.query(Project).options(joinedload(Project.messages)).all()
    else:
        # Get projects where user is owner or invited member
        db_projects = db.query(Project).options(joinedload(Project.messages)).outerjoin(ProjectMember).filter(
            (Project.owner_id == current_user.id) | (ProjectMember.user_id == current_user.id)
        ).distinct().all()
    
    result = []
    for p in db_projects:
        try:
            # Auto-assign session_id if missing
            if not p.session_id:
                import uuid
                p.session_id = f"session-{uuid.uuid4()}"
                db.commit()
            result.append(get_legacy_payload(p))
        except Exception:
            pass
    return result

@router.get("/{project_id}")
def get_project(
    project_id: int,
    project: Project = Depends(require_project_access(ProjectMemberRole.VIEWER)),
    db: Session = Depends(get_db)
):
    return get_legacy_payload(project)

@router.post("")
def create_project(
    payload: ProjectPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role not in [UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.BUSINESS_ANALYST, UserRole.PROJECT_MANAGER, UserRole.REVIEWER]:
        # Log unauthorized attempt
        log_action(
            db=db,
            user_id=current_user.id,
            action="permission denied",
            metadata={"reason": f"Role {current_user.role.value} tried to create project"}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admins, Business Analysts, Project Managers, and Reviewers can create projects"
        )

    import uuid
    if not payload.sessionId:
        payload.sessionId = f"session-{uuid.uuid4()}"
    
    # Initialize the structured state for new project
    state = DEFAULT_STATE.copy()
    state["project_name"] = payload.project.name or "New Project"
    state["department"] = payload.project.department or ""
    state["sponsor"] = payload.project.sponsor or ""
    state["business_unit"] = payload.project.business_unit or ""
    state["timeline"] = payload.project.expected_completion or ""
    
    project_data_json = json.dumps(payload.model_dump())
    
    db_project = Project(
        owner_id=current_user.id,
        name=payload.project.name or "New Project",
        status="DRAFT",
        session_id=payload.sessionId,
        data=project_data_json,
        structured_state=json.dumps(state)
    )
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    
    # Automatically add owner to ProjectMember
    member = ProjectMember(
        project_id=db_project.id,
        user_id=current_user.id,
        role=ProjectMemberRole.PROJECT_MANAGER
    )
    db.add(member)
    db.commit()
    
    # Log audit event
    log_action(
        db=db,
        user_id=current_user.id,
        action="project creation",
        project_id=db_project.id,
        metadata={"name": db_project.name}
    )
    
    return get_legacy_payload(db_project)

@router.put("/{project_id}")
def update_project(
    project_id: int,
    payload: ProjectPayload,
    project: Project = Depends(require_project_access(ProjectMemberRole.CONTRIBUTOR)),
    db: Session = Depends(get_db)
):
    if project.locked:
        raise HTTPException(status_code=403, detail="Project is locked and cannot be updated.")

    # Preserve existing sessionId if update payload lacks one
    try:
        existing_data = json.loads(project.data)
        existing_session_id = existing_data.get("sessionId")
        if existing_session_id and not payload.sessionId:
            payload.sessionId = existing_session_id
    except Exception:
        pass

    if not payload.sessionId:
        import uuid
        payload.sessionId = f"session-{uuid.uuid4()}"

    payload.id = project_id
    project.name = payload.project.name or project.name
    project.session_id = payload.sessionId
    project.data = json.dumps(payload.model_dump())
    
    # Sync structured_state with frontend payload updates
    state = get_structured_state(project)
    state["project_name"] = payload.project.name
    state["department"] = payload.project.department
    state["sponsor"] = payload.project.sponsor
    state["business_unit"] = payload.project.business_unit
    state["industry"] = payload.project.business_unit
    state["timeline"] = payload.project.expected_completion
    
    if isinstance(payload.overview, dict):
      state["overview_description"] = payload.overview.get("description", "")
      state["stakeholders"] = payload.overview.get("stakeholders", [])
        
    if isinstance(payload.discovery, dict):
      state["business_problem"] = payload.discovery.get("business_problem", "")
      state["business_goals"] = payload.discovery.get("business_goals", "")
      state["desired_outcomes"] = payload.discovery.get("desired_outcomes", "")
      state["constraints"] = payload.discovery.get("constraints", "")
      state["budget"] = payload.discovery.get("budget", "")
      state["integrations"] = payload.discovery.get("integrations", [])
      state["non_functional_requirements"] = payload.discovery.get("non_functional_requirements", "")
        
    # Map functional requirements
    state["functional_requirements"] = [
        req.model_dump() if hasattr(req, "model_dump") else req 
        for req in payload.functional_requirements
    ]
    
    project.structured_state = json.dumps(state)
    db.commit()
    
    return get_legacy_payload(project)

@router.delete("/{project_id}")
def delete_project(
    project_id: int,
    project: Project = Depends(require_project_owner),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db.delete(project)
    db.commit()
    
    # Log audit event
    log_action(
        db=db,
        user_id=current_user.id,
        action="project deletion",
        project_id=project_id,
        metadata={"name": project.name}
    )
    return {"status": "deleted"}

@router.get("/{project_id}/export")
def export_project(
    project_id: int,
    format: str,
    project: Project = Depends(require_project_access(ProjectMemberRole.VIEWER)),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):


    session_id = project.session_id
    project_name = project.name
    state = get_structured_state(project)
    
    prompt = (
        f"The requirements interview discovery workshop is complete for project '{project_name}'.\n\n"
        "Here is the final gathered Project Requirements State gathered during the interview:\n"
        f"{json.dumps(state, indent=2)}\n\n"
        "Please generate and compile the final, detailed, and polished Requirements Discovery Document (FDR) "
        "containing all project information, overview, stakeholders, business problem, business goals, timeline, functional requirements, and constraints. "
        "Format the output using clear Markdown headings, bullet points, and numbered lists."
    )
    
    payload = {
        "question": prompt,
        "streaming": False
    }
        
    try:
        response = requests.post(PREDICTION_URL, json=payload, timeout=180, verify=False)
        response.raise_for_status()
        res_data = response.json()
        
        document_text = res_data.get("text")
        if not document_text:
            output_obj = res_data.get("output")
            if isinstance(output_obj, dict):
                document_text = output_obj.get("content", "")
            elif isinstance(output_obj, str):
                document_text = output_obj
            else:
                document_text = ""
                
        if not document_text:
            raise HTTPException(status_code=500, detail="Prediction service returned empty compiled text")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to generate compiled document from Forjinn flow: {str(e)}")
        
    if format.lower() == "docx":
        file_stream = parse_markdown_to_docx(document_text)
        filename = f"{project_name.replace(' ', '_')}_Requirements.docx"
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif format.lower() == "pdf":
        file_stream = parse_markdown_to_pdf(document_text)
        filename = f"{project_name.replace(' ', '_')}_Requirements.pdf"
        media_type = "application/pdf"
    else:
        raise HTTPException(status_code=400, detail="Invalid format. Supported: docx, pdf")
        
    # Log document generation in AuditLog
    log_action(
        db=db,
        user_id=current_user.id,
        action="document generation",
        project_id=project_id,
        metadata={"format": format}
    )

    return StreamingResponse(
        file_stream,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )

@router.post("/{project_id}/submit")
def submit_project(
    project_id: int,
    project: Project = Depends(require_project_access(ProjectMemberRole.CONTRIBUTOR)),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if project.locked:
        raise HTTPException(status_code=403, detail="Project is locked and cannot be submitted.")

    project.status = "PENDING_REVIEW"
    db.commit()
    
    log_action(
        db=db,
        user_id=current_user.id,
        action="project submission",
        project_id=project_id
    )
    return {"status": "ok", "new_status": "PENDING_REVIEW"}

@router.post("/{project_id}/review")
def review_project(
    project_id: int,
    payload: ReviewRequest,
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.REVIEWER])),
    db: Session = Depends(get_db)
):
    project = db.query(Project).options(joinedload(Project.messages)).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    new_status = "APPROVED" if payload.approved else "DRAFT"
    project.status = new_status
    db.commit()
    
    # Log audit event
    log_action(
        db=db,
        user_id=current_user.id,
        action="document approval" if payload.approved else "document rejection",
        project_id=project_id,
        metadata={"feedback": payload.feedback}
    )
    return {"status": "ok", "new_status": new_status}

@router.post("/{project_id}/publish")
def publish_project(
    project_id: int,
    project: Project = Depends(require_project_access(ProjectMemberRole.PROJECT_MANAGER)),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if project.status != "APPROVED":
        raise HTTPException(status_code=400, detail="Only approved requirements can be published.")
        
    project.status = "PUBLISHED"
    db.commit()
    
    log_action(
        db=db,
        user_id=current_user.id,
        action="project publish",
        project_id=project_id
    )
    return {"status": "ok", "new_status": "PUBLISHED"}

@router.post("/{project_id}/invite")
def invite_member(
    project_id: int,
    payload: InviteRequest,
    project: Project = Depends(require_project_owner),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    invited_user = db.query(User).filter(User.email == payload.email).first()
    if not invited_user:
        raise HTTPException(status_code=404, detail="User with this email not found")
        
    # Check if already a member
    existing_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == invited_user.id
    ).first()
    if existing_member:
        existing_member.role = payload.role
        db.commit()
        return {"status": "ok", "message": f"Updated {payload.email} role to {payload.role.value}"}
        
    member = ProjectMember(
        project_id=project_id,
        user_id=invited_user.id,
        role=payload.role
    )
    db.add(member)
    db.commit()
    
    log_action(
        db=db,
        user_id=current_user.id,
        action="member invited",
        project_id=project_id,
        metadata={"invited_email": payload.email, "role": payload.role.value}
    )
    return {"status": "ok", "message": f"User {payload.email} invited as {payload.role.value}"}

@router.get("/{project_id}/members")
def get_members(
    project_id: int,
    project: Project = Depends(require_project_access(ProjectMemberRole.VIEWER)),
    db: Session = Depends(get_db)
):
    members = db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    result = []
    for m in members:
        result.append({
            "id": m.id,
            "user_id": m.user.id,
            "name": m.user.name,
            "email": m.user.email,
            "role": m.role.value
        })
    return result
