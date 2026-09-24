import requests
from sqlalchemy.orm import Session
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import Project, Message
from services.conversation_manager import get_unarchived_messages

PREDICTION_URL = os.getenv("PREDICTION_URL", "https://172.16.34.7:3000/api/v1/prediction/09ee3d2d-5d65-4793-a217-abd65e837366")

SUMMARY_THRESHOLD = 10  # unarchived messages before older ones are folded into the summary


def needs_summarization(db: Session, project_id: int) -> bool:
    """Cheap check used by the request path to decide whether to enqueue a summarize job."""
    return len(get_unarchived_messages(db, project_id)) >= SUMMARY_THRESHOLD


def check_and_summarize(db: Session, project: Project, raise_on_error: bool = False) -> bool:
    """
    Check if the active conversation has 10 or more non-archived messages.
    If so, call Forjinn to merge the older messages (older than the last 5)
    into the rolling summary and archive them.

    Safe to call repeatedly: the summary update and the archiving happen in one
    transaction, and once messages are archived the threshold check is a no-op.
    With raise_on_error=True failures are re-raised (after rollback) instead of
    swallowed, so the job queue can retry them.
    """
    unarchived = get_unarchived_messages(db, project.id)
    
    # We only summarize if we have 10 or more active messages
    if len(unarchived) < SUMMARY_THRESHOLD:
        return False
        
    # We keep the last 5 messages active/raw, and summarize the rest
    messages_to_summarize = unarchived[:-5]
    
    print(f"Triggering rolling summarization for project {project.id} ({len(messages_to_summarize)} older messages)...")
    
    # Format messages for the summarization prompt
    chat_lines = []
    for msg in messages_to_summarize:
        sender = "User" if msg.role == "user" else "AI"
        chat_lines.append(f"{sender}: {msg.text}")
    chat_text = "\n".join(chat_lines)
    
    old_summary = project.summary or "No summary exists yet."
    
    summary_prompt = (
        "You are an expert Business Analyst. Please compile an updated, unified summary of the project requirements "
        "and details captured during the interview workshop so far.\n\n"
        f"--- PREVIOUS RUNNING SUMMARY ---\n{old_summary}\n\n"
        f"--- NEW CONVERSATION MESSAGES ---\n{chat_text}\n\n"
        "Generate a fresh, unified, and cohesive requirements summary incorporating all information from the previous "
        "summary and the new messages. Do not lose functional requirements or constraints details. Keep it professional, structured, and clear."
    )
    
    payload = {
        "question": summary_prompt,
        "streaming": False
    }
    
    try:
        from utils.prod_ready import request_with_retry
        response = request_with_retry("POST", PREDICTION_URL, json=payload, timeout=90, verify=False)
        res_data = response.json()
        
        summary_text = res_data.get("text")
        if not summary_text:
            output_obj = res_data.get("output")
            if isinstance(output_obj, dict):
                summary_text = output_obj.get("content", "")
            elif isinstance(output_obj, str):
                summary_text = output_obj
                
        if not summary_text:
            print("Warning: Summarization service returned empty text.")
            if raise_on_error:
                raise RuntimeError("Summarization service returned empty text")
            return False
            
        # Update project summary in DB
        project.summary = summary_text.strip()
        
        # Archive only the messages that were summarized
        for msg in messages_to_summarize:
            msg.is_archived = True
            
        db.commit()
        print(f"Rolling summarization complete for project {project.id}. Archived {len(messages_to_summarize)} messages.")
        return True
        
    except Exception as e:
        print(f"Failed to perform auto-summarization: {str(e)}")
        db.rollback()
        if raise_on_error:
            raise
        return False
