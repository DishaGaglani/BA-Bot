import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import User, UserRole, AuditLog
from dependencies.auth import get_current_user, get_db, require_role

router = APIRouter(prefix="/api/admin", tags=["admin"])

class UserRoleUpdate(BaseModel):
    role: UserRole

class UserCreateRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: UserRole

@router.get("/users")
def get_users(
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    users = db.query(User).all()
    return [{
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "role": u.role,
        "created_at": u.created_at.isoformat() if u.created_at else None
    } for u in users]

@router.put("/users/{user_id}/role")
def update_user_role(
    user_id: int,
    payload: UserRoleUpdate,
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Do not allow admin to downgrade themselves (safety check)
    if user.id == current_user.id and payload.role != UserRole.ADMIN:
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
    current_user: User = Depends(require_role([UserRole.ADMIN])),
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
        role=payload.role
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
            "role": new_user.role.value
        }
    )
    return {"status": "ok", "user_id": new_user.id}

@router.get("/audit-logs")
def get_audit_logs(
    current_user: User = Depends(require_role([UserRole.ADMIN])),
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
