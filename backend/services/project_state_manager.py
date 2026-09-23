import json
import re
import requests
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy.orm import Session
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import Project
from services.gap_analyzer import analyze_gaps
from utils.prod_ready import request_with_retry

PREDICTION_URL = os.getenv("PREDICTION_URL", "https://172.16.34.7:3000/api/v1/prediction/09ee3d2d-5d65-4793-a217-abd65e837366")

DEFAULT_STATE = {
    # Project Info
    "project_name": "",
    "industry": "",
    "department": "",
    "sponsor": "",
    "business_unit": "",
    "timeline": "",
    "budget": "",
    
    # Core Requirements State
    "business_requirements": [],
    "functional_requirements": [],
    "non_functional_requirements": [],
    "stakeholders": [],
    "constraints": [],
    "assumptions": [],
    "risks": [],
    "integrations": [],
    "user_roles": [],
    
    # Metadata and chatbot tracker
    "asked_questions": [],
    "pending_questions": [],
    "completed_sections": [],
    "generated_summaries": "",
    "next_question": ""
}

def get_structured_state(project: Project) -> dict:
    """Load or initialize the structured state JSON dictionary from database."""
    if not project.structured_state:
        return DEFAULT_STATE.copy()
    try:
        state = json.loads(project.structured_state)
        merged_state = DEFAULT_STATE.copy()
        merged_state.update(state)
        return merged_state
    except Exception:
        return DEFAULT_STATE.copy()

def save_structured_state(db: Session, project: Project, state: dict):
    """Serialize and save the structured state back to database."""
    project.structured_state = json.dumps(state)
    db.commit()

_LIST_OF_STRINGS_FIELDS = {
    "business_requirements", "non_functional_requirements", "stakeholders",
    "constraints", "assumptions", "risks", "integrations", "user_roles",
}


class FunctionalRequirementDelta(BaseModel):
    title: str = ""
    priority: str = "Medium"
    confidence: float = 1.0

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data):
        # The LLM sometimes returns a bare string instead of the {title, priority,
        # confidence} object the prompt asks for; treat it as just the title.
        if isinstance(data, str):
            return {"title": data}
        if not isinstance(data, dict):
            return {}
        return data


class ProjectStateDelta(BaseModel):
    """Schema for the per-turn delta the LLM returns. Only fields the interview
    is actually meant to extract are declared here; anything else (including
    internally-managed bookkeeping keys like completed_sections, which
    update_project_state derives itself) is dropped rather than merged in."""
    model_config = ConfigDict(extra="ignore")

    project_name: str | None = None
    industry: str | None = None
    department: str | None = None
    sponsor: str | None = None
    business_unit: str | None = None
    timeline: str | None = None
    budget: str | None = None
    business_requirements: list[str] | None = None
    functional_requirements: list[FunctionalRequirementDelta] | None = None
    non_functional_requirements: list[str] | None = None
    stakeholders: list[str] | None = None
    constraints: list[str] | None = None
    assumptions: list[str] | None = None
    risks: list[str] | None = None
    integrations: list[str] | None = None
    user_roles: list[str] | None = None
    generated_summaries: str | None = None
    next_question: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_types(cls, data):
        """LLM output is untrusted, text-derived JSON: it frequently returns a
        bare string where a list was expected (or vice versa). Coerce each
        field into its expected shape instead of letting one malformed field
        reject the entire delta and lose everything else the model extracted."""
        if not isinstance(data, dict):
            return {}
        coerced = {}
        for key, value in data.items():
            if key not in cls.model_fields:
                continue  # hallucinated/unknown key -> dropped
            if key in _LIST_OF_STRINGS_FIELDS:
                if isinstance(value, list):
                    coerced[key] = [str(v) for v in value]
                elif value not in (None, ""):
                    coerced[key] = [str(value)]
            elif key == "functional_requirements":
                if isinstance(value, list):
                    coerced[key] = value
                elif value not in (None, ""):
                    coerced[key] = [value]
            else:
                # Plain string-typed field
                if isinstance(value, list):
                    coerced[key] = ", ".join(str(v) for v in value)
                elif isinstance(value, dict):
                    coerced[key] = json.dumps(value)
                elif value is not None:
                    coerced[key] = str(value)
        return coerced


def clean_json_text(text: str) -> str:
    """Clean markdown code wrappers from JSON string."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()

def extract_delta_updates(user_msg: str, ai_reply: str, current_state: dict, active_section: str = None) -> dict:
    """Call Forjinn to identify and parse any updated project values from the latest dialogue."""
    prompt = (
        "You are a precise data extraction agent. Analyze the latest user message and AI reply against the "
        "current project state, and return a JSON object containing ONLY the keys that were newly discovered "
        "or updated in this turn.\n\n"
        f"The user is currently answering questions for the requirement stage: '{active_section or 'General'}'. Focus updates on this section.\n\n"
        f"--- CURRENT PROJECT STATE ---\n{json.dumps(current_state, indent=2)}\n\n"
        f"--- LATEST EXCHANGE ---\nUser: {user_msg}\nAI: {ai_reply}\n\n"
        "Return a JSON dictionary containing only the modified keys. If no values were modified or added, return an empty dictionary {}.\n"
        "Rules:\n"
        "1. For list fields (like functional_requirements, non_functional_requirements, assumptions, risks), return the complete updated list if changes occurred.\n"
        "2. For functional_requirements, each element must be a dictionary with keys: 'title', 'priority' (High/Medium/Low), 'confidence' (float 0.0-1.0).\n"
        "3. Do not include markdown code blocks. Respond with raw JSON text only."
    )
    
    payload = {
        "question": prompt,
        "streaming": False
    }
    
    try:
        response = request_with_retry("POST", PREDICTION_URL, json=payload, timeout=45, verify=False)
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
        raw_delta = json.loads(clean_text)
        if isinstance(raw_delta, dict):
            validated = ProjectStateDelta.model_validate(raw_delta)
            return validated.model_dump(exclude_none=True)
    except Exception as e:
        print(f"Failed to extract delta updates: {str(e)}")
    return {}

def update_project_state(db: Session, project: Project, user_msg: str, ai_reply: str, active_section: str = None) -> dict:
    """Perform delta extraction and apply updates to project state in database."""
    state = get_structured_state(project)
    delta = extract_delta_updates(user_msg, ai_reply, state, active_section)
    
    # Extract questions asked in the AI reply
    questions = re.findall(r'([^.!?]*\?)', ai_reply)
    for q in questions:
        q_clean = q.strip()
        if q_clean and q_clean not in state.setdefault("asked_questions", []):
            state["asked_questions"].append(q_clean)

    if delta:
        print(f"Applying delta updates to project {project.id}: {list(delta.keys())}")
        state.update(delta)
        
        # Track completed sections in state
        gaps = analyze_gaps(state)
        state["completed_sections"] = gaps.get("completed_fields", [])
        
        # Generate cohesive summaries from state
        summary_lines = []
        if state.get("project_name"):
            summary_lines.append(f"Project Name: {state.get('project_name')}")
        if state.get("functional_requirements"):
            titles = [r.get("title") if isinstance(r, dict) else str(r) for r in state.get("functional_requirements")]
            summary_lines.append(f"Functional Reqs: {', '.join(titles)}")
        if state.get("non_functional_requirements"):
            summary_lines.append(f"Non-Functional: {', '.join(state.get('non_functional_requirements'))}")
        if state.get("risks"):
            summary_lines.append(f"Risks: {', '.join(state.get('risks'))}")
            
        state["generated_summaries"] = " | ".join(summary_lines)
        
    save_structured_state(db, project, state)
    return state

def get_legacy_payload(project: Project) -> dict:
    """Bridge the internal structured state and messages into the frontend legacy payload format."""
    state = get_structured_state(project)
    gaps = analyze_gaps(state)
    
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
            
    messages_payload = []
    if project.messages:
        messages_payload = [
            {"role": m.role, "text": m.text}
            for m in sorted(project.messages, key=lambda x: x.created_at)
        ]
    else:
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
            "description": state.get("business_requirements") or state.get("business_problem") or "",
            "stakeholders": state.get("stakeholders") or []
        },
        "discovery": {
            "business_problem": state.get("business_requirements") or "",
            "business_goals": state.get("industry") or "",
            "desired_outcomes": state.get("generated_summaries") or "",
            "constraints": state.get("constraints") or [],
            "budget": state.get("budget") or "",
            "integrations": state.get("integrations") or [],
            "non_functional_requirements": state.get("non_functional_requirements") or []
        },
        "functional_requirements": reqs,
        "missing_fields": gaps["missing_fields"],
        "next_question": state.get("next_question") or (f"Let's discuss the next section: {gaps['current_section']}." if gaps["missing_fields"] else "Discovery is complete!")
    }
