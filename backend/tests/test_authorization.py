"""Authorization: admin route access, BOLA/IDOR isolation, project roles, workflow."""
import re

import pytest

import app as backend_app
from models import AuditLog, Project, ProjectMember, ProjectMemberRole, UserRole
from tests.helpers import project_payload, unwrap

NON_ADMIN_ROLES = [UserRole.USER]
ADMIN_ROLES = [UserRole.ADMIN]
MISSING = 999999


def _admin_routes():
    # Walking app.routes directly used to find every APIRoute flattened onto the app, but
    # include_router now wraps each sub-router opaquely, so the OpenAPI schema (a stable,
    # public FastAPI API) is used instead of reaching into routing internals.
    found = []
    for path, operations in backend_app.app.openapi()["paths"].items():
        if not path.startswith("/api/admin"):
            continue
        for method in operations:
            if method.upper() not in ("HEAD", "OPTIONS"):
                found.append((method.upper(), path))
    return sorted(found)


ADMIN_ROUTES = _admin_routes()
ADMIN_ROUTE_IDS = [f"{m} {p}" for m, p in ADMIN_ROUTES]


def _concrete(path):
    return re.sub(r"\{[^}]+\}", str(MISSING), path)


def _call(client, method, path, headers=None, body=None):
    return client.request(method, path, headers=headers or {}, json=body if body is not None else ({} if method in ("POST", "PUT") else None))


# ------------------------------------------------------------------ /api/admin/*
class TestAdminRouteAccess:
    def test_route_table_was_discovered(self):
        # Guards the introspection itself: if it silently found nothing, every test below would pass vacuously.
        assert len(ADMIN_ROUTES) > 30

    @pytest.mark.parametrize("method,path", ADMIN_ROUTES, ids=ADMIN_ROUTE_IDS)
    def test_anonymous_gets_401(self, client, method, path):
        assert _call(client, method, _concrete(path)).status_code == 401

    @pytest.mark.parametrize("method,path", ADMIN_ROUTES, ids=ADMIN_ROUTE_IDS)
    def test_non_admin_roles_get_403(self, client, make_user, auth, method, path):
        for role in NON_ADMIN_ROLES:
            r = _call(client, method, _concrete(path), auth(make_user(role)))
            assert r.status_code == 403, f"{role.value} reached {method} {path} (got {r.status_code})"

    @pytest.mark.parametrize("path", sorted({p for m, p in ADMIN_ROUTES if m == "GET"}))
    @pytest.mark.parametrize("role", ADMIN_ROLES)
    def test_admin_roles_can_read_admin_endpoints(self, client, make_user, auth, role, path):
        r = _call(client, "GET", _concrete(path), auth(make_user(role)))
        assert r.status_code not in (401, 403), r.text
        assert r.status_code < 500, f"GET {path} crashed for an admin: {r.text[:200]}"

    def test_admin_cannot_change_own_role(self, client, make_user, auth):
        admin = make_user(UserRole.ADMIN)
        r = client.put(f"/api/admin/users/{admin.id}/role", headers=auth(admin), json={"role": "USER"})
        assert r.status_code == 400

    def test_non_admin_cannot_promote_themselves(self, client, db, make_user, auth):
        user = make_user(UserRole.USER)
        r = client.put(f"/api/admin/users/{user.id}/role", headers=auth(user), json={"role": "ADMIN"})
        assert r.status_code == 403
        db.expire_all()
        assert db.get(type(user), user.id).role == UserRole.USER

    def test_admin_can_change_another_users_role_and_it_is_audited(self, client, db, make_user, auth):
        admin, target = make_user(UserRole.ADMIN), make_user(UserRole.USER)
        r = client.put(f"/api/admin/users/{target.id}/role", headers=auth(admin), json={"role": "ADMIN"})
        assert r.status_code == 200
        db.expire_all()
        assert db.get(type(target), target.id).role == UserRole.ADMIN
        assert db.query(AuditLog).filter_by(action="user role updated").count() == 1


# ------------------------------------------------------------------ BOLA / IDOR
PROJECT_ENDPOINTS = [
    ("GET", "", None),
    ("PUT", "", "payload"),
    ("DELETE", "", None),
    ("GET", "/export?format=docx", None),
    ("GET", "/export?format=pdf", None),
    ("POST", "/publish", None),
    ("POST", "/invite", {"email": "someone@test.com", "role": "VIEWER"}),
    ("GET", "/members", None),
]
ENDPOINT_IDS = [f"{m} {s or '/'}" for m, s, _ in PROJECT_ENDPOINTS]


def _body(spec):
    return project_payload(name="HIJACKED") if spec == "payload" else spec


class TestObjectLevelIsolation:
    @pytest.fixture
    def world(self, make_user, make_project):
        owner, stranger = make_user(name="owner"), make_user(name="stranger")
        return owner, stranger, make_project(owner, "Owner's project")

    @pytest.mark.parametrize("method,suffix,body", PROJECT_ENDPOINTS, ids=ENDPOINT_IDS)
    def test_stranger_cannot_touch_someone_elses_project(self, client, auth, world, method, suffix, body):
        _, stranger, project = world
        r = client.request(method, f"/api/projects/{project.id}{suffix}", headers=auth(stranger), json=_body(body))
        assert r.status_code == 403, r.text

    @pytest.mark.parametrize("method,suffix,body", PROJECT_ENDPOINTS, ids=ENDPOINT_IDS)
    def test_anonymous_gets_401(self, client, world, method, suffix, body):
        r = client.request(method, f"/api/projects/{world[2].id}{suffix}", json=_body(body))
        assert r.status_code == 401

    @pytest.mark.parametrize("method,suffix,body", PROJECT_ENDPOINTS, ids=ENDPOINT_IDS)
    def test_missing_project_is_404(self, client, auth, world, method, suffix, body):
        r = client.request(method, f"/api/projects/{MISSING}{suffix}", headers=auth(world[0]), json=_body(body))
        assert r.status_code == 404

    def test_rejected_requests_leave_the_project_untouched(self, client, db, auth, world):
        _, stranger, project = world
        headers = auth(stranger)
        client.put(f"/api/projects/{project.id}", headers=headers, json=project_payload("HIJACKED"))
        client.post(f"/api/projects/{project.id}/publish", headers=headers)
        client.delete(f"/api/projects/{project.id}", headers=headers)
        db.expire_all()
        still_there = db.get(Project, project.id)
        assert still_there is not None
        assert still_there.name == "Owner's project" and still_there.status == "DRAFT"

    def test_stranger_cannot_chat_in_someone_elses_workspace(self, client, auth, llm, world):
        _, stranger, project = world
        by_id = client.post("/api/predict", headers=auth(stranger), json={"question": "hi", "projectId": project.id})
        by_session = client.post("/api/predict", headers=auth(stranger), json={"question": "hi", "sessionId": project.session_id})
        assert by_id.status_code == by_session.status_code == 403
        assert llm.calls == []  # never even reached the model

    def test_predict_requires_a_target_and_authentication(self, client, auth, llm, world):
        assert client.post("/api/predict", json={"question": "hi", "projectId": world[2].id}).status_code == 401
        assert client.post("/api/predict", headers=auth(world[0]), json={"question": "hi"}).status_code == 400
        assert client.post("/api/predict", headers=auth(world[0]), json={"question": "hi", "projectId": MISSING}).status_code == 404

    def test_listing_only_shows_projects_the_user_can_access(self, client, auth, make_user, make_project, add_member):
        owner, member, stranger = make_user(), make_user(), make_user()
        mine, shared, private = make_project(stranger, "mine"), make_project(owner, "shared"), make_project(owner, "private")
        add_member(shared, stranger)
        ids = {p["id"] for p in unwrap(client.get("/api/projects", headers=auth(stranger)))}
        assert ids == {mine.id, shared.id}
        assert private.id not in ids

    def test_admin_listing_sees_everything(self, client, auth, make_user, make_project):
        a, b, admin = make_user(), make_user(), make_user(UserRole.ADMIN)
        p1, p2 = make_project(a), make_project(b)
        ids = {p["id"] for p in unwrap(client.get("/api/projects", headers=auth(admin)))}
        assert {p1.id, p2.id} <= ids

    @pytest.mark.parametrize("role", ADMIN_ROLES)
    def test_admins_can_access_any_project(self, client, auth, make_user, make_project, role):
        project = make_project(make_user())
        headers = auth(make_user(role))
        assert client.get(f"/api/projects/{project.id}", headers=headers).status_code == 200
        assert client.put(f"/api/projects/{project.id}", headers=headers, json=project_payload("Renamed")).status_code == 200


# ------------------------------------------------------------------ project roles
class TestProjectRoleHierarchy:
    """VIEWER (read-only) < MEMBER (read + edit), each checked per action."""

    @pytest.fixture
    def project_with_members(self, make_user, make_project, add_member):
        owner = make_user()
        project = make_project(owner)
        members = {}
        for role in ProjectMemberRole:
            user = make_user()
            add_member(project, user, role)
            members[role] = user
        return project, members, owner

    @pytest.mark.parametrize(
        "role,can_read,can_edit",
        [
            (ProjectMemberRole.VIEWER, True, False),
            (ProjectMemberRole.MEMBER, True, True),
        ],
    )
    def test_read_and_edit_permissions(self, client, auth, project_with_members, role, can_read, can_edit):
        project, members, _ = project_with_members
        headers = auth(members[role])
        assert (client.get(f"/api/projects/{project.id}", headers=headers).status_code == 200) is can_read
        assert (client.put(f"/api/projects/{project.id}", headers=headers, json=project_payload()).status_code == 200) is can_edit

    @pytest.mark.parametrize("role", list(ProjectMemberRole))
    def test_only_the_owner_can_delete_or_invite(self, client, auth, project_with_members, role):
        project, members, _ = project_with_members
        headers = auth(members[role])
        assert client.delete(f"/api/projects/{project.id}", headers=headers).status_code == 403
        r = client.post(f"/api/projects/{project.id}/invite", headers=headers, json={"email": "x@test.com", "role": "VIEWER"})
        assert r.status_code == 403

    def test_publishing_needs_member_role(self, client, auth, project_with_members):
        project, members, _ = project_with_members
        assert client.post(f"/api/projects/{project.id}/publish", headers=auth(members[ProjectMemberRole.VIEWER])).status_code == 403
        assert client.post(f"/api/projects/{project.id}/publish", headers=auth(members[ProjectMemberRole.MEMBER])).status_code == 200


# ------------------------------------------------------------------ creation & workflow
class TestCreationAndWorkflow:
    @pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.USER])
    def test_any_account_type_can_create_projects(self, client, db, make_user, auth, role):
        # No role gate on project creation: both account types may start one.
        user = make_user(role)
        r = client.post("/api/projects", headers=auth(user), json=project_payload("Created"))
        assert r.status_code == 200
        assert db.query(Project).count() == 1

    def test_creator_becomes_owner_and_member(self, client, db, make_user, auth):
        user = make_user()
        project_id = unwrap(client.post("/api/projects", headers=auth(user), json=project_payload("Mine")))["id"]
        project = db.get(Project, project_id)
        assert project.owner_id == user.id and project.status == "DRAFT" and project.session_id
        member = db.query(ProjectMember).filter_by(project_id=project_id, user_id=user.id).one()
        assert member.role == ProjectMemberRole.MEMBER

    def test_publish_workflow_goes_straight_from_draft_to_published(self, client, db, make_user, make_project, auth):
        # No review/approval stage: any MEMBER (or the owner, or an admin) can publish directly.
        owner = make_user()
        project = make_project(owner)
        headers = auth(owner)

        assert unwrap(client.post(f"/api/projects/{project.id}/publish", headers=headers))["new_status"] == "PUBLISHED"
        assert client.post(f"/api/projects/{project.id}/publish", headers=headers).status_code == 400  # already published

        db.expire_all()
        assert db.get(Project, project.id).locked is True
        assert db.query(AuditLog).filter_by(action="project publish").count() == 1

    def test_published_project_is_locked_against_changes(self, client, db, make_user, make_project, auth, llm):
        owner = make_user()
        project = make_project(owner, status="PUBLISHED", locked=True)
        headers = auth(owner)
        assert client.put(f"/api/projects/{project.id}", headers=headers, json=project_payload("Edit")).status_code == 403
        assert client.post("/api/predict", headers=headers, json={"question": "hi", "projectId": project.id}).status_code == 403
        assert client.get(f"/api/projects/{project.id}", headers=headers).status_code == 200  # still readable
        assert llm.calls == []

    def test_admin_can_lock_and_unlock(self, client, db, make_user, make_project, auth):
        admin, owner = make_user(UserRole.ADMIN), make_user()
        project = make_project(owner)
        assert client.put(f"/api/admin/projects/{project.id}/lock", headers=auth(admin)).status_code == 200
        assert client.put(f"/api/projects/{project.id}", headers=auth(owner), json=project_payload()).status_code == 403
        assert client.put(f"/api/admin/projects/{project.id}/unlock", headers=auth(admin)).status_code == 200
        assert client.put(f"/api/projects/{project.id}", headers=auth(owner), json=project_payload()).status_code == 200


class TestInvitations:
    def test_owner_can_invite_and_reinvite_without_duplicating(self, client, db, make_user, make_project, auth):
        owner, guest = make_user(), make_user()
        project = make_project(owner)
        url = f"/api/projects/{project.id}/invite"
        assert client.post(url, headers=auth(owner), json={"email": guest.email, "role": "VIEWER"}).status_code == 200
        assert client.post(url, headers=auth(owner), json={"email": guest.email, "role": "MEMBER"}).status_code == 200
        rows = db.query(ProjectMember).filter_by(project_id=project.id, user_id=guest.id).all()
        assert len(rows) == 1 and rows[0].role == ProjectMemberRole.MEMBER

    def test_unknown_user_and_invalid_role(self, client, make_user, make_project, auth):
        owner = make_user()
        project = make_project(owner)
        url = f"/api/projects/{project.id}/invite"
        assert client.post(url, headers=auth(owner), json={"email": "ghost@test.com", "role": "VIEWER"}).status_code == 404
        assert client.post(url, headers=auth(owner), json={"email": owner.email, "role": "GOD"}).status_code == 422

    def test_invited_user_gains_exactly_the_granted_access(self, client, make_user, make_project, auth):
        owner, guest = make_user(), make_user()
        project = make_project(owner)
        assert client.get(f"/api/projects/{project.id}", headers=auth(guest)).status_code == 403
        client.post(f"/api/projects/{project.id}/invite", headers=auth(owner), json={"email": guest.email, "role": "VIEWER"})
        assert client.get(f"/api/projects/{project.id}", headers=auth(guest)).status_code == 200
        assert client.put(f"/api/projects/{project.id}", headers=auth(guest), json=project_payload()).status_code == 403

    def test_members_endpoint_lists_roles(self, client, make_user, make_project, add_member, auth):
        owner, guest = make_user(), make_user()
        project = make_project(owner)
        add_member(project, guest, ProjectMemberRole.MEMBER)
        members = {m["email"]: m["role"] for m in unwrap(client.get(f"/api/projects/{project.id}/members", headers=auth(owner)))}
        assert members == {owner.email: "MEMBER", guest.email: "MEMBER"}
