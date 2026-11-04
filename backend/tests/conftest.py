import os

import pytest

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
