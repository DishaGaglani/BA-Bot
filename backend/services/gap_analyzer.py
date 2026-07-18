import sys
import os

def is_field_empty(val) -> bool:
    """Check if a field value in state is empty or unpopulated."""
    if val is None:
        return True
    if isinstance(val, str):
        return len(val.strip()) == 0
    if isinstance(val, list):
        return len(val) == 0
    return False

def analyze_gaps(state: dict) -> dict:
    """
    Deterministically analyze the structured state to identify missing requirements
    and select the next target interview section.
    """
    # Define sections, their checking fields, and display labels
    sections_map = [
        {"key": "project_name", "label": "Project Name", "section": "Project Name"},
        {"key": "industry", "label": "Industry & Business Domain", "section": "Business Domain"},
        {"key": "stakeholders", "label": "Stakeholders & Key Roles", "section": "Stakeholders"},
        {"key": "timeline", "label": "Timeline & Key Milestones", "section": "Project Timeline"},
        {"key": "budget", "label": "Budget & Resources", "section": "Project Budget"},
        {"key": "functional_requirements", "label": "Functional Requirements & Core Features", "section": "Functional Requirements"},
        {"key": "non_functional_requirements", "label": "Non-Functional Requirements (Security/Speed)", "section": "Non-Functional Requirements"},
        {"key": "integrations", "label": "Integrations & Third-Party Systems", "section": "System Integrations"},
        {"key": "constraints", "label": "Constraints & Business Risks", "section": "Constraints & Risks"}
    ]
    
    missing_fields = []
    completed_fields = []
    current_section = "Project Complete"
    
    found_focus = False
    for sec in sections_map:
        val = state.get(sec["key"])
        if is_field_empty(val):
            missing_fields.append(sec["label"])
            if not found_focus:
                current_section = sec["section"]
                found_focus = True
        else:
            completed_fields.append(sec["label"])
            
    # Calculate progress percentage
    total_sections = len(sections_map)
    completed_count = total_sections - len(missing_fields)
    progress_percentage = round((completed_count / total_sections) * 100)
    
    return {
        "missing_fields": missing_fields,
        "completed_fields": completed_fields,
        "current_section": current_section,
        "progress": progress_percentage
    }
