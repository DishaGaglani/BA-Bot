import json
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import Message

DEFAULT_SYSTEM_PROMPT = (
    "You are an expert Business Analyst leading a structured discovery workshop.\n"
    "Your objective is to interview the user and gather requirements. Ask only one clear, "
    "concise question at a time to gather the needed information for the current focus section.\n"
    "Guidelines:\n"
    "1. Do not ask questions about sections that are already completed.\n"
    "2. If the user wanders off-topic, gently guide them back to the active section.\n"
    "3. Keep your questions and responses brief and highly conversational."
)

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
            
    # Include draft values for uncompleted fields if they have partial text
    state_context_lines.append(f"\nActive Focus Section: {current_section}")
    state_context_lines.append("Current Focus Details:")
    
    # Only list the active/focused key values to keep token usage minimal
    focus_keys_map = {
        "Project Name": ["project_name", "department", "sponsor", "business_unit"],
        "Business Domain": ["industry", "business_problem"],
        "Stakeholders": ["stakeholders", "sponsor"],
        "Project Timeline": ["timeline"],
        "Project Budget": ["budget"],
        "Functional Requirements": ["functional_requirements", "business_goals"],
        "Non-Functional Requirements": ["non_functional_requirements", "constraints"],
        "System Integrations": ["integrations"],
        "Constraints & Risks": ["constraints"]
    }
    
    active_keys = focus_keys_map.get(current_section, [])
    for k in active_keys:
        val = state.get(k)
        if val:
            state_context_lines.append(f"- {k}: {json.dumps(val)}")
            
    state_context = "\n".join(state_context_lines)
    
    # 2. Format running summary if present
    summary_context = ""
    if summary:
        summary_context = f"\n--- RUNNING INTERVIEW SUMMARY ---\n{summary}\n"
        
    # 3. Format active message history window (last 5-8 messages)
    history_lines = []
    if active_history:
        history_lines.append("\n--- ACTIVE CONVERSATION WINDOW ---")
        for msg in active_history:
            sender = "User" if msg.role == "user" else "AI"
            history_lines.append(f"{sender}: {msg.text}")
    history_context = "\n".join(history_lines)
    
    # 4. Assemble the final unified prompt
    prompt = (
        f"{DEFAULT_SYSTEM_PROMPT}\n\n"
        f"{state_context}\n"
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
