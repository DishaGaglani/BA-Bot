import json
import re
import requests
from sqlalchemy.orm import Session
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import Project
from services.gap_analyzer import analyze_gaps

PREDICTION_URL = "https://forjinn.com/api/v1/prediction/249fc96e-5b62-4208-8787-0d77367e9eaf"

DEFAULT_STATE = {
    "project_name": "",
    "industry": "",
    "stakeholders": [],
    "timeline": "",
    "budget": "",
    "functional_requirements": [],
    "non_functional_requirements": [],
    "integrations": [],
    "constraints": [],
    # Additional keys for legacy compatibility
    "department": "",
    "sponsor": "",
    "business_unit": "",
    "business_problem": "",
    "business_goals": "",
    "desired_outcomes": ""
}

def get_structured_state(project: Project) -> dict:
    """Load or initialize the structured state JSON dictionary from database."""
    if not project.structured_state:
        return DEFAULT_STATE.copy()
    try:
        state = json.loads(project.structured_state)
        # Ensure all default keys are present
        merged_state = DEFAULT_STATE.copy()
        merged_state.update(state)
        return merged_state
    except Exception:
        return DEFAULT_STATE.copy()

def save_structured_state(db: Session, project: Project, state: dict):
    """Serialize and save the structured state back to database."""
    project.structured_state = json.dumps(state)
    db.commit()

def clean_json_text(text: str) -> str:
    """Clean markdown code wrappers from JSON string."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()

def extract_delta_updates(user_msg: str, ai_reply: str, current_state: dict) -> dict:
    """Call Forjinn to identify and parse any updated project values from the latest dialogue."""
    prompt = (
        "You are a precise data extraction agent. Analyze the latest user message and AI reply against the "
        "current project state, and return a JSON object containing ONLY the keys that were newly discovered "
        "or updated in this turn.\n\n"
        f"--- CURRENT PROJECT STATE ---\n{json.dumps(current_state, indent=2)}\n\n"
        f"--- LATEST EXCHANGE ---\nUser: {user_msg}\nAI: {ai_reply}\n\n"
        "Return a JSON dictionary containing only the modified keys. If no values were modified or added, return an empty dictionary {}.\n"
        "Rules:\n"
        "1. For list fields like stakeholders or functional_requirements, return the complete updated list if changes occurred.\n"
        "2. For functional_requirements, each element must be a dictionary with keys: 'title', 'priority' (High/Medium/Low), 'confidence' (float 0.0-1.0).\n"
        "3. Do not include markdown code blocks (like ```json). Respond with raw JSON text only."
    )
    
    payload = {
        "question": prompt,
        "streaming": False
    }
    
    try:
        response = requests.post(PREDICTION_URL, json=payload, timeout=45, verify=False)
        response.raise_for_status()
        res_data = response.json()
        
        extracted_text = res_data.get("text")
        if not extracted_text:
            output_obj = res_data.get("output")
            if isinstance(output_obj, dict):
                extracted_text = output_obj.get("content", "")
            elif isinstance(output_obj, str):
                extracted_text = output_obj
                
        if not extracted_text:
            return {}
            
        clean_text = clean_json_text(extracted_text)
        delta = json.loads(clean_text)
        if isinstance(delta, dict):
            return delta
    except Exception as e:
        print(f"Failed to extract delta updates: {str(e)}")
    return {}

def update_project_state(db: Session, project: Project, user_msg: str, ai_reply: str) -> dict:
    """Perform delta extraction and apply updates to project state in database."""
    state = get_structured_state(project)
    delta = extract_delta_updates(user_msg, ai_reply, state)
    
    if delta:
        print(f"Applying delta updates to project {project.id}: {list(delta.keys())}")
        state.update(delta)
        save_structured_state(db, project, state)
    else:
        print(f"No state delta detected for project {project.id}.")
        
    return state

def get_legacy_payload(project: Project) -> dict:
    """Bridge the internal structured state and messages into the frontend legacy payload format."""
    state = get_structured_state(project)
    gaps = analyze_gaps(state)
    
    # Format requirements
    reqs = []
    for r in state.get("functional_requirements", []):
        if isinstance(r, dict):
            reqs.append({
                "title": r.get("title", ""),
                "priority": r.get("priority", "Medium"),
                "confidence": r.get("confidence", 1.0)
            })
        elif isinstance(r, str):
            reqs.append({
                "title": r,
                "priority": "Medium",
                "confidence": 1.0
            })
            
    # Load messages from relationship sorted chronologically
    messages_payload = []
    if project.messages:
        messages_payload = [
            {"role": m.role, "text": m.text}
            for m in sorted(project.messages, key=lambda x: x.created_at)
        ]
    else:
        # Fallback to legacy field data
        try:
            if project.data:
                existing_data = json.loads(project.data)
                messages_payload = existing_data.get("messages", [])
        except Exception:
            pass
            
    return {
        "id": project.id,
        "owner_id": project.owner_id,
        "status": project.status,
        "sessionId": project.session_id,
        "pdfGenerated": "pdfGenerated" in state or False,
        "messages": messages_payload,
        "project": {
            "name": state.get("project_name") or project.name or "",
            "department": state.get("department") or "",
            "sponsor": state.get("sponsor") or "",
            "business_unit": state.get("business_unit") or state.get("industry") or "",
            "expected_completion": state.get("timeline") or ""
        },
        "overview": {
            "description": state.get("overview_description") or state.get("business_problem") or "",
            "stakeholders": state.get("stakeholders") or []
        },
        "discovery": {
            "business_problem": state.get("business_problem") or "",
            "business_goals": state.get("business_goals") or "",
            "desired_outcomes": state.get("desired_outcomes") or "",
            "constraints": state.get("constraints") or ""
        },
        "functional_requirements": reqs,
        "missing_fields": gaps["missing_fields"],
        "next_question": state.get("next_question") or (f"Let's discuss the next section: {gaps['current_section']}." if gaps["missing_fields"] else "Discovery is complete!")
    }
