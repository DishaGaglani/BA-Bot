import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import User, UserRole, AuditLog, Project, Message, ProjectMember, ProjectMemberRole, Team, TeamProject
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
    token_usage = db.query(func.sum(Message.token_count)).scalar() or 0
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
            "locked": p.locked,
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
        "locked": project.locked,
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

class SystemSettingsUpdate(BaseModel):
    workspaceName: str
    aiModel: str
    tokenTimeout: int
    allowRegistration: bool
    systemPrompt: str | None = None

@router.get("/conversations")
def list_admin_conversations(
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    from sqlalchemy import func
    from models import Message
    # Query project name, session_id, message count, and last active timestamp
    results = db.query(
        Project.id.label("project_id"),
        Project.name.label("project_name"),
        Project.session_id.label("session_id"),
        func.count(Message.id).label("message_count"),
        func.max(Message.created_at).label("last_active")
    ).join(Message, Message.project_id == Project.id).group_by(Project.id).all()
    
    return [{
        "project_id": r.project_id,
        "project_name": r.project_name,
        "session_id": r.session_id,
        "message_count": r.message_count,
        "last_active": r.last_active.isoformat() if r.last_active else None
    } for r in results]

@router.delete("/conversations/{project_id}")
def delete_admin_conversation(
    project_id: int,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    from models import Message
    # Delete all messages for this project
    db.query(Message).filter(Message.project_id == project_id).delete()
    db.commit()
    
    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="conversation deleted",
        project_id=project_id,
        metadata={"deleted_by": current_user.email}
    )
    return {"status": "ok", "message": "Conversation history cleared successfully."}

@router.get("/documents")
def list_admin_documents(
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    # Query export logs
    doc_logs = db.query(AuditLog).filter(
        AuditLog.action.like("%export%")
    ).order_by(AuditLog.timestamp.desc()).all()
    
    result = []
    for dl in doc_logs:
        doc_type = "PDF" if "pdf" in dl.action.lower() else "DOCX"
        project_name = dl.project.name if dl.project else "Unknown Project"
        result.append({
            "id": dl.id,
            "project_id": dl.project_id,
            "project_name": project_name,
            "action": dl.action,
            "format": doc_type,
            "triggered_by": dl.user.email if dl.user else "System",
            "timestamp": dl.timestamp.isoformat()
        })
    return result

@router.get("/analytics")
def get_admin_analytics(
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    from sqlalchemy import func
    
    # 1. Users by Role
    role_stats = db.query(User.role, func.count(User.id)).group_by(User.role).all()
    roles_data = [{"role": r[0].value, "count": r[1]} for r in role_stats]
    
    # 2. Projects trend
    proj_stats = db.query(
        func.strftime("%Y-%m-%d", Project.created_at).label("day"),
        func.count(Project.id)
    ).group_by("day").order_by("day").all()
    projects_trend = [{"date": r[0], "count": r[1]} for r in proj_stats]
    
    # 3. Top Active Users (most audit logs)
    top_users = db.query(
        User.name,
        User.email,
        func.count(AuditLog.id).label("log_count")
    ).join(AuditLog, AuditLog.user_id == User.id).group_by(User.id).order_by(func.count(AuditLog.id).desc()).limit(5).all()
    
    active_users_data = [{
        "name": r.name,
        "email": r.email,
        "activity_count": r.log_count
    } for r in top_users]
    
    # 4. Logs summary count by action
    action_stats = db.query(
        AuditLog.action,
        func.count(AuditLog.id)
    ).group_by(AuditLog.action).order_by(func.count(AuditLog.id).desc()).limit(10).all()
    actions_data = [{"action": r[0], "count": r[1]} for r in action_stats]
    
    return {
        "rolesDistribution": roles_data,
        "projectsTrend": projects_trend,
        "mostActiveUsers": active_users_data,
        "actionsSummary": actions_data
    }

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "system_settings.json")

def read_settings() -> dict:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "workspaceName": "BA Bot Workspace",
        "aiModel": "Prediction Agent",
        "tokenTimeout": 3600,
        "allowRegistration": True,
        "systemPrompt": (
            "You are an expert Business Analyst leading a structured discovery workshop.\n"
            "Your objective is to interview the user and gather requirements. Ask only one clear, "
            "concise question at a time to gather the needed information for the current focus section.\n"
            "Guidelines:\n"
            "1. Do not ask questions about sections that are already completed.\n"
            "2. If the user wanders off-topic, gently guide them back to the active section.\n"
            "3. Keep your questions and responses brief and highly conversational."
        )
    }

@router.get("/settings")
def get_admin_settings(
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN]))
):
    return read_settings()

@router.put("/settings")
def save_admin_settings(
    payload: SystemSettingsUpdate,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN]))
):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(payload.model_dump(), f, indent=2)
        return {"status": "ok", "message": "Settings saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save settings file: {str(e)}")

@router.put("/projects/{project_id}/lock")
def lock_admin_project(
    project_id: int,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    project.locked = True
    db.commit()
    
    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="project locked",
        project_id=project.id,
        metadata={"locked_by": current_user.email}
    )
    return {"status": "ok", "message": "Project locked successfully."}

@router.put("/projects/{project_id}/unlock")
def unlock_admin_project(
    project_id: int,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    project.locked = False
    db.commit()
    
    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="project unlocked",
        project_id=project.id,
        metadata={"unlocked_by": current_user.email}
    )
    return {"status": "ok", "message": "Project unlocked successfully."}

@router.post("/projects/{project_id}/clone")
def clone_admin_project(
    project_id: int,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    import uuid
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    session_id = f"session-{uuid.uuid4()}"
    
    # Create clone
    cloned_project = Project(
        owner_id=current_user.id,
        name=f"Copy of {project.name}",
        description=project.description,
        department=project.department,
        business_unit=project.business_unit,
        priority=project.priority,
        start_date=project.start_date,
        end_date=project.end_date,
        status="DRAFT",
        tags=project.tags,
        session_id=session_id,
        data=project.data,
        summary=project.summary,
        structured_state=project.structured_state,
        locked=False
    )
    db.add(cloned_project)
    db.commit()
    db.refresh(cloned_project)
    
    # Copy members
    original_members = db.query(ProjectMember).filter(ProjectMember.project_id == project_id).all()
    has_creator = False
    for m in original_members:
        if m.user_id == current_user.id:
            has_creator = True
        new_m = ProjectMember(
            project_id=cloned_project.id,
            user_id=m.user_id,
            role=m.role
        )
        db.add(new_m)
        
    if not has_creator:
        creator_m = ProjectMember(
            project_id=cloned_project.id,
            user_id=current_user.id,
            role=ProjectMemberRole.PROJECT_MANAGER
        )
        db.add(creator_m)
        
    db.commit()
    
    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="project cloned",
        project_id=cloned_project.id,
        metadata={
            "cloned_from_id": project_id,
            "cloned_by": current_user.email
        }
    )
    return {"status": "ok", "message": "Project cloned successfully.", "project_id": cloned_project.id}

class TeamCreate(BaseModel):
    name: str
    manager_id: int | None = None

class TeamUpdate(BaseModel):
    name: str
    manager_id: int | None = None

class TeamMembersAssign(BaseModel):
    user_ids: list[int]

class TeamProjectsAssign(BaseModel):
    project_ids: list[int]

@router.get("/teams")
def list_admin_teams(
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    teams = db.query(Team).all()
    result = []
    for t in teams:
        members_count = db.query(User).filter(User.team_id == t.id).count()
        projects_count = db.query(TeamProject).filter(TeamProject.team_id == t.id).count()
        manager_name = "None"
        if t.manager:
            manager_name = t.manager.name
        result.append({
            "id": t.id,
            "name": t.name,
            "manager_id": t.manager_id,
            "manager_name": manager_name,
            "members_count": members_count,
            "projects_count": projects_count,
            "created_at": t.created_at.isoformat()
        })
    return result

@router.post("/teams")
def create_admin_team(
    payload: TeamCreate,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    if payload.manager_id:
        mgr = db.query(User).filter(User.id == payload.manager_id).first()
        if not mgr:
            raise HTTPException(status_code=404, detail="Manager user not found")
            
    existing = db.query(Team).filter(Team.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Team name already exists")
        
    db_team = Team(
        name=payload.name,
        manager_id=payload.manager_id
    )
    db.add(db_team)
    db.commit()
    db.refresh(db_team)
    
    if payload.manager_id:
        mgr = db.query(User).filter(User.id == payload.manager_id).first()
        mgr.team_id = db_team.id
        db.commit()
        
    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="team created",
        metadata={"team_id": db_team.id, "team_name": db_team.name}
    )
    return {"status": "ok", "message": "Team created successfully.", "team_id": db_team.id}

@router.put("/teams/{team_id}")
def update_admin_team(
    team_id: int,
    payload: TeamUpdate,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
        
    if payload.manager_id:
        mgr = db.query(User).filter(User.id == payload.manager_id).first()
        if not mgr:
            raise HTTPException(status_code=404, detail="Manager user not found")
            
    existing = db.query(Team).filter(Team.name == payload.name, Team.id != team_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Team name already exists")
        
    team.name = payload.name
    team.manager_id = payload.manager_id
    db.commit()
    
    if payload.manager_id:
        mgr = db.query(User).filter(User.id == payload.manager_id).first()
        mgr.team_id = team_id
        db.commit()
        
    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="team updated",
        metadata={"team_id": team.id, "team_name": team.name}
    )
    return {"status": "ok", "message": "Team updated successfully."}

@router.delete("/teams/{team_id}")
def delete_admin_team(
    team_id: int,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
        
    db.query(User).filter(User.team_id == team_id).update({User.team_id: None})
    db.query(TeamProject).filter(TeamProject.team_id == team_id).delete()
    
    db.delete(team)
    db.commit()
    
    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="team deleted",
        metadata={"deleted_team_id": team_id}
    )
    return {"status": "ok", "message": "Team deleted successfully."}

@router.post("/teams/{team_id}/members")
def assign_admin_team_members(
    team_id: int,
    payload: TeamMembersAssign,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
        
    db.query(User).filter(User.team_id == team_id).update({User.team_id: None})
    
    for uid in payload.user_ids:
        usr = db.query(User).filter(User.id == uid).first()
        if usr:
            usr.team_id = team_id
            
    if team.manager_id:
        mgr = db.query(User).filter(User.id == team.manager_id).first()
        if mgr:
            mgr.team_id = team_id
            
    db.commit()
    
    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="team members assigned",
        metadata={"team_id": team_id, "user_ids": payload.user_ids}
    )
    return {"status": "ok", "message": "Team members updated successfully."}

@router.post("/teams/{team_id}/projects")
def assign_admin_team_projects(
    team_id: int,
    payload: TeamProjectsAssign,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
        
    db.query(TeamProject).filter(TeamProject.team_id == team_id).delete()
    
    for pid in payload.project_ids:
        proj = db.query(Project).filter(Project.id == pid).first()
        if proj:
            link = TeamProject(team_id=team_id, project_id=pid)
            db.add(link)
            
    db.commit()
    
    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="team projects assigned",
        metadata={"team_id": team_id, "project_ids": payload.project_ids}
    )
    return {"status": "ok", "message": "Team projects updated successfully."}

@router.get("/teams/{team_id}/analytics")
def get_admin_team_analytics(
    team_id: int,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
        
    team_members = db.query(User).filter(User.team_id == team_id).all()
    members_list = [{
        "id": m.id,
        "name": m.name,
        "email": m.email,
        "role": m.role.value
    } for m in team_members]
    
    team_projects = db.query(TeamProject).filter(TeamProject.team_id == team_id).all()
    projects_list = []
    project_ids = []
    for tp in team_projects:
        if tp.project:
            projects_list.append({
                "id": tp.project.id,
                "name": tp.project.name,
                "status": tp.project.status,
                "department": tp.project.department or "—",
                "priority": tp.project.priority or "MEDIUM"
            })
            project_ids.append(tp.project.id)
            
    member_ids = [m.id for m in team_members]
    messages_count = 0
    if member_ids and project_ids:
        messages_count = db.query(Message).filter(Message.project_id.in_(project_ids)).count()
        
    activity_count = 0
    recent_activities = []
    if member_ids:
        activity_count = db.query(AuditLog).filter(AuditLog.user_id.in_(member_ids)).count()
        logs = db.query(AuditLog).filter(
            AuditLog.user_id.in_(member_ids)
        ).order_by(AuditLog.timestamp.desc()).limit(20).all()
        
        for l in logs:
            recent_activities.append({
                "id": l.id,
                "action": l.action,
                "user_email": l.user.email if l.user else "System",
                "timestamp": l.timestamp.isoformat()
            })
            
    return {
        "teamName": team.name,
        "managerName": team.manager.name if team.manager else "None",
        "members": members_list,
        "projects": projects_list,
        "messagesCount": messages_count,
        "activityCount": activity_count,
        "recentActivity": recent_activities
    }

class DiscoverySectionUpdate(BaseModel):
    prompt: str
    enabled: bool
    mandatory: bool
    question_order: int
    default_value: str | None = None
    validation_rules: str | None = None

@router.get("/discovery-sections")
def list_admin_discovery_sections(
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    sections = db.query(DiscoverySection).order_by(DiscoverySection.question_order.asc()).all()
    result = []
    for s in sections:
        result.append({
            "id": s.id,
            "section_key": s.section_key,
            "section_name": s.section_name,
            "prompt": s.prompt,
            "enabled": s.enabled,
            "mandatory": s.mandatory,
            "question_order": s.question_order,
            "default_value": s.default_value or "",
            "validation_rules": s.validation_rules or ""
        })
    return result

@router.put("/discovery-sections/{section_id}")
def update_admin_discovery_section(
    section_id: int,
    payload: DiscoverySectionUpdate,
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    section = db.query(DiscoverySection).filter(DiscoverySection.id == section_id).first()
    if not section:
        raise HTTPException(status_code=404, detail="Discovery section not found")
        
    section.prompt = payload.prompt
    section.enabled = payload.enabled
    section.mandatory = payload.mandatory
    section.question_order = payload.question_order
    section.default_value = payload.default_value
    section.validation_rules = payload.validation_rules
    db.commit()
    
    from services.audit import log_action
    log_action(
        db=db,
        user_id=current_user.id,
        action="discovery config updated",
        metadata={"section_key": section.section_key, "question_order": section.question_order}
    )
    return {"status": "ok", "message": "Discovery section configuration updated successfully."}
