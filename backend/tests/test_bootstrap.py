import pytest
from sqlalchemy import func, select

from app import admin
from app.db import get_session_factory
from app.models import ModelVersion, User
from tests.api_helpers import Api

pytestmark = pytest.mark.real_auth
PW = "a-strong-bootstrap-pass-1"


def run(capsys):
    code = admin.main(["bootstrap"])
    out = capsys.readouterr()
    return code, out.out + out.err


def test_bootstrap_creates_everything_once_and_never_prints_the_password(db_env, monkeypatch, capsys):
    monkeypatch.setenv("CREDITLENS_BOOTSTRAP_ADMIN_EMAIL", "Owner@Example.com")
    monkeypatch.setenv("CREDITLENS_BOOTSTRAP_ADMIN_PASSWORD", PW)
    code, out = run(capsys)
    assert code == 0 and "bootstrap complete" in out and "admin account created for owner@example.com" in out
    assert PW not in out and "password=" not in out
    with get_session_factory()() as s:
        assert s.scalar(select(func.count()).select_from(User).where(User.role == "admin")) == 1
        active = s.scalars(select(ModelVersion).where(ModelVersion.is_active.is_(True))).all()
        assert len(active) == 1 and active[0].track == "simulation"
    admin_api = Api()
    assert admin_api.login("owner@example.com", PW).status_code == 200
    assert admin_api.get("/api/v1/admin/users").status_code == 200


def test_bootstrap_is_idempotent_and_does_not_reset_an_existing_password(db_env, monkeypatch, capsys):
    monkeypatch.setenv("CREDITLENS_BOOTSTRAP_ADMIN_EMAIL", "owner@example.com")
    monkeypatch.setenv("CREDITLENS_BOOTSTRAP_ADMIN_PASSWORD", PW)
    run(capsys)
    monkeypatch.setenv("CREDITLENS_BOOTSTRAP_ADMIN_PASSWORD", "a-different-password-2")      # e.g. someone edits the env var later
    code, out = run(capsys)
    assert code == 0 and "admin account: exists" in out and "already registered" in out
    with get_session_factory()() as s:
        assert s.scalar(select(func.count()).select_from(User)) == 1
        assert s.scalar(select(func.count()).select_from(ModelVersion)) == 1
    assert Api().login("owner@example.com", PW).status_code == 200
    assert Api().login("owner@example.com", "a-different-password-2").status_code == 401


def test_bootstrap_warns_when_no_admin_credentials_are_configured(db_env, monkeypatch, capsys):
    monkeypatch.delenv("CREDITLENS_BOOTSTRAP_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("CREDITLENS_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    code, out = run(capsys)
    assert code == 0 and "WARNING: no admin account exists" in out


def test_bootstrap_rejects_a_weak_admin_password(db_env, monkeypatch, capsys):
    monkeypatch.setenv("CREDITLENS_BOOTSTRAP_ADMIN_EMAIL", "owner@example.com")
    monkeypatch.setenv("CREDITLENS_BOOTSTRAP_ADMIN_PASSWORD", "password123")
    code, out = run(capsys)
    assert code == 1 and "could not create the bootstrap admin" in out and "password123" not in out
    with get_session_factory()() as s:
        assert s.scalar(select(func.count()).select_from(User)) == 0


def test_bootstrap_fails_clearly_without_a_trained_model(db_env, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CREDITLENS_MODELS_DIR", str(tmp_path / "empty"))
    code, out = run(capsys)
    assert code == 1 and "python -m app.train" in out
