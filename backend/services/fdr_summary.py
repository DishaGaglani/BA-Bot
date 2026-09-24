import json
import logging
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import Project
from services.project_state_manager import clean_json_text
from utils.prod_ready import request_with_retry

logger = logging.getLogger("ba-bot")

PREDICTION_URL = os.getenv("PREDICTION_URL", "https://172.16.34.7:3000/api/v1/prediction/09ee3d2d-5d65-4793-a217-abd65e837366")

LIST_FIELD_KEYS = {
    "key_features": ("feature", "description"),
    "user_roles": ("role", "permissions"),
    "data_sources": ("data", "source", "location"),
}

# The actual runtime default — list fields start empty so a total extraction failure
# renders as a genuinely empty [MISSING] row, not a blank-but-present one.
FDR_SCHEMA = {
    "project_name": "", "department": "", "business_unit": "", "project_sponsor": "", "date": "",
    "project_description": "", "stakeholders": "",
    "business_problem": "", "business_goals": "", "desired_outcomes": "", "other_insights": "",
    "business_objectives": "", "existing_process_pain_points": "", "success_criteria_kpis": "",
    "roi_operations_impact": "", "roi_business_impact": "", "scope": "",
    "key_features": [],
    "user_roles": [],
    "performance": "", "security": "", "scalability": "",
    "platforms_devices": "", "integration": "", "data_requirements": "",
    "nature_of_data": "",
    "data_sources": [],
    "project_manager_name": "", "project_manager_date": "",
    "sponsors_names": "", "sponsors_date": "",
}

# Shown to the model so it knows the expected shape of each list item; not used as a
# runtime default (see FDR_SCHEMA above).
_SCHEMA_HINT = dict(FDR_SCHEMA, **{
    key: [{field: "" for field in fields}] for key, fields in LIST_FIELD_KEYS.items()
})


def _sanitize_list_field(value, keys) -> list:
    """Keep only well-shaped dict items so a malformed LLM response (e.g. a list of
    plain strings) can't crash the docx builder downstream."""
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value:
        if isinstance(item, dict):
            cleaned.append({k: item.get(k, "") for k in keys})
    return cleaned


def _conversation_transcript(project: Project) -> str:
    messages = sorted(project.messages, key=lambda m: m.created_at) if project.messages else []
    lines = []
    for m in messages:
        sender = "User" if m.role == "user" else "AI"
        lines.append(f"{sender}: {m.text}")
    return "\n".join(lines)


def generate_fdr_json(project: Project) -> dict:
    """Ask the conversational model to summarize the full interview into the
    Requirement Discovery Form JSON schema. Any field not discussed is left blank
    and rendered as [MISSING] by the docx builder."""
    transcript = _conversation_transcript(project)

    prompt = (
        "You are a data extraction assistant. Below is the full transcript of a Business Analyst "
        "requirement discovery interview. Summarize everything captured in the conversation into a single "
        "JSON object that exactly matches this schema (same keys, same shapes):\n\n"
        f"{json.dumps(_SCHEMA_HINT, indent=2)}\n\n"
        "Rules:\n"
        "1. Fill each field using only information actually present in the transcript.\n"
        "2. If a field was never discussed, leave it as an empty string (or empty list for key_features, "
        "user_roles, data_sources) — do not guess or invent content.\n"
        "3. key_features, user_roles, and data_sources must be lists of objects with exactly the keys shown.\n"
        "4. Respond with raw JSON only. No markdown code fences, no commentary.\n\n"
        f"--- INTERVIEW TRANSCRIPT ---\n{transcript}\n"
    )

    payload = {"question": prompt, "streaming": False}

    try:
        response = request_with_retry("POST", PREDICTION_URL, json=payload, timeout=60, verify=False)
        res_data = response.json()

        extracted_text = res_data.get("text")
        if not extracted_text:
            output_obj = res_data.get("output")
            if isinstance(output_obj, dict):
                extracted_text = output_obj.get("content", "")
            elif isinstance(output_obj, str):
                extracted_text = output_obj

        if not extracted_text:
            return dict(FDR_SCHEMA)

        parsed = json.loads(clean_json_text(extracted_text))
        merged = dict(FDR_SCHEMA)
        if isinstance(parsed, dict):
            merged.update(parsed)
        for key, fields in LIST_FIELD_KEYS.items():
            merged[key] = _sanitize_list_field(merged.get(key), fields)
        return merged
    except Exception as e:
        logger.warning(f"Failed to generate structured FDR JSON: {str(e)}")
        return dict(FDR_SCHEMA)
