import datetime
import enum
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Enum as SqlEnum
from sqlalchemy.orm import relationship
import sys
import os

# Adjust path to import Base from database
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import Base

class UserRole(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    BUSINESS_ANALYST = "BUSINESS_ANALYST"
    PROJECT_MANAGER = "PROJECT_MANAGER"
    VIEWER = "VIEWER"
    REVIEWER = "REVIEWER"

class ProjectMemberRole(str, enum.Enum):
    PROJECT_MANAGER = "PROJECT_MANAGER"
    BUSINESS_ANALYST = "BUSINESS_ANALYST"
    CONTRIBUTOR = "CONTRIBUTOR"
    VIEWER = "VIEWER"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(SqlEnum(UserRole), default=UserRole.BUSINESS_ANALYST, nullable=False)
    department = Column(String, default="IT", nullable=True)
    status = Column(String, default="ACTIVE", nullable=True)
    last_login = Column(DateTime, default=datetime.datetime.utcnow, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # Relationships
    owned_projects = relationship("Project", back_populates="owner", cascade="all, delete-orphan")
    memberships = relationship("ProjectMember", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user")

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    status = Column(String, default="DRAFT", nullable=False)  # DRAFT, IN_REVIEW, APPROVED, REJECTED
    session_id = Column(String, unique=True, index=True, nullable=True)
    description = Column(Text, nullable=True)
    department = Column(String, nullable=True)
    business_unit = Column(String, nullable=True)
    priority = Column(String, default="MEDIUM", nullable=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    tags = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)
    data = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    structured_state = Column(Text, nullable=True)
    locked = Column(Boolean, default=False, nullable=False)

    # Relationships
    owner = relationship("User", back_populates="owned_projects")
    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="project", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="project", cascade="all, delete-orphan")

class ProjectMember(Base):
    __tablename__ = "project_members"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(SqlEnum(ProjectMemberRole), default=ProjectMemberRole.VIEWER, nullable=False)

    # Relationships
    project = relationship("Project", back_populates="members")
    user = relationship("User", back_populates="memberships")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    metadata_json = Column(Text, nullable=True)  # renamed to avoid collision with SQLAlchemy metadata object

    # Relationships
    user = relationship("User", back_populates="audit_logs")
    project = relationship("Project", back_populates="audit_logs")

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    role = Column(String, nullable=False)  # 'user' or 'ai'
    text = Column(Text, nullable=False)
    is_archived = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # Relationships
    project = relationship("Project", back_populates="messages")
