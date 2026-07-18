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
                    
                    # Insert ProjectMember OWNER
                    member = ProjectMember(
                        project_id=old_id,
                        user_id=admin_user_id,
                        role=ProjectMemberRole.OWNER
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
            
        # Ensure new columns exist in projects
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            try:
                cursor.execute("ALTER TABLE projects ADD COLUMN summary TEXT;")
                print("Added column 'summary' to projects table.")
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute("ALTER TABLE projects ADD COLUMN structured_state TEXT;")
                print("Added column 'structured_state' to projects table.")
            except sqlite3.OperationalError:
                pass
            conn.commit()
            conn.close()
            
        # Seed test users
        print("Ensuring default system users for all roles exist...")
        users_to_seed = [
            ("Admin User", "admin@example.com", "admin123", UserRole.ADMIN),
            ("Business Analyst", "ba@example.com", "ba123", UserRole.BUSINESS_ANALYST),
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
