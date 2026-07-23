from sqlalchemy.orm import Session
import datetime
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import Message

def save_message(db: Session, project_id: int, role: str, text: str) -> Message:
    """Save a single conversation message in the database."""
    message = Message(
        project_id=project_id,
        role=role,
        text=text,
        is_archived=False,
        token_count=len(text) // 4,
        created_at=datetime.datetime.utcnow()
    )
    db.add(message)
    try:
        db.commit()
        db.refresh(message)
    except Exception as e:
        db.rollback()
        print(f"Error saving message: {str(e)}")
        raise e
    return message

def get_active_messages(db: Session, project_id: int, limit: int = 6) -> list[Message]:
    """Retrieve the last N non-archived messages for LLM context, sorted chronologically."""
    messages = db.query(Message).filter(
        Message.project_id == project_id,
        Message.is_archived == False
    ).order_by(Message.created_at.desc()).limit(limit).all()
    
    # Reverse to return in chronological order
    messages.reverse()
    return messages

def get_unarchived_messages(db: Session, project_id: int) -> list[Message]:
    """Retrieve all non-archived messages (e.g. to perform summarization), sorted chronologically."""
    return db.query(Message).filter(
        Message.project_id == project_id,
        Message.is_archived == False
    ).order_by(Message.created_at.asc()).all()
