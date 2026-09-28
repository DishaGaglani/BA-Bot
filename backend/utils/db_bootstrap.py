"""Database schema and data bootstrap, run once at app startup, replacing the old
utils/migrate.py.

Schema is owned by Alembic (backend/migrations/): every table, column, index and
constraint lives in a revision under migrations/versions/, generated with
`alembic revision --autogenerate` (see backend/README.md) and never hand-written. This
module's own job is narrower and split in two:

  1. run_schema_migrations() drives Alembic itself. A brand new database just runs the
     revisions in order. A database that predates this project's use of Alembic (its
     tables already exist, created by the old code's `Base.metadata.create_all()`, but
     there's no `alembic_version` table) is a one-time adoption case: create_all() only
     ever creates whole tables, so such a database is typically missing columns, indexes
     and constraints later revisions add. _adopt_pre_alembic_database() reconciles it —
     using plain SQLAlchemy Core, not a driver-specific module like sqlite3 — then stamps
     it at head so every later schema change goes through a real revision instead of code
     like this.

  2. ensure_seed_data() does idempotent DATA work a schema migration tool has no concept
     of: values in an old format updated to their current equivalent, de-duplicating rows
     an old code path allowed before a constraint existed to forbid them, backfilling, and
     seed/demo rows. Entirely through the SQLAlchemy ORM/Core.

Not carried over from utils/migrate.py: the ad-hoc "rename `projects` to `projects_old`,
copy rows by hand" recovery path for databases that predate the `Project.owner_id` column
(long before this app had per-project membership at all). Alembic revisions are the
supported way to evolve the schema from here on; that one-time, pre-ownership-model
recovery was never expressed as one and is dropped rather than ported.
"""
import os
import uuid

from alembic import command
from alembic.config import Config
from sqlalchemy import Index, UniqueConstraint, inspect, text

from database import SessionLocal, engine
from models import Base, DiscoverySection, Project, User, UserRole
from auth.jwt import hash_password

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _alembic_config() -> Config:
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "migrations"))
    return cfg


# Columns the pre-Alembic code added with ad-hoc `ALTER TABLE ... ADD COLUMN` statements,
# because create_all() does not retrofit a column onto a table that already exists. Only
# relevant to _adopt_pre_alembic_database(); a fresh database gets all of these from the
# baseline revision instead.
_LEGACY_COLUMNS = {
    "users": {
        "department": "VARCHAR DEFAULT 'IT'",
        "status": "VARCHAR DEFAULT 'ACTIVE'",
        "last_login": "DATETIME",
        "team_id": "INTEGER REFERENCES teams(id)",
    },
    "projects": {
        "summary": "TEXT",
        "structured_state": "TEXT",
        "forjinn_session_id": "VARCHAR",
        "requirements_state": "TEXT DEFAULT '{}'",
        "description": "TEXT",
        "department": "VARCHAR",
        "business_unit": "VARCHAR",
        "priority": "VARCHAR DEFAULT 'MEDIUM'",
        "start_date": "DATETIME",
        "end_date": "DATETIME",
        "tags": "VARCHAR",
        "locked": "BOOLEAN DEFAULT 0",
    },
    "messages": {
        "token_count": "INTEGER DEFAULT 0",
    },
}


def _adopt_pre_alembic_database() -> None:
    """No-op for a fresh database or one already tracked by Alembic. For a database that
    predates Alembic, reconciles it with what the baseline revision expects to find, then
    stamps it at head. See the module docstring for why this step exists at all.
    """
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "alembic_version" in tables or "users" not in tables:
        return

    # Tables added after this database was created (e.g. discovery_sections) don't exist
    # yet at all; create_all only ever adds whole missing tables, never touches one that's
    # already there, so this is safe to run before the column-level patching below.
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, columns in _LEGACY_COLUMNS.items():
            if table not in tables:
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl_type in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))

        if "project_members" in tables:
            # Old role names, from before PROJECT_MANAGER/CONTRIBUTOR existed.
            conn.execute(text("UPDATE project_members SET role = 'PROJECT_MANAGER' WHERE role = 'OWNER'"))
            conn.execute(text("UPDATE project_members SET role = 'CONTRIBUTOR' WHERE role = 'EDITOR'"))

            # De-duplicate before the baseline revision's unique constraint can be applied:
            # repeated /invite calls for the same (project_id, user_id) pair could have
            # inserted duplicate rows on a database old enough to predate that constraint.
            conn.execute(text("""
                DELETE FROM project_members
                WHERE id NOT IN (SELECT MIN(id) FROM project_members GROUP BY project_id, user_id)
            """))

    # create_all() only creates whole missing tables; it never retrofits an index or
    # constraint onto one that already existed before the model declared it (exactly
    # issue #6: hot foreign-key columns and the project_members unique pairing were never
    # indexed/enforced on a database old enough to predate those model changes). Every
    # index and unique constraint the models declare is taken from Base.metadata itself —
    # nothing here is a hand-written index list — and created if it's still missing.
    with engine.begin() as conn:
        for table in Base.metadata.tables.values():
            if table.name not in tables:
                continue
            for index in table.indexes:
                index.create(bind=conn, checkfirst=True)
            for constraint in table.constraints:
                if isinstance(constraint, UniqueConstraint) and constraint.name:
                    # SQLite has no ALTER TABLE ADD CONSTRAINT; a UNIQUE index enforces the
                    # same rule and is how SQLite itself represents a unique constraint.
                    Index(constraint.name, *constraint.columns, unique=True).create(bind=conn, checkfirst=True)

    # The reconciliation above brings this database's shape in line with what the
    # baseline revision creates, so mark it as already being there — running that
    # revision's own CREATE TABLE/CREATE INDEX statements against tables that already
    # exist would fail instead.
    command.stamp(_alembic_config(), "head")


def run_schema_migrations() -> None:
    """Bring the database schema up to date. Safe to call on every startup."""
    _adopt_pre_alembic_database()
    command.upgrade(_alembic_config(), "head")


def _get_or_create_user(db, name, email, password, role):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(name=name, email=email, password_hash=hash_password(password), role=role)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


_DISCOVERY_SECTIONS = [
    {
        "section_key": "project_name",
        "section_name": "Project Information",
        "prompt": "Introduce yourself as the discovery AI and ask the user to provide the Project Name, Sponsor Name, Department, and Business Unit. Try to elicit all of these details conversationally.",
        "enabled": True, "mandatory": True, "question_order": 1,
        "default_value": "My Project", "validation_rules": "Should contain a name and description.",
    },
    {
        "section_key": "industry",
        "section_name": "Business Objectives",
        "prompt": "Elicit details about the business domain, industry, and the core problems or objectives this project aims to solve.",
        "enabled": True, "mandatory": True, "question_order": 2,
        "default_value": "IT Automation", "validation_rules": "Explain the target business goal.",
    },
    {
        "section_key": "stakeholders",
        "section_name": "Stakeholders",
        "prompt": "Ask the user to identify key stakeholders, target users, sponsors, and project managers who will interact with the system.",
        "enabled": True, "mandatory": True, "question_order": 3,
        "default_value": "Internal Employees", "validation_rules": "List at least one stakeholder group.",
    },
    {
        "section_key": "functional_requirements",
        "section_name": "Functional Requirements",
        "prompt": "Ask the user to describe the primary features, workflows, capabilities, and functional requirements of the system.",
        "enabled": True, "mandatory": True, "question_order": 4,
        "default_value": "User Login, Reports Generation", "validation_rules": "Minimum 20 characters.",
    },
    {
        "section_key": "non_functional_requirements",
        "section_name": "Non Functional Requirements",
        "prompt": "Discuss non-functional aspects: performance expectations, data security guidelines, availability, or platform support.",
        "enabled": True, "mandatory": True, "question_order": 5,
        "default_value": "Secure login, fast load time < 2s", "validation_rules": "Discuss speed or security constraints.",
    },
    {
        "section_key": "integrations",
        "section_name": "Risks",
        "prompt": "Elicit potential deployment threats, security vulnerabilities, or dependencies that represent a risk to the project.",
        "enabled": True, "mandatory": True, "question_order": 6,
        "default_value": "Security compliance audits", "validation_rules": "List at least one potential project block risk.",
    },
    {
        "section_key": "timeline",
        "section_name": "Assumptions",
        "prompt": "Identify any core assumptions about technical resources, vendor dependencies, or resource availability.",
        "enabled": True, "mandatory": True, "question_order": 7,
        "default_value": "Resources will be allocated on time", "validation_rules": "State resource or stack assumptions.",
    },
    {
        "section_key": "budget",
        "section_name": "Constraints",
        "prompt": "Elicit constraints: budget limitations, hard timelines, compliance regulations, or legacy system barriers.",
        "enabled": True, "mandatory": True, "question_order": 8,
        "default_value": "Timeline limit 6 months", "validation_rules": "List budget or timeline constraint.",
    },
    {
        "section_key": "constraints",
        "section_name": "Acceptance Criteria",
        "prompt": "Discuss project criteria required for business analyst sign-off and user acceptance testing.",
        "enabled": True, "mandatory": True, "question_order": 9,
        "default_value": "All tests pass successfully", "validation_rules": "Detail validation approval workflow.",
    },
]


def ensure_seed_data() -> None:
    """Idempotent data fixes and demo/seed rows. Safe to call on every startup."""
    db = SessionLocal()
    try:
        # Backfill session_id for any legacy projects that predate it always being set at
        # creation time. Done once here (not on every GET /api/projects) so that route
        # stays read-only per RFC 9110.
        legacy_projects = db.query(Project).filter(
            (Project.session_id.is_(None)) | (Project.session_id == "")
        ).all()
        for legacy_project in legacy_projects:
            legacy_project.session_id = f"session-{uuid.uuid4()}"
        if legacy_projects:
            db.commit()
            print(f"Backfilled session_id for {len(legacy_projects)} legacy project(s).")

        print("Ensuring default system users for all roles exist...")
        for name, email, password, role in [
            ("Super Admin", "superadmin@example.com", "admin123", UserRole.SUPER_ADMIN),
            ("Admin User", "admin@example.com", "admin123", UserRole.ADMIN),
            ("Business Analyst", "ba@example.com", "ba123", UserRole.BUSINESS_ANALYST),
            ("Project Manager", "pm@example.com", "pm123", UserRole.PROJECT_MANAGER),
            ("Viewer User", "viewer@example.com", "viewer123", UserRole.VIEWER),
            ("Reviewer User", "reviewer@example.com", "reviewer123", UserRole.REVIEWER),
        ]:
            _get_or_create_user(db, name, email, password, role)
        print("Default system users check complete.")

        print("Ensuring default discovery sections exist...")
        for sec in _DISCOVERY_SECTIONS:
            if not db.query(DiscoverySection).filter(DiscoverySection.section_key == sec["section_key"]).first():
                db.add(DiscoverySection(**sec))
        db.commit()
        print("Ensuring default discovery sections complete.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_migration() -> None:
    """Entry point used by app.py at startup (kept under the old name for a one-line
    call-site change): schema first, then data."""
    run_schema_migrations()
    ensure_seed_data()


if __name__ == "__main__":
    run_migration()
