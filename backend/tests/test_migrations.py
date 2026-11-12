import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import admin, db as appdb
from app.models import AuthSession

pytestmark = pytest.mark.real_auth

EXPECTED = {"users", "sessions", "consent_records", "applications", "uploads", "transactions", "feature_snapshots",
            "assessments", "explanations", "review_decisions", "info_requests", "model_versions", "audit_events"}


@pytest.fixture
def url(tmp_path, monkeypatch):
    from tests.conftest import fresh_database_url
    u = fresh_database_url(tmp_path)
    monkeypatch.setenv("CREDITLENS_DATABASE_URL", u)
    appdb.reset_engine()
    yield u
    appdb.reset_engine()


def test_upgrade_creates_every_entity_and_matches_the_models(url):
    admin.upgrade_database()
    engine = create_engine(url)
    assert EXPECTED <= set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), appdb.Base.metadata)
    assert diff == [], f"migrations are out of date with the models: {diff}"


def test_downgrade_removes_the_schema_and_upgrade_is_repeatable(url):
    admin.upgrade_database()
    command.downgrade(admin.alembic_config(), "base")
    assert EXPECTED.isdisjoint(set(inspect(create_engine(url)).get_table_names()))
    admin.upgrade_database()
    admin.upgrade_database()                       # running twice is harmless
    assert EXPECTED <= set(inspect(create_engine(url)).get_table_names())


def test_foreign_keys_are_enforced(url):
    admin.upgrade_database()
    with Session(appdb.get_engine()) as s:
        s.add(AuthSession(user_id=9999, token_hash="x" * 64, csrf_token="c",
                          expires_at=appdb.utcnow()))
        with pytest.raises(IntegrityError):
            s.commit()


def test_role_check_constraint_blocks_invalid_roles(url):
    from app.models import User
    admin.upgrade_database()
    with Session(appdb.get_engine()) as s:
        s.add(User(email="x@example.com", password_hash="h", role="superuser"))
        with pytest.raises(IntegrityError):
            s.commit()
