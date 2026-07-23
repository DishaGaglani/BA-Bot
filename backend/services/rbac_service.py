import os
import json

# Path to the permissions matrix JSON file
PERMISSIONS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "role_permissions.json")

# Define the standard roles and the set of available permissions
ALL_PERMISSIONS = [
    "Create Project",
    "Delete Project",
    "Edit Project",
    "Generate Document",
    "Manage Users",
    "Manage Prompts",
    "Manage AI",
    "View Analytics"
]

DEFAULT_MATRIX = {
    "SUPER_ADMIN": {p: True for p in ALL_PERMISSIONS},
    "ADMIN": {p: True for p in ALL_PERMISSIONS},
    "BUSINESS_ANALYST": {
        "Create Project": True,
        "Delete Project": False,
        "Edit Project": True,
        "Generate Document": True,
        "Manage Users": False,
        "Manage Prompts": False,
        "Manage AI": False,
        "View Analytics": True
    },
    "PROJECT_MANAGER": {
        "Create Project": True,
        "Delete Project": True,
        "Edit Project": True,
        "Generate Document": True,
        "Manage Users": False,
        "Manage Prompts": False,
        "Manage AI": False,
        "View Analytics": True
    },
    "VIEWER": {
        "Create Project": False,
        "Delete Project": False,
        "Edit Project": False,
        "Generate Document": False,
        "Manage Users": False,
        "Manage Prompts": False,
        "Manage AI": False,
        "View Analytics": True
    },
    "REVIEWER": {
        "Create Project": False,
        "Delete Project": False,
        "Edit Project": True,
        "Generate Document": True,
        "Manage Users": False,
        "Manage Prompts": False,
        "Manage AI": False,
        "View Analytics": True
    }
}

def get_role_permissions_matrix() -> dict:
    """
    Load permissions matrix from local JSON file or return default.
    
    # TODO: Migrate this logic to a relational database table (e.g., RolePermission mapping table)
    # for cleaner transaction handling and multi-instance API deployments.
    """
    if not os.path.exists(PERMISSIONS_FILE):
        try:
            with open(PERMISSIONS_FILE, "w") as f:
                json.dump(DEFAULT_MATRIX, f, indent=2)
            return DEFAULT_MATRIX
        except Exception as e:
            print(f"Failed to create default role_permissions.json: {str(e)}")
            return DEFAULT_MATRIX
            
    try:
        with open(PERMISSIONS_FILE, "r") as f:
            matrix = json.load(f)
            # Ensure any missing roles or permissions are backfilled with defaults
            for role, perms in DEFAULT_MATRIX.items():
                if role not in matrix:
                    matrix[role] = perms
                else:
                    for p in ALL_PERMISSIONS:
                        if p not in matrix[role]:
                            matrix[role][p] = perms.get(p, False)
            return matrix
    except Exception as e:
        print(f"Error loading role permissions matrix: {str(e)}")
        return DEFAULT_MATRIX

def update_role_permissions_matrix(new_matrix: dict) -> bool:
    """
    Save the updated permissions matrix back to the JSON file.
    
    # TODO: Implement relational database storage transaction block here.
    """
    # Validate structure
    validated_matrix = {}
    for role, perms in new_matrix.items():
        validated_matrix[role] = {}
        for p in ALL_PERMISSIONS:
            validated_matrix[role][p] = bool(perms.get(p, False))
            
    try:
        with open(PERMISSIONS_FILE, "w") as f:
            json.dump(validated_matrix, f, indent=2)
        return True
    except Exception as e:
        print(f"Failed to write updated permissions to {PERMISSIONS_FILE}: {str(e)}")
        return False

def check_permission(role: str, permission: str) -> bool:
    """
    Determine if a given role possesses a specific permission.
    """
    matrix = get_role_permissions_matrix()
    role_perms = matrix.get(role, {})
    return role_perms.get(permission, False)
