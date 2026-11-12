import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from app import config
from app.db import get_session_factory, utcnow
from app.models import AuditEvent, AuthSession, User
from app.notice import NOTICE_VERSION
from app.security import hash_password, hash_token, password_problems, verify_password
from tests.api_helpers import LOAN, PASSWORD, Api, logged_in, seed

pytestmark = pytest.mark.real_auth


def test_argon2_hashing_and_policy():
    h = hash_password(PASSWORD)
    assert h.startswith("$argon2id$") and PASSWORD not in h
    assert verify_password(h, PASSWORD) and not verify_password(h, "wrong") and not verify_password("junk", PASSWORD)
    assert password_problems("short") and password_problems("password123") and password_problems("aaaaaaaaaaaa")
    assert password_problems("najrudeen-2026-x", "najrudeen@example.com")
    assert password_problems(PASSWORD, "someone@example.com") == []


def test_register_sets_httponly_cookie_and_stores_only_a_token_hash(db_env):
    api = Api()
    r = api.register("a@example.com")
    assert r.status_code == 201 and r.json()["user"]["role"] == "applicant" and r.json()["csrf_token"]
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "creditlens_session=" in cookie
    token = api.client.cookies.get("creditlens_session")
    db = get_session_factory()()
    sess = db.scalar(select(AuthSession))
    assert sess.token_hash == hash_token(token) and sess.token_hash != token
    db.close()


def test_cookie_is_secure_when_configured(db_env, monkeypatch):
    monkeypatch.setenv("CREDITLENS_COOKIE_SECURE", "true")
    assert "Secure" in Api().register("s@example.com").headers["set-cookie"]


def test_registration_rules(db_env):
    api = Api()
    assert api.register("a@example.com", notice="old-version").status_code == 422
    assert api.register("a@example.com", password="short").status_code == 422
    assert api.register("not-an-email").status_code == 422
    assert api.register("a@example.com", role="admin").json()["user"]["role"] == "applicant"   # role cannot be chosen
    assert Api().register("A@Example.com").status_code == 409                                     # case-insensitive duplicate


def test_login_errors_are_generic_and_accounts_lock(db_env):
    api = Api()
    api.register("a@example.com")
    unknown = Api().login("nobody@example.com", PASSWORD)
    wrong = Api().login("a@example.com", "wrong-password-1")
    assert unknown.status_code == wrong.status_code == 401 and unknown.json() == wrong.json()
    for _ in range(config.max_failed_logins() - 1):
        assert Api().login("a@example.com", "wrong-password-1").status_code == 401
    # failures so far: 1 (`wrong`) + (max-1) in the loop = max, so the account is now locked
    assert Api().login("a@example.com", PASSWORD).status_code == 429                      # even the right password is refused
    db = get_session_factory()()
    u = db.scalar(select(User).where(User.email == "a@example.com"))
    u.locked_until = utcnow() - timedelta(minutes=1)
    db.commit(); db.close()
    assert Api().login("a@example.com", PASSWORD).status_code == 200


def test_login_rotates_the_session(db_env):
    api = Api()
    api.register("a@example.com")
    first = api.client.cookies.get("creditlens_session")
    api.login("a@example.com")
    assert api.client.cookies.get("creditlens_session") != first


def test_me_requires_login_and_returns_csrf(db_env):
    assert Api().get("/api/v1/auth/me").status_code == 401
    api = logged_in("a@example.com")
    body = api.get("/api/v1/auth/me").json()
    assert body["user"]["email"] == "a@example.com" and body["csrf_token"] == api.csrf


def test_csrf_token_is_required_for_unsafe_methods(db_env):
    seed()
    api = logged_in("a@example.com")
    path = "/api/v1/applications"
    good = api.csrf
    api.csrf = None
    assert api.post(path, json=LOAN).status_code == 403
    api.csrf = "x" * len(good)
    assert api.post(path, json=LOAN).status_code == 403
    api.csrf = good
    assert api.post(path, json=LOAN).status_code == 201
    api.csrf = None
    assert api.get(path).status_code == 200                                   # safe methods need no token


def test_origin_header_is_checked(db_env):
    seed()
    api = logged_in("a@example.com")
    assert api.post("/api/v1/applications", json=LOAN, headers={"Origin": "http://evil.example"}).status_code == 403
    assert api.post("/api/v1/applications", json=LOAN, headers={"Origin": "http://localhost:3000"}).status_code == 201
    assert Api().client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": PASSWORD},
                             headers={"Origin": "http://evil.example"}).status_code == 403


def test_logout_and_replay(db_env):
    api = logged_in("a@example.com")
    stolen = api.client.cookies.get("creditlens_session")
    assert api.post("/api/v1/auth/logout").status_code == 200
    assert api.get("/api/v1/auth/me").status_code == 401
    replay = Api()
    replay.client.cookies.set("creditlens_session", stolen)
    assert replay.get("/api/v1/auth/me").status_code == 401


def test_expired_session_is_rejected(db_env):
    api = logged_in("a@example.com")
    db = get_session_factory()()
    s = db.scalar(select(AuthSession))
    s.expires_at = utcnow() - timedelta(seconds=1)
    db.commit(); db.close()
    r = api.get("/api/v1/auth/me")
    assert r.status_code == 401 and "expired" in r.json()["detail"].lower()


def test_deactivated_user_loses_access(db_env):
    seed()
    victim = logged_in("victim@example.com")
    admin = Api(); admin.login("admin@demo.local")
    uid = victim.user["id"]
    assert admin.patch(f"/api/v1/admin/users/{uid}", json={"is_active": False}).status_code == 200
    assert victim.get("/api/v1/auth/me").status_code == 401
    assert Api().login("victim@example.com", PASSWORD).status_code == 401


def test_role_enforcement_matrix(db_env):
    seed()
    anon, applicant = Api(), logged_in("a@example.com")
    reviewer, admin = Api(), Api()
    reviewer.login("reviewer@demo.local"); admin.login("admin@demo.local")
    endpoints = [("get", "/api/v1/applications"), ("get", "/api/v1/reviews/queue"), ("get", "/api/v1/admin/users")]
    for method, path in endpoints:
        assert getattr(anon, method)(path).status_code == 401
    expected = {"applicant": (200, 403, 403), "reviewer": (403, 200, 403), "admin": (403, 403, 200)}
    for name, api in (("applicant", applicant), ("reviewer", reviewer), ("admin", admin)):
        got = tuple(getattr(api, m)(p).status_code for m, p in endpoints)
        assert got == expected[name], (name, got)
    assert reviewer.post("/api/v1/applications", json=LOAN).status_code == 403
    assert admin.post("/api/v1/applications", json=LOAN).status_code == 403


def test_earlier_stage_endpoints_now_require_login(db_env):
    seed()
    assert Api().post("/predict", json=LOAN).status_code == 401
    assert Api().get("/api/v1/fairness/public").status_code == 401
    assert logged_in("a@example.com").get("/api/v1/fairness/public").status_code == 403      # applicants: no sensitive audit
    assert Api().get("/health").status_code == 200


def test_cors_allows_only_the_configured_origin_with_credentials(db_env):
    c = Api().client
    ok = c.options("/api/v1/auth/me", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert ok.headers["access-control-allow-credentials"] == "true"
    bad = c.options("/api/v1/auth/me", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers
    pre = c.options("/api/v1/applications", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST",
                                                      "Access-Control-Request-Headers": "content-type,x-csrf-token"})
    assert pre.status_code == 200 and "x-csrf-token" in pre.headers["access-control-allow-headers"].lower()


def test_security_headers_present(db_env):
    r = Api().get("/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-store"


def test_audit_log_never_contains_credentials_or_email(db_env):
    api = Api()
    api.register("private.person@example.com")
    api.login("private.person@example.com")
    Api().login("private.person@example.com", "wrong-password-9")
    db = get_session_factory()()
    blob = json.dumps([[e.action, e.entity_id, e.details] for e in db.scalars(select(AuditEvent))])
    db.close()
    assert "private.person" not in blob and PASSWORD not in blob and "wrong-password" not in blob
    assert "auth.registered" in blob and "auth.login_failed" in blob


# ---------------- black-box sweep of EVERY route (guards against forgetting a dependency on a future endpoint) ----------------
import re

from app.main import app as _app

PUBLIC_ROUTES = {("GET", "/health"), ("GET", "/api/v1/consent/notice"), ("POST", "/api/v1/auth/register"), ("POST", "/api/v1/auth/login")}


def _all_routes():
    out = []
    for path, ops in _app.openapi()["paths"].items():
        for method in ops:
            if method.upper() in {"GET", "POST", "PATCH", "DELETE", "PUT"}:
                out.append((method.upper(), path))
    return out


def _concrete(path):
    return re.sub(r"\{[^}]+\}", "1", path)


def _call(api, method, path):
    return api.client.request(method, _concrete(path), json={} if method != "GET" else None,
                              headers={"X-CSRF-Token": api.csrf} if api.csrf else {})


def test_openapi_enumerates_the_whole_api():
    routes = _all_routes()
    paths = [p for _, p in routes]
    for prefix in ("/api/v1/auth", "/api/v1/applications", "/api/v1/reviews", "/api/v1/admin", "/api/v1/scenarios",
                   "/api/v1/uploads", "/api/v1/cashflow", "/api/v1/assessments", "/api/v1/models", "/api/v1/fairness"):
        assert any(p.startswith(prefix) for p in paths), f"no routes found under {prefix}: the sweep would miss them"
    assert len(routes) >= 40 and PUBLIC_ROUTES <= set(routes)


def test_every_route_refuses_anonymous_callers(db_env):
    anon = Api()
    leaks = []
    for method, path in _all_routes():
        status = _call(anon, method, path).status_code
        if (method, path) in PUBLIC_ROUTES:
            assert status in (200, 422), (method, path, status)          # public: works or fails validation, never 401/403/500
        elif status != 401:
            leaks.append((method, path, status))
    assert leaks == [], f"routes that did not require login: {leaks}"


def test_every_route_enforces_its_role(db_env):
    seed()
    applicant = logged_in("a@example.com")
    reviewer, admin = Api(), Api()
    reviewer.login("reviewer@demo.local"); admin.login("admin@demo.local")
    wrong = []
    for method, path in _all_routes():
        if (method, path) in PUBLIC_ROUTES:
            continue
        if path.startswith("/api/v1/admin"):
            denied = [("applicant", applicant), ("reviewer", reviewer)]
        elif path.startswith("/api/v1/reviews"):
            denied = [("applicant", applicant), ("admin", admin)]
        elif path.startswith("/api/v1/applications"):
            denied = [("reviewer", reviewer), ("admin", admin)]
        elif path == "/api/v1/fairness/public":
            denied = [("applicant", applicant)]
        else:
            continue
        for name, api in denied:
            status = _call(api, method, path).status_code
            if status != 403:
                wrong.append((name, method, path, status))
    assert wrong == [], f"role boundary leaks: {wrong}"
