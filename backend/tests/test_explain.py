import math
import shutil

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import explain
from app.main import app
from app.predict import load_bundle, predict_one
from app.reason_codes import describe_loan, describe_public, format_value
from tests.conftest import VALID_APPLICATION
from tests.test_public import GOOD, public_run  # noqa: F401  (fixture re-used)

client = TestClient(app)
BURDENED = {**VALID_APPLICATION, "loan_amount": 1_200_000, "existing_emi": 20000, "credit_history_months": None}


def full(app_input):
    r = client.post("/api/v1/assessments/predict?detail=full", json=app_input)
    assert r.status_code == 200
    return r.json()


def test_contributions_add_up_to_the_raw_score(trained_dir):
    body = full(BURDENED)
    ex = body["explanation"]
    total = ex["baseline"] + sum(c["contribution"] for c in ex["contributions"])
    assert total == pytest.approx(ex["model_output"], abs=1e-6)
    assert ex["model_output"] == pytest.approx(body["uncalibrated_model_score"], abs=1e-9)
    assert "uncalibrated" in ex["scale"] and len(ex["notes"]) == 3


def test_directions_and_reason_codes(trained_dir):
    ex = full(BURDENED)["explanation"]
    assert all(i["contribution"] > 0 for i in ex["top_risk_increasing"])
    assert all(i["contribution"] < 0 for i in ex["top_risk_reducing"])
    assert ex["reason_codes"] and all("risk score" in r for r in ex["reason_codes"])
    emi = next(c for c in ex["contributions"] if c["feature"] == "total_emi_to_income")
    assert emi["contribution"] > 0                      # high EMI burden raises the model's score
    unknown = next(c for c in ex["contributions"] if c["feature"] == "credit_history_months")
    assert "unknown" in unknown["value_display"]        # missing history shown as unknown, not zero


def test_explanation_is_deterministic(trained_dir):
    a = full(BURDENED)["explanation"]["contributions"]
    b = full(BURDENED)["explanation"]["contributions"]
    assert a == b


def test_summary_is_short_and_full_has_everything(trained_dir):
    s = client.post("/api/v1/assessments/predict", json=BURDENED).json()["explanation"]
    f = full(BURDENED)["explanation"]
    assert "contributions" not in s and "global_importance" not in s
    assert len(f["contributions"]) == 14 and f["global_importance"]["values"]


def test_global_importance_is_stored_with_the_model(trained_dir):
    gi = load_bundle(trained_dir / "models").metadata["global_importance"]
    vals = [v["mean_abs_shap"] for v in gi["values"]]
    assert vals == sorted(vals, reverse=True) and len(vals) == 14
    assert gi["computed_on"].startswith("sample of the validation split")


def test_missing_background_is_reported_not_faked(trained_dir):
    bundle = load_bundle(trained_dir / "models")
    bundle.background = None
    result = predict_one(bundle, VALID_APPLICATION)
    assert result["explanation"]["status"] == "unavailable" and "Retrain" in result["explanation"]["reason"]
    assert 0 <= result["default_probability_simulated"] <= 1     # prediction still works


def test_explainer_crash_does_not_break_prediction(trained_dir, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("secret internals")
    monkeypatch.setattr(explain, "_make_explainer", boom)
    r = client.post("/api/v1/assessments/predict", json=VALID_APPLICATION)
    assert r.status_code == 200
    ex = r.json()["explanation"]
    assert ex["status"] == "unavailable" and "secret" not in str(ex)


def test_failed_additivity_check_withholds_explanation(trained_dir, monkeypatch):
    monkeypatch.setattr(explain, "CONSISTENCY_TOL", -1.0)       # force the check to fail
    ex = client.post("/api/v1/assessments/predict", json=VALID_APPLICATION).json()["explanation"]
    assert ex["status"] == "unavailable" and "additivity" in ex["reason"]


def test_public_model_explanation(public_run):  # noqa: F811
    r = client.post("/api/v1/assessments/predict-public?detail=full", json=GOOD)
    ex = r.json()["explanation"]
    assert ex["status"] == "available" and len(ex["contributions"]) == 23
    assert ex["baseline"] + sum(c["contribution"] for c in ex["contributions"]) == pytest.approx(ex["model_output"], abs=1e-6)
    labels = {c["feature"]: c["label"] for c in ex["contributions"]}
    assert labels["PAY_0"] == "Repayment status, Sep 2005"


def test_value_formatting():
    assert format_value(float("nan"), "money") == "unknown (not treated as zero)"
    assert format_value(0.3, "pct") == "30%"
    assert format_value(-1, "pay") == "paid duly (-1)" and format_value(2, "pay") == "2 month(s) delayed"
    assert "not defined" in format_value(0, "pay") and "not defined" in format_value(-2, "pay")
    assert describe_public("LIMIT_BAL", 50000)[1] == "NT$50,000"
    assert describe_loan("credit_history_missing", 1.0)[1] == "not available"


# ---------------- evaluation endpoint ----------------
def test_evaluation_endpoint(trained_dir, public_run, tmp_path, monkeypatch):  # noqa: F811
    reports = tmp_path / "reports"
    reports.mkdir()
    shutil.copy(trained_dir / "reports" / "evaluation.json", reports / "evaluation.json")
    shutil.copy(trained_dir / "public_reports" / "evaluation_public.json", reports / "evaluation_public.json")
    monkeypatch.setenv("CREDITLENS_REPORTS_DIR", str(reports))
    sim = client.get("/api/v1/models/simulation/evaluation").json()
    pub = client.get("/api/v1/models/public/evaluation").json()
    assert sim["track"] == "simulation" and "SYNTHETIC" in sim["report"]["data_provenance"]
    assert pub["report"]["dataset"]["licence"] and pub["limitations"]
    assert sim["report"]["calibration_curve_test"]["mean_predicted"]
    assert client.get("/api/v1/models/other/evaluation").status_code == 422


def test_evaluation_404_when_untrained(tmp_path, monkeypatch):
    monkeypatch.setenv("CREDITLENS_REPORTS_DIR", str(tmp_path))
    assert client.get("/api/v1/models/public/evaluation").status_code == 404


def test_model_card_is_generated_from_artifacts(trained_dir, public_run, tmp_path):  # noqa: F811
    from app.model_card import render_model_card
    models, reports = trained_dir / "models", trained_dir / "reports"
    card = render_model_card("simulation", models, reports)
    assert "SYNTHETIC" in card and "No fairness assessment" in card and "(selected)" in card
    assert "Out of scope" in card and "Brier" in card
    pub = render_model_card("public", models, trained_dir / "public_reports")
    assert "CC BY 4.0" in pub and "## Citation" in pub and "https://doi.org/10.0000/fixture" in pub
