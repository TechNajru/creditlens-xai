"""Helpers for tests that use real cookies, CSRF tokens and roles."""
from pathlib import Path

from fastapi.testclient import TestClient

from app import registry
from app.admin import create_user
from app.db import get_session_factory
from app.main import app
from app.notice import NOTICE_VERSION

PASSWORD = "correct-horse-battery-1"
SAMPLES = Path(__file__).resolve().parents[2] / "sample_data"
LOAN = {"monthly_income": 60000, "loan_amount": 400000, "tenure_months": 36, "annual_interest_rate": 12.0,
        "existing_emi": 6000, "age": 32, "employment_years": 5, "num_existing_loans": 1, "credit_history_months": 48}
HEAVY = {**LOAN, "monthly_income": 40000, "loan_amount": 1_200_000, "annual_interest_rate": 14, "existing_emi": 15000,
         "credit_history_months": None}


class Api:
    """One browser-like client: its own cookie jar and its own CSRF token."""

    def __init__(self):
        self.client = TestClient(app)
        self.csrf = None
        self.user = None

    def _headers(self, extra=None):
        h = dict(extra or {})
        if self.csrf:
            h["X-CSRF-Token"] = self.csrf
        return h

    def request(self, method, path, headers=None, **kw):
        return self.client.request(method, path, headers=self._headers(headers), **kw)

    def get(self, path, **kw): return self.request("GET", path, **kw)
    def post(self, path, **kw): return self.request("POST", path, **kw)
    def patch(self, path, **kw): return self.request("PATCH", path, **kw)
    def delete(self, path, **kw): return self.request("DELETE", path, **kw)

    def _adopt(self, r):
        if r.status_code in (200, 201):
            body = r.json()
            self.csrf, self.user = body["csrf_token"], body["user"]
        return r

    def register(self, email, password=PASSWORD, notice=NOTICE_VERSION, **extra):
        return self._adopt(self.client.post("/api/v1/auth/register", json={
            "email": email, "password": password, "accept_notice_version": notice, **extra}))

    def login(self, email, password=PASSWORD):
        return self._adopt(self.client.post("/api/v1/auth/login", json={"email": email, "password": password}))

    def upload(self, app_id, path_or_bytes, name="statement.csv"):
        data = Path(path_or_bytes).read_bytes() if isinstance(path_or_bytes, (str, Path)) else path_or_bytes
        return self.post(f"/api/v1/applications/{app_id}/uploads", files={"file": (name, data, "text/csv")})


def seed(roles=("reviewer", "admin"), activate=True):
    """Create staff users and (optionally) register + activate the trained simulation model."""
    db = get_session_factory()()
    try:
        for role in roles:
            create_user(db, f"{role}@demo.local", role, PASSWORD)
        if activate:
            mv, _ = registry.register_artifact(db, "simulation")
            registry.activate(db, mv)
        db.commit()
    finally:
        db.close()


def logged_in(email, role=None):
    api = Api()
    r = api.register(email) if role is None else api.login(email)
    assert r.status_code in (200, 201), r.text
    return api
