import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal
from models import DiscoverySection

# --- Predefined Section Dependency Graph ---
# Key: section_key, Value: List of required parent section_keys that must be populated first
DEPENDENCY_GRAPH = {
    "functional_requirements": ["industry"],  # Requires Business Objectives (industry)
    "non_functional_requirements": ["functional_requirements"],  # Requires Functional Reqs
    "integrations": ["functional_requirements"],  # Requires Functional Reqs
    "constraints": ["timeline", "budget"]  # Requires Timeline & Budget
}

def is_field_empty(val) -> bool:
    """Check if a field value in state is empty or unpopulated."""
    if val is None:
        return True
    if isinstance(val, str):
        return len(val.strip()) == 0
    if isinstance(val, list):
        return len(val) == 0
    return False

def analyze_gaps(state: dict, db=None) -> dict:
    """
    Deterministically analyze the structured state to identify missing requirements
    and select the next target interview section based on dynamic database orders and dependencies.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # Load enabled sections from database, ordered by question_order
        sections_config = db.query(DiscoverySection).filter(DiscoverySection.enabled == True).order_by(DiscoverySection.question_order.asc()).all()
    except Exception as e:
        print(f"Warning: Failed to fetch discovery sections from DB: {str(e)}")
        sections_config = []

    if close_db:
        db.close()

    # Reconstruct dynamic sections map
    sections_map = []
    if sections_config:
        for sec in sections_config:
            sections_map.append({
                "key": sec.section_key,
                "label": sec.section_name,
                "section": sec.section_name
            })
    else:
        # Fallback defaults if table is empty or error
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
    
    # Track completed keys for dependency verification
    completed_keys = set()
    for sec in sections_map:
        val = state.get(sec["key"])
        if not is_field_empty(val):
            completed_keys.add(sec["key"])
            completed_fields.append(sec["label"])
        else:
            missing_fields.append(sec["label"])

    # Determine focus section considering Dependency Graph & Priority (question_order)
    found_focus = False
    for sec in sections_map:
        # If already completed, skip questioning
        if sec["key"] in completed_keys:
            continue
            
        # Check dependencies
        deps = DEPENDENCY_GRAPH.get(sec["key"], [])
        deps_met = True
        for dep in deps:
            if dep not in completed_keys:
                deps_met = False
                break
                
        # If pre-requisites are met, target this section
        if deps_met and not found_focus:
            current_section = sec["section"]
            found_focus = True

    # Fallback to first unpopulated section if dependency cycles or blocks occur
    if not found_focus and missing_fields:
        for sec in sections_map:
            if sec["key"] not in completed_keys:
                current_section = sec["section"]
                break
            
    # Calculate progress percentage
    total_sections = len(sections_map)
    if total_sections == 0:
        progress_percentage = 100
    else:
        completed_count = total_sections - len(missing_fields)
        progress_percentage = round((completed_count / total_sections) * 100)
    
    return {
        "missing_fields": missing_fields,
        "completed_fields": completed_fields,
        "current_section": current_section,
        "progress": progress_percentage
    }
