from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session, joinedload
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal
from models import User, UserRole, Project, ProjectMember, ProjectMemberRole
from auth.jwt import decode_access_token
from services.audit import log_action

reusable_oauth2 = HTTPBearer()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(
    db: Session = Depends(get_db),
    token_creds: HTTPAuthorizationCredentials = Depends(reusable_oauth2)
) -> User:
    """FastAPI dependency to retrieve the currently logged-in user from the JWT token."""
    if not token_creds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials"
        )
    
    payload = decode_access_token(token_creds.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token or token expired"
        )
    
    email = payload["sub"]
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user no longer exists"
        )
    
    return user

def require_role(allowed_roles: list[UserRole]):
    """FastAPI dependency to require one of the specified User roles. Admins access everything."""
    def role_checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ) -> User:
        if current_user.role == UserRole.ADMIN or current_user.role in allowed_roles:
            return current_user
        
        # Log permission denied
        log_action(
            db=db,
            user_id=current_user.id,
            action="permission denied",
            metadata={"reason": f"Required roles {allowed_roles}, user had role {current_user.role}"}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action"
        )
    return role_checker

def require_project_access(minimum_role: ProjectMemberRole):
    """FastAPI dependency to require a minimum ProjectMemberRole for the requested project. Admins bypass."""
    def project_access_checker(
        project_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ) -> Project:
        project = db.query(Project).options(joinedload(Project.messages)).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Admin override
        if current_user.role == UserRole.ADMIN:
            return project
            
        # Check if project owner (owner always has OWNER role)
        if project.owner_id == current_user.id:
            return project
            
        # Check ProjectMember table
        member = db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == current_user.id
        ).first()
        
        if not member:
            # Log permission denied
            log_action(
                db=db,
                user_id=current_user.id,
                action="permission denied",
                project_id=project_id,
                metadata={"reason": "User is not a member of this project"}
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this project"
            )
            
        # Compare roles hierarchy
        role_hierarchy = {
            ProjectMemberRole.OWNER: 3,
            ProjectMemberRole.EDITOR: 2,
            ProjectMemberRole.VIEWER: 1
        }
        
        if role_hierarchy[member.role] < role_hierarchy[minimum_role]:
            # Log permission denied
            log_action(
                db=db,
                user_id=current_user.id,
                action="permission denied",
                project_id=project_id,
                metadata={"reason": f"Required project role {minimum_role.value}, user had {member.role.value}"}
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient project permissions"
            )
            
        return project
    return project_access_checker

def require_project_owner(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Project:
    """FastAPI dependency requiring the user to be the project owner. Admins bypass."""
    project = db.query(Project).options(joinedload(Project.messages)).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
        
    if current_user.role == UserRole.ADMIN or project.owner_id == current_user.id:
        return project
        
    # Log permission denied
    log_action(
        db=db,
        user_id=current_user.id,
        action="permission denied",
        project_id=project_id,
        metadata={"reason": "User is not the project owner"}
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only the project owner can perform this operation"
    )
