import json
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import Message, DiscoverySection
from database import SessionLocal

DEFAULT_SYSTEM_PROMPT = (
    "You are an expert Business Analyst leading a structured discovery workshop.\n"
    "Your objective is to interview the user and gather requirements. Ask only one clear, "
    "concise question at a time to gather the needed information for the current focus section.\n"
    "Guidelines:\n"
    "1. Do not ask questions about sections that are already completed.\n"
    "2. If the user wanders off-topic, gently guide them back to the active section.\n"
    "3. Keep your questions and responses brief and highly conversational."
)

def get_system_prompt() -> str:
    settings_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "system_settings.json")
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r") as f:
                cfg = json.load(f)
                if "systemPrompt" in cfg and cfg["systemPrompt"]:
                    return cfg["systemPrompt"]
        except Exception:
            pass
    return DEFAULT_SYSTEM_PROMPT

def build_optimized_prompt(
    state: dict,
    gap_analysis: dict,
    summary: str | None,
    active_history: list[Message],
    current_query: str
) -> str:
    """
    Construct a token-minimized prompt detailing only the active section
    and active history, preventing context duplication.
    """
    completed = gap_analysis.get("completed_fields", [])
    current_section = gap_analysis.get("current_section", "Project Complete")
    
    # 1. State section formatting: list completed sections by name ONLY (saving tokens)
    state_context_lines = []
    state_context_lines.append("--- WORKSHOP REQUIREMENTS STATUS ---")
    
    if completed:
        state_context_lines.append("Completed Sections (Do not ask about these):")
        for field in completed:
            state_context_lines.append(f"- {field}: [COMPLETE]")
            
    state_context_lines.append(f"\nActive Focus Section: {current_section}")
    state_context_lines.append("Current Focus Details:")
    
    # Only list the active/focused key values to keep token usage minimal
    focus_keys_map = {
        "Project Information": ["project_name", "department", "sponsor", "business_unit"],
        "Business Objectives": ["industry", "business_problem"],
        "Stakeholders": ["stakeholders", "sponsor"],
        "Functional Requirements": ["functional_requirements", "business_goals"],
        "Non Functional Requirements": ["non_functional_requirements", "constraints"],
        "Risks": ["integrations"],
        "Assumptions": ["timeline"],
        "Constraints": ["budget"],
        "Acceptance Criteria": ["constraints"]
    }
    
    active_keys = focus_keys_map.get(current_section, [])
    for k in active_keys:
        val = state.get(k)
        if val:
            state_context_lines.append(f"- {k}: {json.dumps(val)}")
            
    state_context = "\n".join(state_context_lines)
    
    # Fetch active section instructions from DB
    section_instructions = ""
    db = SessionLocal()
    try:
        sec_config = db.query(DiscoverySection).filter(
            DiscoverySection.section_name == current_section,
            DiscoverySection.enabled == True
        ).first()
        if sec_config:
            section_instructions = f"\nFocus instructions for eliciting {current_section}: {sec_config.prompt}\n"
            if sec_config.default_value:
                section_instructions += f"Default value: {sec_config.default_value}\n"
            if sec_config.validation_rules:
                section_instructions += f"Enforced Validation Rules: {sec_config.validation_rules}\n"
    except Exception:
        pass
    finally:
        db.close()
        
    # 2. Format running summary if present
    summary_context = ""
    if summary:
        summary_context = f"\n--- RUNNING INTERVIEW SUMMARY ---\n{summary}\n"
        
    # 3. Format active message history window (last 5 messages)
    history_lines = []
    if active_history:
        history_lines.append("\n--- ACTIVE CONVERSATION WINDOW ---")
        for msg in active_history:
            sender = "User" if msg.role == "user" else "AI"
            history_lines.append(f"{sender}: {msg.text}")
    history_context = "\n".join(history_lines)
    
    # 4. Assemble the final unified prompt
    prompt = (
        f"{get_system_prompt()}\n\n"
        f"{state_context}\n"
        f"{section_instructions}\n"
        f"{summary_context}\n"
        f"{history_context}\n\n"
        f"--- LATEST USER MESSAGE ---\n"
        f"User: {current_query}\n\n"
        f"AI:"
    )
    
    return prompt

def estimate_tokens(text: str) -> int:
    """Helper to generate a rough token estimate (4 characters per token average)."""
    return len(text) // 4
