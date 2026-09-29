"""Authentication: registration, login, JWT validation, password handling."""
import base64
import datetime
import io
import json
import os
import subprocess
import sys
import time
import types

import jwt as pyjwt
import pytest

import auth.routes as auth_routes
from auth.jwt import (
    ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from models import AuditLog, User, UserRole
from tests.conftest import BACKEND_DIR, DEFAULT_PASSWORD, TEST_JWT_SECRET
from tests.helpers import pending_fix, unwrap

OLD_PUBLIC_DEFAULT_SECRET = "development_secret_key_change_me_in_production"


def _register(client, **overrides):
    body = {"name": "New Person", "email": "new@test.com", "password": "S3cret!pass"}
    body.update(overrides)
    return client.post("/api/auth/register", json=body)


def _token(claims=None, secret=TEST_JWT_SECRET, expires_in=3600, algorithm=ALGORITHM):
    payload = {"exp": int(time.time()) + expires_in}
    payload.update(claims or {})
    return pyjwt.encode(payload, secret, algorithm=algorithm)


# ------------------------------------------------------------------ registration
class TestRegistration:
    def test_creates_account_with_default_role(self, client, db):
        r = _register(client)
        assert r.status_code == 200
        assert unwrap(r)["role"] == "BUSINESS_ANALYST"
        assert db.query(User).filter_by(email="new@test.com").one().role == UserRole.BUSINESS_ANALYST

    @pytest.mark.parametrize("role", ["SUPER_ADMIN", "ADMIN", "REVIEWER", "PROJECT_MANAGER"])
    @pending_fix("issue 1", "POST /api/auth/register honours a client-supplied role, so anyone can self-register as an admin")
    def test_cannot_self_assign_privileged_role(self, client, db, role):
        r = _register(client, email=f"{role.lower()}@test.com", role=role)
        # Either rejecting the request or ignoring the field is acceptable;
        # what is never acceptable is creating the account with that role.
        if r.status_code == 200:
            user = db.query(User).filter_by(email=f"{role.lower()}@test.com").one()
            assert user.role == UserRole.BUSINESS_ANALYST
        else:
            assert 400 <= r.status_code < 500

    def test_duplicate_email_rejected(self, client, make_user):
        existing = make_user()
        r = _register(client, email=existing.email)
        assert r.status_code == 400

    @pytest.mark.parametrize(
        "body",
        [{"email": "not-an-email"}, {"password": None}, {"name": None}],
    )
    def test_invalid_payload_rejected(self, client, body):
        r = _register(client, **body)
        assert r.status_code == 422

    def test_password_is_hashed_and_never_returned(self, client, db):
        r = _register(client)
        assert "password" not in json.dumps(unwrap(r)).lower()
        stored = db.query(User).filter_by(email="new@test.com").one().password_hash
        assert stored != "S3cret!pass"
        assert stored.startswith("$2")  # bcrypt

    def test_can_be_disabled_by_administrator(self, client, monkeypatch):
        fake_os = types.SimpleNamespace(
            path=types.SimpleNamespace(
                join=os.path.join, dirname=os.path.dirname, abspath=os.path.abspath, exists=lambda p: True
            )
        )
        monkeypatch.setattr(auth_routes, "os", fake_os)
        monkeypatch.setattr(auth_routes, "open", lambda *a, **k: io.StringIO('{"allowRegistration": false}'), raising=False)
        r = _register(client)
        assert r.status_code == 403

    def test_registration_is_audited(self, client, db):
        _register(client)
        assert db.query(AuditLog).filter_by(action="user registration").count() == 1


# ------------------------------------------------------------------ login
class TestLogin:
    def _login(self, client, email, password=DEFAULT_PASSWORD):
        return client.post("/api/auth/login", json={"email": email, "password": password})

    def test_success_returns_token_and_public_profile(self, client, make_user):
        user = make_user(UserRole.PROJECT_MANAGER)
        r = self._login(client, user.email)
        assert r.status_code == 200
        data = unwrap(r)
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == user.email
        assert data["user"]["role"] == "PROJECT_MANAGER"
        assert "password" not in json.dumps(data).lower()

    def test_issued_token_carries_identity_claims(self, client, make_user):
        user = make_user()
        claims = decode_access_token(unwrap(self._login(client, user.email))["access_token"])
        assert claims["sub"] == user.email and claims["uid"] == user.id and claims["role"] == "BUSINESS_ANALYST"

    def test_updates_last_login(self, client, db, make_user):
        user = make_user()
        user.last_login = datetime.datetime(2000, 1, 1)
        db.commit()
        self._login(client, user.email)
        db.expire_all()
        assert db.get(User, user.id).last_login.year >= 2024

    def test_wrong_password_and_unknown_email_are_indistinguishable(self, client, make_user):
        user = make_user()
        wrong_pw = self._login(client, user.email, "nope")
        unknown = self._login(client, "ghost@test.com")
        assert wrong_pw.status_code == unknown.status_code == 401
        assert wrong_pw.json()["message"] == unknown.json()["message"]  # no account enumeration

    def test_disabled_account_cannot_log_in(self, client, make_user):
        user = make_user(status="DISABLED")
        assert self._login(client, user.email).status_code == 403

    def test_success_and_failure_are_audited(self, client, db, make_user):
        user = make_user()
        self._login(client, user.email)
        self._login(client, user.email, "wrong")
        assert db.query(AuditLog).filter_by(action="login").count() == 1
        assert db.query(AuditLog).filter_by(action="permission denied").count() == 1

    def test_me_returns_current_user(self, client, make_user, auth):
        user = make_user()
        r = client.get("/api/auth/me", headers=auth(user))
        assert r.status_code == 200 and unwrap(r)["email"] == user.email

    def test_logout_requires_authentication_and_is_audited(self, client, db, make_user, auth):
        assert client.post("/api/auth/logout").status_code == 401
        user = make_user()
        assert client.post("/api/auth/logout", headers=auth(user)).status_code == 200
        assert db.query(AuditLog).filter_by(action="logout").count() == 1


# ------------------------------------------------------------------ JWT
class TestJwtTokens:
    def test_round_trip(self):
        claims = decode_access_token(create_access_token({"sub": "a@b.com", "role": "ADMIN"}))
        assert claims["sub"] == "a@b.com" and claims["role"] == "ADMIN"

    def test_default_lifetime_is_24_hours(self):
        exp = decode_access_token(create_access_token({"sub": "a"}))["exp"]
        assert abs(exp - (time.time() + 24 * 3600)) < 5

    def test_custom_lifetime(self):
        exp = decode_access_token(create_access_token({"sub": "a"}, datetime.timedelta(minutes=5)))["exp"]
        assert abs(exp - (time.time() + 300)) < 5

    def test_expired_token_rejected(self):
        assert decode_access_token(create_access_token({"sub": "a"}, datetime.timedelta(seconds=-10))) is None

    def test_wrong_signing_secret_rejected(self):
        assert decode_access_token(_token({"sub": "a"}, secret="some-other-secret-that-is-long-enough!!")) is None

    def test_token_signed_with_old_public_default_is_rejected(self):
        assert decode_access_token(_token({"sub": "a"}, secret=OLD_PUBLIC_DEFAULT_SECRET)) is None

    def test_tampered_payload_rejected(self):
        header, _, signature = _token({"sub": "a", "role": "BUSINESS_ANALYST"}).split(".")
        forged = base64.urlsafe_b64encode(
            json.dumps({"sub": "a", "role": "SUPER_ADMIN", "exp": int(time.time()) + 3600}).encode()
        ).rstrip(b"=").decode()
        assert decode_access_token(f"{header}.{forged}.{signature}") is None

    def test_alg_none_token_rejected(self):
        b64 = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
        unsigned = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({'sub': 'a', 'exp': int(time.time()) + 3600})}."
        assert decode_access_token(unsigned) is None

    @pytest.mark.parametrize("garbage", ["", "abc", "a.b.c", "Bearer x", "....."])
    def test_garbage_rejected(self, garbage):
        assert decode_access_token(garbage) is None

    @pending_fix("issue 2", "JWT secret falls back to a hardcoded, publicly-known string when JWT_SECRET is unset")
    def test_no_publicly_known_fallback_when_secret_unset(self):
        forged = pyjwt.encode(
            {"sub": "admin@example.com", "exp": int(time.time()) + 3600}, OLD_PUBLIC_DEFAULT_SECRET, algorithm=ALGORITHM
        )
        code = (
            "import sys; sys.path.insert(0, sys.argv[1]);"
            "from auth.jwt import decode_access_token;"
            "print('ACCEPTED' if decode_access_token(sys.argv[2]) else 'REJECTED')"
        )
        env = {k: v for k, v in os.environ.items() if k != "JWT_SECRET"}
        out = subprocess.run([sys.executable, "-c", code, str(BACKEND_DIR), forged], env=env, capture_output=True, text=True)
        assert out.stdout.strip() == "REJECTED", out.stderr


class TestTokenEnforcementOnRoutes:
    @pytest.mark.parametrize(
        "header",
        [
            None,
            "Bearer",
            "Bearer not-a-jwt",
            "Basic abc123",
            "Bearer " + _token({"sub": "a@b.com"}, secret="wrong-secret-wrong-secret-wrong-secret"),
            "Bearer " + _token({"sub": "a@b.com"}, expires_in=-60),
            "Bearer " + _token({"role": "ADMIN"}),  # valid signature but no subject
        ],
    )
    def test_invalid_credentials_get_401(self, client, header):
        headers = {"Authorization": header} if header else {}
        assert client.get("/api/auth/me", headers=headers).status_code == 401

    def test_token_for_deleted_user_rejected(self, client, db, make_user, auth):
        user = make_user()
        headers = auth(user)
        db.delete(user)
        db.commit()
        assert client.get("/api/auth/me", headers=headers).status_code == 401

    def test_disabled_user_with_valid_token_rejected(self, client, db, make_user, auth):
        user = make_user()
        headers = auth(user)
        user.status = "DISABLED"
        db.commit()
        assert client.get("/api/auth/me", headers=headers).status_code == 403

    def test_role_claim_in_token_is_not_trusted(self, client, make_user):
        """Authorization must use the role stored in the database, not the token's claim."""
        user = make_user(UserRole.BUSINESS_ANALYST)
        forged = _token({"sub": user.email, "role": "SUPER_ADMIN", "uid": user.id})
        r = client.get("/api/admin/users", headers={"Authorization": f"Bearer {forged}"})
        assert r.status_code == 403


# ------------------------------------------------------------------ passwords
class TestPasswordHashing:
    def test_hash_verifies_and_is_salted(self):
        h1, h2 = hash_password("pw"), hash_password("pw")
        assert h1 != h2 and verify_password("pw", h1) and verify_password("pw", h2)

    def test_wrong_password_fails(self):
        assert not verify_password("other", hash_password("pw"))

    @pytest.mark.parametrize("bad_hash", ["", "not-a-hash"])
    def test_malformed_hash_returns_false_instead_of_raising(self, bad_hash):
        assert verify_password("pw", bad_hash) is False

    @pending_fix(
        "finding A",
        "bcrypt panics on a truncated hash that has a valid prefix; the panic is a BaseException, "
        "so verify_password's `except Exception` misses it and a corrupted stored hash crashes login",
    )
    def test_truncated_hash_with_valid_prefix_returns_false(self):
        assert verify_password("pw", "$2b$12$short") is False
