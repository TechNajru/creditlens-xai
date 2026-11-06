import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import VALID_APPLICATION

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_valid_prediction(trained_dir):
    r = client.post("/api/v1/assessments/predict", json=VALID_APPLICATION)
    assert r.status_code == 200
    body = r.json()
    assert 0 <= body["default_probability_simulated"] <= 1
    assert "SYNTHETIC" in body["data_provenance"]
    assert body["explanation"]["status"] == "available" and body["explanation"]["reason_codes"]
    assert body["derived_values"]["total_emi_to_income"] > 0


def test_legacy_predict_route_matches_v1(trained_dir):
    a = client.post("/predict", json=VALID_APPLICATION).json()
    b = client.post("/api/v1/assessments/predict", json=VALID_APPLICATION).json()
    assert a["default_probability_simulated"] == b["default_probability_simulated"]


def test_unknown_credit_history_is_accepted(trained_dir):
    r = client.post("/predict", json={**VALID_APPLICATION, "credit_history_months": None})
    assert r.status_code == 200
    assert r.json()["derived_values"]["credit_history_missing"] is True


@pytest.mark.parametrize("patch", [
    {"tenure_months": 0}, {"loan_amount": -100}, {"monthly_income": 0}, {"age": 12},
])
def test_invalid_input_is_rejected(trained_dir, patch):
    assert client.post("/predict", json={**VALID_APPLICATION, **patch}).status_code == 422


def test_missing_field_is_rejected(trained_dir):
    bad = {k: v for k, v in VALID_APPLICATION.items() if k != "monthly_income"}
    assert client.post("/predict", json=bad).status_code == 422


def test_higher_emi_burden_gives_higher_simulated_risk(trained_dir):
    low = client.post("/predict", json={**VALID_APPLICATION, "loan_amount": 50000}).json()
    high = client.post("/predict", json={**VALID_APPLICATION, "loan_amount": 1_000_000,
                                         "existing_emi": 20000}).json()
    assert high["default_probability_simulated"] > low["default_probability_simulated"]


def test_missing_artifact_returns_503(tmp_path, monkeypatch):
    monkeypatch.setenv("CREDITLENS_MODELS_DIR", str(tmp_path))
    r = client.post("/predict", json=VALID_APPLICATION)
    assert r.status_code == 503
    assert "train" in r.json()["detail"].lower()
