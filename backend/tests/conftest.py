import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("CREDITLENS_GLOBAL_SHAP_ROWS", "40")  # keep tests fast

from app import train as train_module


@pytest.fixture(scope="session")
def trained_dir(tmp_path_factory):
    """Train a small model once per test session into a temporary folder."""
    base = tmp_path_factory.mktemp("artifacts")
    models, reports = base / "models", base / "reports"
    train_module.train(models_dir=models, reports_dir=reports, n_samples=4000, seed=7)
    old = os.environ.get("CREDITLENS_MODELS_DIR")
    os.environ["CREDITLENS_MODELS_DIR"] = str(models)
    yield base
    if old is None:
        os.environ.pop("CREDITLENS_MODELS_DIR", None)
    else:
        os.environ["CREDITLENS_MODELS_DIR"] = old


VALID_APPLICATION = {
    "monthly_income": 50000, "loan_amount": 300000, "tenure_months": 36,
    "annual_interest_rate": 12.0, "existing_emi": 5000, "age": 32,
    "employment_years": 5, "num_existing_loans": 1, "credit_history_months": 48,
}


# ---------------- Stage 5: authentication in tests ----------------
@pytest.fixture(autouse=True)
def _legacy_auth(request):
    """Stage 1-4 tests exercise stateless endpoints, not login. They get a fake logged-in admin.
    Tests marked `real_auth` use the real cookie + CSRF + role checks instead."""
    if request.node.get_closest_marker("real_auth"):
        yield
        return
    from app.deps import authenticated_user, staff_user
    from app.main import app
    fake = SimpleNamespace(id=0, email="test@example.com", role="admin", is_active=True)
    app.dependency_overrides[authenticated_user] = lambda: fake
    app.dependency_overrides[staff_user] = lambda: fake
    yield
    app.dependency_overrides.clear()


def fresh_database_url(tmp_path) -> str:
    """SQLite file per test by default. If CREDITLENS_TEST_DATABASE_URL points at PostgreSQL, use it and wipe the schema first,
    so the same tests prove the app works on both databases."""
    pg = os.environ.get("CREDITLENS_TEST_DATABASE_URL")
    if not pg:
        return f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    from sqlalchemy import create_engine, text
    from app.config import normalize_database_url
    pg = normalize_database_url(pg)
    engine = create_engine(pg, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    return pg


@pytest.fixture
def db_env(tmp_path, trained_dir, monkeypatch):
    """A fresh migrated database (SQLite, or PostgreSQL if CREDITLENS_TEST_DATABASE_URL is set) + model registry per test."""
    monkeypatch.setenv("CREDITLENS_DATABASE_URL", fresh_database_url(tmp_path))
    monkeypatch.setenv("CREDITLENS_REGISTRY_DIR", str(tmp_path / "registry"))
    from app import admin, db, registry
    db.reset_engine()
    registry.clear_cache()
    admin.upgrade_database()
    yield tmp_path
    db.reset_engine()
    registry.clear_cache()
