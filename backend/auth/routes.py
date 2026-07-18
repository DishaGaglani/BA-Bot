from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal
from models import User, UserRole
from auth.jwt import hash_password, verify_password, create_access_token
from services.audit import log_action
from dependencies.auth import get_current_user, get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])

class UserRegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: UserRole = UserRole.BUSINESS_ANALYST

class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: UserRole

    class Config:
        from_attributes = True

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

@router.post("/register", response_model=UserResponse)
def register(payload: UserRegisterRequest, db: Session = Depends(get_db)):
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered"
        )
    
    # Create new user
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
            detail=f"Database error during registration: {str(e)}"
        )
    
    # Log registration in AuditLog (optional, but good practice)
    log_action(
        db=db,
        user_id=new_user.id,
        action="user registration",
        metadata={"email": new_user.email, "role": new_user.role.value}
    )
    
    return new_user

@router.post("/login", response_model=LoginResponse)
def login(payload: UserLoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        # Log failed login attempt
        log_action(
            db=db,
            user_id=user.id if user else None,
            action="permission denied",
            metadata={"reason": "Invalid credentials", "attempted_email": payload.email}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Generate token
    token_data = {"sub": user.email, "role": user.role.value, "uid": user.id}
    token = create_access_token(data=token_data)
    
    # Log successful login
    log_action(
        db=db,
        user_id=user.id,
        action="login",
        metadata={"email": user.email}
    )
    
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=user
    )

@router.post("/logout")
def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Log logout action
    log_action(
        db=db,
        user_id=current_user.id,
        action="logout",
        metadata={"email": current_user.email}
    )
    return {"status": "ok", "message": "Logged out successfully"}

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
