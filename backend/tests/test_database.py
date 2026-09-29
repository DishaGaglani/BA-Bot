"""Database layer: relationships, cascades, constraints, defaults, message store."""
import datetime

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from database import engine
from models import (
    AuditLog,
    DiscoverySection,
    Message,
    Project,
    ProjectMember,
    ProjectMemberRole,
    Team,
    TeamProject,
    User,
    UserRole,
)
from services.audit import log_action
from services.conversation_manager import get_active_messages, get_unarchived_messages, save_message
from tests.helpers import pending_fix


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


# ------------------------------------------------------------------ relationships
class TestRelationships:
    def test_project_graph_is_navigable_in_both_directions(self, db, make_user, make_project, add_member):
        owner, guest = make_user(), make_user()
        project = make_project(owner)
        add_member(project, guest, ProjectMemberRole.CONTRIBUTOR)
        message = save_message(db, project.id, "user", "hello")
        db.expire_all()

        project = db.get(Project, project.id)
        assert project.owner.id == owner.id
        assert project in db.get(User, owner.id).owned_projects
        assert {m.user_id for m in project.members} == {owner.id, guest.id}
        assert [m.project_id for m in db.get(User, guest.id).memberships] == [project.id]
        assert [m.id for m in project.messages] == [message.id]
        assert db.get(Message, message.id).project.id == project.id

    def test_team_relationships(self, db, make_user, make_project):
        manager = make_user()
        team = Team(name="Team A", manager_id=manager.id)
        db.add(team)
        db.commit()
        member = make_user(team_id=team.id)
        project = make_project(manager)
        db.add(TeamProject(team_id=team.id, project_id=project.id))
        db.commit()
        db.expire_all()

        team = db.get(Team, team.id)
        assert team.manager.id == manager.id
        assert [u.id for u in team.members] == [member.id]
        assert [tp.project_id for tp in team.projects] == [project.id]
        assert db.get(User, member.id).team.id == team.id
        assert [tp.team_id for tp in db.get(Project, project.id).teams] == [team.id]


# ------------------------------------------------------------------ cascading deletes
class TestCascadingDeletion:
    @pytest.fixture
    def populated(self, db, make_user, make_project, add_member):
        owner, guest = make_user(), make_user()
        project = make_project(owner)
        add_member(project, guest)
        for i in range(3):
            save_message(db, project.id, "user", f"msg {i}")
        log_action(db, owner.id, "something", project_id=project.id)
        team = Team(name="T")
        db.add(team)
        db.commit()
        db.add(TeamProject(team_id=team.id, project_id=project.id))
        db.commit()
        return owner, guest, project, team

    def _counts(self, db, project_id):
        db.expire_all()
        return {
            "members": db.query(ProjectMember).filter_by(project_id=project_id).count(),
            "messages": db.query(Message).filter_by(project_id=project_id).count(),
            "audit": db.query(AuditLog).filter_by(project_id=project_id, action="something").count(),
            "team_links": db.query(TeamProject).filter_by(project_id=project_id).count(),
        }

    def test_deleting_a_project_removes_everything_that_belongs_to_it(self, db, populated):
        _, _, project, _ = populated
        assert self._counts(db, project.id) == {"members": 2, "messages": 3, "audit": 1, "team_links": 1}
        db.delete(db.get(Project, project.id))
        db.commit()
        assert db.get(Project, project.id) is None
        assert self._counts(db, project.id) == {"members": 0, "messages": 0, "audit": 0, "team_links": 0}

    def test_deleting_a_project_leaves_users_and_teams_alone(self, db, populated):
        owner, guest, project, team = populated
        db.delete(db.get(Project, project.id))
        db.commit()
        db.expire_all()
        assert db.get(User, owner.id) and db.get(User, guest.id) and db.get(Team, team.id)

    def test_delete_endpoint_cascades_and_leaves_other_projects_intact(self, client, db, auth, populated, make_project):
        owner, _, project, _ = populated
        bystander = make_project(owner, "other")
        save_message(db, bystander.id, "user", "keep me")
        assert client.delete(f"/api/projects/{project.id}", headers=auth(owner)).status_code == 200
        assert self._counts(db, project.id) == {"members": 0, "messages": 0, "audit": 0, "team_links": 0}
        assert db.query(Message).filter_by(project_id=bystander.id).count() == 1
        assert db.query(ProjectMember).filter_by(project_id=bystander.id).count() == 1

    def test_deleting_a_project_is_audited(self, client, db, auth, populated):
        owner, _, project, _ = populated
        client.delete(f"/api/projects/{project.id}", headers=auth(owner))
        assert db.query(AuditLog).filter_by(action="project deletion").count() == 1


# ------------------------------------------------------------------ constraints
class TestConstraints:
    def test_user_email_is_unique(self, db, make_user):
        existing = make_user()
        db.add(User(name="dup", email=existing.email, password_hash="x"))
        with pytest.raises(IntegrityError):
            db.commit()

    def test_project_session_id_is_unique(self, db, make_user, make_project):
        owner = make_user()
        first = make_project(owner, session_id="session-shared")
        db.add(Project(owner_id=owner.id, name="dup", session_id=first.session_id))
        with pytest.raises(IntegrityError):
            db.commit()

    def test_team_name_is_unique(self, db):
        db.add(Team(name="Same"))
        db.commit()
        db.add(Team(name="Same"))
        with pytest.raises(IntegrityError):
            db.commit()

    def test_discovery_section_key_is_unique(self, db):
        row = dict(section_key="k", section_name="n", prompt="p")
        db.add(DiscoverySection(**row))
        db.commit()
        db.add(DiscoverySection(**row))
        with pytest.raises(IntegrityError):
            db.commit()

    @pytest.mark.parametrize("model,fields", [(User, {"email": "a@b.com", "password_hash": "x"}), (Project, {"owner_id": 1})])
    def test_required_columns_are_enforced(self, db, model, fields):
        db.add(model(**fields))  # name is NOT NULL on both
        with pytest.raises(IntegrityError):
            db.commit()

    @pending_fix("issue 6", "project_members has no unique constraint on (project_id, user_id), so duplicate memberships are possible")
    def test_membership_pair_is_unique(self, db, make_user, make_project):
        owner, guest = make_user(), make_user()
        project = make_project(owner)
        db.add(ProjectMember(project_id=project.id, user_id=guest.id, role=ProjectMemberRole.VIEWER))
        db.commit()
        db.add(ProjectMember(project_id=project.id, user_id=guest.id, role=ProjectMemberRole.VIEWER))
        with pytest.raises(IntegrityError):
            db.commit()

    @pending_fix("issue 6", "foreign-key columns used by hot queries (messages.project_id, audit_logs.*) have no index")
    def test_hot_foreign_keys_are_indexed(self):
        indexed = lambda table: {c for ix in inspect(engine).get_indexes(table) for c in ix["column_names"]}
        assert "project_id" in indexed("messages")
        assert {"user_id", "project_id"} <= indexed("audit_logs")
        assert {"project_id", "user_id"} <= indexed("project_members")


# ------------------------------------------------------------------ defaults
class TestDefaults:
    def test_user_defaults(self, db):
        user = User(name="u", email="u@test.com", password_hash="x")
        db.add(user)
        db.commit()
        db.refresh(user)
        assert (user.role, user.status, user.department) == (UserRole.BUSINESS_ANALYST, "ACTIVE", "IT")
        assert abs((_now() - user.created_at).total_seconds()) < 10

    def test_project_defaults(self, db, make_user):
        owner = make_user()
        project = Project(owner_id=owner.id, name="p")
        db.add(project)
        db.commit()
        db.refresh(project)
        assert (project.status, project.locked, project.priority, project.requirements_state) == ("DRAFT", False, "MEDIUM", "{}")
        assert project.created_at == project.updated_at or abs((project.updated_at - project.created_at).total_seconds()) < 1

    def test_updated_at_advances_on_change_but_created_at_does_not(self, db, make_user, make_project):
        project = make_project(make_user())
        created, first_updated = project.created_at, project.updated_at
        project.name = "renamed"
        db.commit()
        db.refresh(project)
        assert project.created_at == created
        assert project.updated_at > first_updated

    def test_message_defaults(self, db, make_user, make_project):
        message = save_message(db, make_project(make_user()).id, "ai", "x" * 40)
        assert message.is_archived is False and message.token_count == 10  # 4 chars per token estimate


# ------------------------------------------------------------------ conversation store
class TestConversationStore:
    @pytest.fixture
    def project(self, make_user, make_project):
        return make_project(make_user())

    def _seed(self, db, project, count, archived_upto=0):
        base = _now()
        for i in range(count):
            db.add(
                Message(
                    project_id=project.id,
                    role="user" if i % 2 == 0 else "ai",
                    text=f"m{i}",
                    is_archived=i < archived_upto,
                    created_at=base + datetime.timedelta(seconds=i),
                )
            )
        db.commit()

    def test_active_messages_are_the_latest_n_in_chronological_order(self, db, project):
        self._seed(db, project, 10)
        assert [m.text for m in get_active_messages(db, project.id, limit=4)] == ["m6", "m7", "m8", "m9"]

    def test_active_messages_default_window_is_six(self, db, project):
        self._seed(db, project, 10)
        assert len(get_active_messages(db, project.id)) == 6

    def test_archived_messages_are_excluded(self, db, project):
        self._seed(db, project, 10, archived_upto=8)
        assert [m.text for m in get_active_messages(db, project.id)] == ["m8", "m9"]
        assert [m.text for m in get_unarchived_messages(db, project.id)] == ["m8", "m9"]

    def test_unarchived_returns_everything_oldest_first(self, db, project):
        self._seed(db, project, 5)
        assert [m.text for m in get_unarchived_messages(db, project.id)] == ["m0", "m1", "m2", "m3", "m4"]

    def test_messages_are_scoped_to_their_project(self, db, project, make_user, make_project):
        other = make_project(make_user())
        self._seed(db, project, 3)
        self._seed(db, other, 2)
        assert len(get_active_messages(db, project.id)) == 3
        assert len(get_active_messages(db, other.id)) == 2

    def test_empty_conversation(self, db, project):
        assert get_active_messages(db, project.id) == [] and get_unarchived_messages(db, project.id) == []


# ------------------------------------------------------------------ audit log
class TestAuditLog:
    def test_records_action_with_json_metadata(self, db, make_user):
        user = make_user()
        entry = log_action(db, user.id, "did a thing", metadata={"k": "v"})
        assert entry.id and entry.user_id == user.id and entry.action == "did a thing"
        assert entry.metadata_json == '{"k": "v"}'

    def test_metadata_is_optional(self, db):
        assert log_action(db, None, "anonymous event").metadata_json is None

    def test_failure_to_write_never_breaks_the_calling_request(self, db, monkeypatch):
        def boom():
            raise RuntimeError("disk full")

        with monkeypatch.context() as patch:
            patch.setattr(db, "commit", boom)
            log_action(db, None, "will fail")  # must not raise
        assert db.query(AuditLog).count() == 0  # and left the session usable
