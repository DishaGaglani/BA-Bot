import sqlite3
import json
import sys
import os

# Set up paths so we can import from database and models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import engine, SessionLocal
from models import Base, User, UserRole, Project, ProjectMember, ProjectMemberRole
from auth.jwt import hash_password

def get_or_create_user(db, name, email, password, role):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        pwd_hash = hash_password(password)
        user = User(
            name=name,
            email=email,
            password_hash=pwd_hash,
            role=role
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

def run_migration():
    db_path = "/Users/dishagaglani/Desktop/L&T PES/BA_BOT/ba-agent/backend/ba_bot.db"
    
    needs_migration = False
    rename_needed = False
    
    # 1. Check if database exists and inspect schema of the projects table
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if table 'projects' exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='projects';")
        has_projects = cursor.fetchone()
        
        # Check if table 'projects_old' exists (due to a previous failed run)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='projects_old';")
        has_projects_old = cursor.fetchone()
        
        if has_projects_old:
            needs_migration = True
            rename_needed = False
        elif has_projects:
            # Check columns in projects
            cursor.execute("PRAGMA table_info(projects);")
            columns = [col[1] for col in cursor.fetchall()]
            # If owner_id is missing, we need migration
            if "owner_id" not in columns:
                needs_migration = True
                rename_needed = True
                
        conn.close()
    else:
        needs_migration = False

    db = SessionLocal()
    try:
        # If migration is needed:
        if needs_migration:
            print("Detected old projects table schema. Starting database migration...")
            
            # Connect directly via sqlite3 to rename old projects table and drop index
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            if rename_needed:
                cursor.execute("ALTER TABLE projects RENAME TO projects_old;")
            cursor.execute("DROP INDEX IF EXISTS ix_projects_id;")
            conn.commit()
            conn.close()
            
            # Create all new tables using SQLAlchemy
            Base.metadata.create_all(bind=engine)
            
            # Seed/get the default admin user
            admin_user = get_or_create_user(db, "System Administrator", "admin@example.com", "admin123", UserRole.ADMIN)
            admin_user_id = admin_user.id
            
            # Query and migrate the old projects
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT id, data FROM projects_old;")
            old_projects = cursor.fetchall()
            conn.close()
            
            print(f"Migrating {len(old_projects)} project records...")
            for old_id, data_str in old_projects:
                name = f"Project {old_id}"
                session_id = None
                
                try:
                    data_dict = json.loads(data_str)
                    session_id = data_dict.get("sessionId")
                    project_info = data_dict.get("project", {})
                    if project_info and project_info.get("name"):
                        name = project_info.get("name")
                except Exception as e:
                    print(f"Failed to parse old project data for id {old_id}: {str(e)}")
                
                # Check if project already exists in new table to prevent duplicates
                existing_project = db.query(Project).filter(Project.id == old_id).first()
                if not existing_project:
                    # Insert project
                    new_project = Project(
                        id=old_id,
                        owner_id=admin_user_id,
                        name=name,
                        status="DRAFT",
                        session_id=session_id,
                        data=data_str
                    )
                    db.add(new_project)
                    
                    # Insert ProjectMember PROJECT_MANAGER
                    member = ProjectMember(
                        project_id=old_id,
                        user_id=admin_user_id,
                        role=ProjectMemberRole.PROJECT_MANAGER
                    )
                    db.add(member)
            
            db.commit()
            
            # Clean up: Drop old table
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("DROP TABLE projects_old;")
            conn.commit()
            conn.close()
            print("Database migration completed successfully!")
            
        else:
            # Table is either new or already migrated. Run metadata create_all.
            print("Initializing database schema...")
            Base.metadata.create_all(bind=engine)
            
        # Ensure new columns exist in projects and users
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Add new project and user columns
            for table, col, col_def in [
                ("projects", "summary", "TEXT"),
                ("projects", "structured_state", "TEXT"),
                ("projects", "description", "TEXT"),
                ("projects", "department", "TEXT"),
                ("projects", "business_unit", "TEXT"),
                ("projects", "priority", "TEXT DEFAULT 'MEDIUM'"),
                ("projects", "start_date", "TEXT"),
                ("projects", "end_date", "TEXT"),
                ("projects", "tags", "TEXT"),
                ("users", "department", "TEXT DEFAULT 'IT'"),
                ("users", "status", "TEXT DEFAULT 'ACTIVE'"),
                ("users", "last_login", "TEXT")
            ]:
                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def};")
                    print(f"Added column '{col}' to {table} table.")
                except sqlite3.OperationalError:
                    pass

            # Update existing roles in project_members table
            try:
                cursor.execute("UPDATE project_members SET role = 'PROJECT_MANAGER' WHERE role = 'OWNER';")
                cursor.execute("UPDATE project_members SET role = 'CONTRIBUTOR' WHERE role = 'EDITOR';")
                print("Migrated old project membership roles ('OWNER' -> 'PROJECT_MANAGER', 'EDITOR' -> 'CONTRIBUTOR') in database.")
            except sqlite3.OperationalError as e:
                print(f"Warning during member role migration: {str(e)}")

            conn.commit()
            conn.close()
            
        # Seed test users
        print("Ensuring default system users for all roles exist...")
        users_to_seed = [
            ("Super Admin", "superadmin@example.com", "admin123", UserRole.SUPER_ADMIN),
            ("Admin User", "admin@example.com", "admin123", UserRole.ADMIN),
            ("Business Analyst", "ba@example.com", "ba123", UserRole.BUSINESS_ANALYST),
            ("Project Manager", "pm@example.com", "pm123", UserRole.PROJECT_MANAGER),
            ("Viewer User", "viewer@example.com", "viewer123", UserRole.VIEWER),
            ("Reviewer User", "reviewer@example.com", "reviewer123", UserRole.REVIEWER)
        ]
        for name, email, password, role in users_to_seed:
            get_or_create_user(db, name, email, password, role)
        print("Default system users check complete.")

    except Exception as e:
        print(f"Error during migration: {str(e)}")
        db.rollback()
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    run_migration()
