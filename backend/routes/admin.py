import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import User, UserRole, AuditLog, Project, Message, ProjectMember, ProjectMemberRole
from dependencies.auth import get_current_user, get_db, require_role
from services.rbac_service import get_role_permissions_matrix, update_role_permissions_matrix

router = APIRouter(prefix="/api/admin", tags=["admin"])

@router.get("/dashboard-stats")
def get_dashboard_stats(
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    import datetime
    from sqlalchemy import func
    
    # 1. Total Users
    total_users = db.query(User).count()
    
    # 2. Active Users
    active_users = db.query(User).filter(User.status != "DISABLED").count()
    
    # 3. Projects
    total_projects = db.query(Project).count()
    
    # 4. Documents Generated (export log actions)
    docs_count = db.query(AuditLog).filter(AuditLog.action.like("%export%")).count()
    
    # 5. AI Requests Today (AI messages generated today)
    today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    ai_requests_today = db.query(Message).filter(
        Message.role == "ai",
        Message.created_at >= today_start
    ).count()
    
    # 6. Token Usage and Cost
    # SQLite length gives characters. Assume 1 token ~ 4 characters.
    total_chars = db.query(func.sum(func.length(Message.text))).scalar() or 0
    token_usage = total_chars // 4
    estimated_cost = token_usage * 0.00002
    
    # 7. Activity Chart Data (last 7 days of AI requests)
    seven_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=7)
    activity_query = db.query(
        func.strftime("%Y-%m-%d", Message.created_at).label("day"),
        func.count(Message.id).label("count")
    ).filter(
        Message.role == "ai",
        Message.created_at >= seven_days_ago
    ).group_by("day").order_by("day").all()
    
    # Map dates to chart activity
    activity_data = []
    for r in activity_query:
        if r.day:
            # Parse day name (Mon, Tue, Wed...)
            try:
                dt = datetime.datetime.strptime(r.day, "%Y-%m-%d")
                day_name = dt.strftime("%a")
            except Exception:
                day_name = r.day
            activity_data.append({"label": day_name, "value": r.count})
            
    # Default list if empty to prevent empty charts rendering problems
    if not activity_data:
        activity_data = [
            {"label": "Mon", "value": 0},
            {"label": "Tue", "value": 0},
            {"label": "Wed", "value": 0},
            {"label": "Thu", "value": 0},
            {"label": "Fri", "value": 0},
            {"label": "Sat", "value": 0},
            {"label": "Sun", "value": 0}
        ]
        
    # 8. Department Donut Chart Data
    dept_query = db.query(
        User.department,
        func.count(User.id)
    ).group_by(User.department).all()
    
    dept_data = []
    for dept, count in dept_query:
        dept_name = dept or "IT"
        dept_data.append({
            "name": dept_name,
            "count": count,
            "percentage": round((count / total_users) * 100) if total_users > 0 else 0
        })
        
    if not dept_data:
        dept_data = [{"name": "IT", "count": 1, "percentage": 100}]
        
    return {
        "totalUsers": total_users,
        "activeUsers": active_users,
        "totalProjects": total_projects,
        "documentsGenerated": docs_count,
        "aiRequestsToday": ai_requests_today,
        "tokenUsage": token_usage,
        "estimatedCost": estimated_cost,
        "activity": activity_data,
        "departments": dept_data
    }

class UserRoleUpdate(BaseModel):
    role: UserRole

class UserCreateRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: UserRole
    department: str | None = "IT"

class UserUpdateRequest(BaseModel):
    name: str
    email: EmailStr
    role: UserRole
    department: str | None = "IT"
    status: str | None = "ACTIVE"

class UserStatusUpdateRequest(BaseModel):
    status: str

@router.get("/users")
def get_users(
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    users = db.query(User).all()
    return [{
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "role": u.role,
        "department": u.department if hasattr(u, "department") else "IT",
        "status": u.status if hasattr(u, "status") else "ACTIVE",
        "last_login": u.last_login.isoformat() if (hasattr(u, "last_login") and u.last_login) else None,
        "projects_count": len(u.owned_projects) if hasattr(u, "owned_projects") else 0,
        "created_at": u.created_at.isoformat() if u.created_at else None
    } for u in users]

@router.put("/users/{user_id}/role")
def update_user_role(
    user_id: int,
    payload: UserRoleUpdate,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Do not allow admin to downgrade themselves (safety check)
    if user.id == current_user.id and payload.role != current_user.role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot change or downgrade their own system role."
        )

    old_role = user.role.value
    user.role = payload.role
    db.commit()
    
    # Log audit event
    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="user role updated",
        metadata={
            "target_user_id": user.id,
            "target_user_email": user.email,
            "old_role": old_role,
            "new_role": payload.role.value
        }
    )
    return {"status": "ok", "message": f"User role updated to {payload.role.value}"}

@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user_by_admin(
    payload: UserCreateRequest,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered"
        )
        
    from auth.jwt import hash_password
    pwd_hash = hash_password(payload.password)
    new_user = User(
        name=payload.name,
        email=payload.email,
        password_hash=pwd_hash,
        role=payload.role,
        department=payload.department or "IT",
        status="ACTIVE"
    )
    db.add(new_user)
    try:
        db.commit()
        db.refresh(new_user)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error during admin user creation: {str(e)}"
        )
        
    # Log audit event
    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="user created by admin",
        metadata={
            "created_user_id": new_user.id,
            "created_user_email": new_user.email,
            "role": new_user.role.value,
            "department": new_user.department
        }
    )
    return {"status": "ok", "user_id": new_user.id}

@router.put("/users/{user_id}")
def update_user_details(
    user_id: int,
    payload: UserUpdateRequest,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Prevent admin from disabling or downgrading themselves
    if user.id == current_user.id:
        if payload.status == "DISABLED":
            raise HTTPException(status_code=400, detail="You cannot disable your own administrator account.")
        if payload.role != current_user.role:
            raise HTTPException(status_code=400, detail="You cannot change your own administrator role.")

    # Check email duplicate
    email_user = db.query(User).filter(User.email == payload.email).first()
    if email_user and email_user.id != user_id:
        raise HTTPException(status_code=400, detail="Email is already used by another user.")

    old_values = {
        "name": user.name,
        "email": user.email,
        "role": user.role.value,
        "department": user.department,
        "status": user.status
    }

    user.name = payload.name
    user.email = payload.email
    user.role = payload.role
    user.department = payload.department
    user.status = payload.status
    db.commit()

    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="user details updated",
        metadata={
            "target_user_id": user.id,
            "old_values": old_values,
            "new_values": {
                "name": payload.name,
                "email": payload.email,
                "role": payload.role.value,
                "department": payload.department,
                "status": payload.status
            }
        }
    )
    return {"status": "ok", "message": "User details successfully updated."}

@router.put("/users/{user_id}/status")
def update_user_status(
    user_id: int,
    payload: UserStatusUpdateRequest,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user.id == current_user.id and payload.status == "DISABLED":
        raise HTTPException(status_code=400, detail="You cannot disable your own administrator account.")

    old_status = user.status
    user.status = payload.status
    db.commit()

    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="user status updated",
        metadata={
            "target_user_id": user.id,
            "target_user_email": user.email,
            "old_status": old_status,
            "new_status": payload.status
        }
    )
    return {"status": "ok", "message": f"User status updated to {payload.status}"}

@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own administrator account.")

    target_email = user.email
    db.delete(user)
    db.commit()

    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="user deleted",
        metadata={
            "deleted_user_id": user_id,
            "deleted_user_email": target_email
        }
    )
    return {"status": "ok", "message": "User successfully deleted from system."}

@router.get("/permissions")
def get_permissions(
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN]))
):
    return get_role_permissions_matrix()

@router.put("/permissions")
def save_permissions(
    payload: dict,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN]))
):
    success = update_role_permissions_matrix(payload)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save role permissions matrix.")
    return {"status": "ok", "message": "Permissions matrix successfully updated."}

@router.get("/audit-logs")
def get_audit_logs(
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    # Query logs ordered by timestamp descending
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).all()
    
    result = []
    for l in logs:
        user_email = "System/Anonymous"
        if l.user:
            user_email = l.user.email
            
        result.append({
            "id": l.id,
            "user_id": l.user_id,
            "user_email": user_email,
            "action": l.action,
            "project_id": l.project_id,
            "timestamp": l.timestamp.isoformat(),
            "metadata": json.loads(l.metadata_json) if l.metadata_json else None
        })
    return result

class ProjectAdminCreate(BaseModel):
    name: str
    description: str | None = None
    department: str | None = None
    business_unit: str | None = None
    priority: str | None = "MEDIUM"
    start_date: str | None = None
    end_date: str | None = None
    status: str | None = "DRAFT"
    tags: str | None = None

class ProjectAdminUpdate(BaseModel):
    name: str
    description: str | None = None
    department: str | None = None
    business_unit: str | None = None
    priority: str | None = "MEDIUM"
    start_date: str | None = None
    end_date: str | None = None
    status: str | None = "DRAFT"
    tags: str | None = None

class ProjectMembersAssign(BaseModel):
    user_ids: list[int]
    role: ProjectMemberRole

class ProjectMemberRoleUpdate(BaseModel):
    role: ProjectMemberRole

class ProjectOwnershipTransfer(BaseModel):
    owner_id: int

@router.get("/projects")
def list_admin_projects(
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    projects = db.query(Project).all()
    result = []
    for p in projects:
        member_count = db.query(ProjectMember).filter(ProjectMember.project_id == p.id).count()
        owner_name = "Unknown"
        if p.owner:
            owner_name = p.owner.name
        result.append({
            "id": p.id,
            "name": p.name,
            "owner_id": p.owner_id,
            "owner_name": owner_name,
            "description": p.description or "",
            "department": p.department or "",
            "business_unit": p.business_unit or "",
            "priority": p.priority or "MEDIUM",
            "start_date": p.start_date.isoformat() if p.start_date else None,
            "end_date": p.end_date.isoformat() if p.end_date else None,
            "status": p.status,
            "tags": p.tags or "",
            "member_count": member_count,
            "created_at": p.created_at.isoformat()
        })
    return result

@router.post("/projects")
def create_admin_project(
    payload: ProjectAdminCreate,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    import datetime
    import uuid
    
    s_date = None
    if payload.start_date:
        try:
            s_date = datetime.datetime.fromisoformat(payload.start_date.replace("Z", "+00:00"))
        except Exception:
            try:
                s_date = datetime.datetime.strptime(payload.start_date, "%Y-%m-%d")
            except Exception:
                pass
                
    e_date = None
    if payload.end_date:
        try:
            e_date = datetime.datetime.fromisoformat(payload.end_date.replace("Z", "+00:00"))
        except Exception:
            try:
                e_date = datetime.datetime.strptime(payload.end_date, "%Y-%m-%d")
            except Exception:
                pass

    session_id = f"session-{uuid.uuid4()}"
    
    # Initialize basic structured state
    from services.project_state_manager import DEFAULT_STATE
    state = DEFAULT_STATE.copy()
    state["project_name"] = payload.name
    state["department"] = payload.department or ""
    state["business_unit"] = payload.business_unit or ""

    db_project = Project(
        owner_id=current_user.id,
        name=payload.name,
        description=payload.description,
        department=payload.department,
        business_unit=payload.business_unit,
        priority=payload.priority or "MEDIUM",
        start_date=s_date,
        end_date=e_date,
        status=payload.status or "DRAFT",
        tags=payload.tags,
        session_id=session_id,
        structured_state=json.dumps(state)
    )
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    
    # Auto assign creator as PROJECT_MANAGER
    member = ProjectMember(
        project_id=db_project.id,
        user_id=current_user.id,
        role=ProjectMemberRole.PROJECT_MANAGER
    )
    db.add(member)
    db.commit()
    
    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="project created",
        project_id=db_project.id,
        metadata={"created_by": current_user.email, "project_name": db_project.name}
    )
    return {"status": "ok", "message": "Project created successfully.", "project_id": db_project.id}

@router.put("/projects/{project_id}")
def update_admin_project(
    project_id: int,
    payload: ProjectAdminUpdate,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    import datetime
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    s_date = None
    if payload.start_date:
        try:
            s_date = datetime.datetime.fromisoformat(payload.start_date.replace("Z", "+00:00"))
        except Exception:
            try:
                s_date = datetime.datetime.strptime(payload.start_date, "%Y-%m-%d")
            except Exception:
                pass
                
    e_date = None
    if payload.end_date:
        try:
            e_date = datetime.datetime.fromisoformat(payload.end_date.replace("Z", "+00:00"))
        except Exception:
            try:
                e_date = datetime.datetime.strptime(payload.end_date, "%Y-%m-%d")
            except Exception:
                pass
    
    project.name = payload.name
    project.description = payload.description
    project.department = payload.department
    project.business_unit = payload.business_unit
    project.priority = payload.priority
    project.start_date = s_date
    project.end_date = e_date
    project.status = payload.status
    project.tags = payload.tags
    
    # Sync with structured state
    try:
        if project.structured_state:
            state = json.loads(project.structured_state)
            state["project_name"] = payload.name
            state["department"] = payload.department or ""
            state["business_unit"] = payload.business_unit or ""
            project.structured_state = json.dumps(state)
    except Exception:
        pass
        
    db.commit()
    
    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="project updated",
        project_id=project.id,
        metadata={"updated_by": current_user.email}
    )
    return {"status": "ok", "message": "Project updated successfully."}

@router.delete("/projects/{project_id}")
def delete_admin_project(
    project_id: int,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    db.delete(project)
    db.commit()
    
    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="project deleted",
        metadata={"deleted_project_id": project_id}
    )
    return {"status": "ok", "message": "Project deleted successfully."}

@router.put("/projects/{project_id}/archive")
def archive_admin_project(
    project_id: int,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project.status = "ARCHIVED"
    db.commit()
    
    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="project archived",
        project_id=project.id,
        metadata={"archived_by": current_user.email}
    )
    return {"status": "ok", "message": "Project archived successfully."}

@router.put("/projects/{project_id}/transfer-ownership")
def transfer_admin_project_ownership(
    project_id: int,
    payload: ProjectOwnershipTransfer,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    new_owner = db.query(User).filter(User.id == payload.owner_id).first()
    if not new_owner:
        raise HTTPException(status_code=404, detail="New owner user not found")
        
    old_owner_id = project.owner_id
    project.owner_id = payload.owner_id
    
    # Ensure new owner is in project members as PROJECT_MANAGER
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == payload.owner_id
    ).first()
    if member:
        member.role = ProjectMemberRole.PROJECT_MANAGER
    else:
        new_member = ProjectMember(
            project_id=project_id,
            user_id=payload.owner_id,
            role=ProjectMemberRole.PROJECT_MANAGER
        )
        db.add(new_member)
        
    db.commit()
    
    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="project ownership transferred",
        project_id=project.id,
        metadata={
            "old_owner_id": old_owner_id,
            "new_owner_id": payload.owner_id
        }
    )
    return {"status": "ok", "message": "Project ownership transferred successfully."}

@router.post("/projects/{project_id}/members")
def assign_admin_project_members(
    project_id: int,
    payload: ProjectMembersAssign,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    added_count = 0
    for uid in payload.user_ids:
        user_exists = db.query(User).filter(User.id == uid).first()
        if not user_exists:
            continue
        existing_member = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == uid
        ).first()
        if existing_member:
            existing_member.role = payload.role
        else:
            new_member = ProjectMember(
                project_id=project_id,
                user_id=uid,
                role=payload.role
            )
            db.add(new_member)
        added_count += 1
        
    db.commit()
    
    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="project members assigned",
        project_id=project_id,
        metadata={"user_ids": payload.user_ids, "role": payload.role}
    )
    return {"status": "ok", "message": f"Successfully assigned {added_count} users to project."}

@router.put("/projects/{project_id}/members/{user_id}")
def update_admin_project_member_role(
    project_id: int,
    user_id: int,
    payload: ProjectMemberRoleUpdate,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found in this project.")
        
    old_role = member.role
    member.role = payload.role
    db.commit()
    
    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="project member role updated",
        project_id=project_id,
        metadata={"target_user_id": user_id, "old_role": old_role, "new_role": payload.role}
    )
    return {"status": "ok", "message": "Member role updated successfully."}

@router.delete("/projects/{project_id}/members/{user_id}")
def remove_admin_project_member(
    project_id: int,
    user_id: int,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found in this project.")
        
    db.delete(member)
    db.commit()
    
    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="project member removed",
        project_id=project_id,
        metadata={"target_user_id": user_id}
    )
    return {"status": "ok", "message": "User removed from project successfully."}

@router.get("/projects/{project_id}/details")
def get_admin_project_details(
    project_id: int,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    owner_name = project.owner.name if project.owner else "Unknown"
    owner_email = project.owner.email if project.owner else ""
    
    overview = {
        "id": project.id,
        "name": project.name,
        "description": project.description or "",
        "department": project.department or "",
        "business_unit": project.business_unit or "",
        "priority": project.priority or "MEDIUM",
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "end_date": project.end_date.isoformat() if project.end_date else None,
        "status": project.status,
        "tags": project.tags or "",
        "owner_name": owner_name,
        "owner_email": owner_email,
        "created_at": project.created_at.isoformat()
    }
    
    members_query = db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    members = []
    for m in members_query:
        if m.user:
            members.append({
                "id": m.user.id,
                "name": m.user.name,
                "email": m.user.email,
                "project_role": m.role
            })
            
    doc_logs = db.query(AuditLog).filter(
        AuditLog.project_id == project_id,
        AuditLog.action.like("%export%")
    ).order_by(AuditLog.timestamp.desc()).all()
    documents = []
    for dl in doc_logs:
        doc_type = "PDF" if "pdf" in dl.action.lower() else "DOCX"
        documents.append({
            "id": dl.id,
            "timestamp": dl.timestamp.isoformat(),
            "action": dl.action,
            "format": doc_type,
            "triggered_by": dl.user.email if dl.user else "System"
        })
        
    from models import Message
    messages_query = db.query(Message).filter(
        Message.project_id == project_id
    ).order_by(Message.created_at.desc()).limit(30).all()
    messages_query.reverse()
    conversations = [{
        "id": m.id,
        "role": m.role,
        "text": m.text,
        "created_at": m.created_at.isoformat()
    } for m in messages_query]
    
    activity_logs = db.query(AuditLog).filter(
        AuditLog.project_id == project_id
    ).order_by(AuditLog.timestamp.desc()).limit(50).all()
    activity = []
    for al in activity_logs:
        user_email = al.user.email if al.user else "System"
        activity.append({
            "id": al.id,
            "action": al.action,
            "user_email": user_email,
            "timestamp": al.timestamp.isoformat(),
            "metadata": json.loads(al.metadata_json) if al.metadata_json else None
        })
        
    return {
        "overview": overview,
        "members": members,
        "documents": documents,
        "conversations": conversations,
        "activity": activity
    }
