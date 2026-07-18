import requests
from sqlalchemy.orm import Session
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import Project, Message
from services.conversation_manager import get_unarchived_messages

PREDICTION_URL = "https://forjinn.com/api/v1/prediction/249fc96e-5b62-4208-8787-0d77367e9eaf"

def check_and_summarize(db: Session, project: Project) -> bool:
    """
    Check if the active conversation has 15 or more non-archived messages.
    If so, call Forjinn to merge them into a rolling summary and archive the messages.
    """
    unarchived = get_unarchived_messages(db, project.id)
    
    # We only summarize if we have 15 or more active messages
    if len(unarchived) < 15:
        return False
        
    print(f"Triggering rolling summarization for project {project.id} ({len(unarchived)} active messages)...")
    
    # Format messages for the summarization prompt
    chat_lines = []
    for msg in unarchived:
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
        response = requests.post(PREDICTION_URL, json=payload, timeout=90, verify=False)
        response.raise_for_status()
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
            return False
            
        # Update project summary in DB
        project.summary = summary_text.strip()
        
        # Archive the messages that were summarized
        for msg in unarchived:
            msg.is_archived = True
            
        db.commit()
        print(f"Rolling summarization complete for project {project.id}.")
        return True
        
    except Exception as e:
        print(f"Failed to perform auto-summarization: {str(e)}")
        db.rollback()
        return False
