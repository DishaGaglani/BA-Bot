import json
import datetime
from sqlalchemy.orm import Session
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import AuditLog

def log_action(
    db: Session,
    user_id: int | None,
    action: str,
    project_id: int | None = None,
    metadata: dict | None = None
) -> AuditLog:
    """Log an audit action to the database."""
    metadata_str = json.dumps(metadata) if metadata else None
    
    db_log = AuditLog(
        user_id=user_id,
        action=action,
        project_id=project_id,
        timestamp=datetime.datetime.utcnow(),
        metadata_json=metadata_str
    )
    db.add(db_log)
    try:
        db.commit()
        db.refresh(db_log)
    except Exception as e:
        db.rollback()
        # In case of logging failure, print or ignore, but do not block app flows
        print(f"Failed to log audit event '{action}': {str(e)}")
    return db_log
