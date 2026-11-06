import json

import joblib
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.predict import ModelNotAvailableError
from app.public_data import DatasetNotFoundError, find_dataset, load_public_dataset
from app.public_features import (AUDIT_COLUMNS, PAY_COLS, PUBLIC_FEATURE_COLUMNS, PUBLIC_TARGET, RAW_PUBLIC,
                                 InvalidPublicInputError, build_public_features)
from app.public_predict import load_public_bundle, predict_public
from app.public_train import split_indices, train_public

client = TestClient(app)


def fixture_frame(n=3000, seed=0):
    """TEST FIXTURE ONLY: random data shaped like the UCI file. Not real, not for reporting."""
    rng = np.random.default_rng(seed)
    d = {"LIMIT_BAL": rng.integers(10_000, 500_000, n).astype(float), "AGE": rng.integers(21, 70, n)}
    for c in PAY_COLS:
        d[c] = rng.choice([-2, -1, 0, 1, 2, 3], n, p=[.1, .2, .4, .15, .1, .05])
    for i in range(1, 7):
        d[f"BILL_AMT{i}"] = rng.integers(-500, 200_000, n).astype(float)
        d[f"PAY_AMT{i}"] = rng.integers(0, 20_000, n).astype(float)
    raw = pd.DataFrame(d)
    logit = -1.6 + 0.9 * (raw["PAY_0"] >= 1) + 0.4 * (raw["PAY_2"] >= 1) + rng.normal(0, 0.5, n)
    y = pd.Series((rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int), name=PUBLIC_TARGET)
    audit = pd.DataFrame({"SEX": rng.integers(1, 3, n), "EDUCATION": rng.integers(1, 4, n),
                          "MARRIAGE": rng.integers(1, 4, n)})
    return raw, y, audit, {"name": "fixture", "creator": "test", "url": "https://example.org/fixture", "doi": "https://doi.org/10.0000/fixture", "licence": "CC BY 4.0 (fixture)",
                           "population": "fixture", "label": "fixture", "rows": n, "positive_rate": float(y.mean()),
                           "duplicate_rows_excluding_id": 0}


GOOD = {"LIMIT_BAL": 100000, "AGE": 35, "PAY_0": 2, "PAY_2": -1, "PAY_3": 0, "PAY_4": 1, "PAY_5": -2, "PAY_6": 3,
        **{f"BILL_AMT{i}": 50000 for i in range(1, 7)}, **{f"PAY_AMT{i}": 5000 for i in range(1, 7)}}


# ---------------- features ----------------
def test_hand_checked_derived_features():
    f = build_public_features(pd.DataFrame([GOOD])).iloc[0]
    assert f["utilization_latest"] == pytest.approx(0.5)
    assert f["payment_ratio_latest"] == pytest.approx(0.1)
    assert f["months_delayed"] == 3          # PAY_0=2, PAY_4=1, PAY_6=3; -2/-1/0 are not counted as delays


@pytest.mark.parametrize("bill", [0, -100])
def test_payment_ratio_is_unknown_not_zero_when_bill_not_positive(bill):
    f = build_public_features(pd.DataFrame([{**GOOD, "BILL_AMT1": bill}])).iloc[0]
    assert np.isnan(f["payment_ratio_latest"])


def test_negative_bill_is_kept_not_clipped():
    f = build_public_features(pd.DataFrame([{**GOOD, "BILL_AMT1": -500}])).iloc[0]
    assert f["BILL_AMT1"] == -500 and f["utilization_latest"] == pytest.approx(-0.005)


@pytest.mark.parametrize("patch", [{"PAY_0": 10}, {"AGE": 17}, {"LIMIT_BAL": 0}, {"PAY_AMT1": -1}, {"PAY_2": None}])
def test_invalid_inputs_rejected(patch):
    with pytest.raises(InvalidPublicInputError):
        build_public_features(pd.DataFrame([{**GOOD, **patch}]))


def test_missing_column_rejected():
    with pytest.raises(InvalidPublicInputError):
        build_public_features(pd.DataFrame([{k: v for k, v in GOOD.items() if k != "AGE"}]))


def test_sensitive_columns_and_target_not_in_features():
    assert not set(AUDIT_COLUMNS) & set(PUBLIC_FEATURE_COLUMNS)
    assert PUBLIC_TARGET not in PUBLIC_FEATURE_COLUMNS and "ID" not in PUBLIC_FEATURE_COLUMNS


# ---------------- loader ----------------
def _csv(tmp_path, name, with_extra_header, target_name):
    raw, y, audit, _ = fixture_frame(60, 1)
    df = pd.concat([pd.Series(range(1, 61), name="ID"), raw, audit, y.rename(target_name)], axis=1)
    p = tmp_path / name
    if with_extra_header:
        extra = ",".join(["X"] * len(df.columns))
        p.write_text(extra + "\n" + df.to_csv(index=False))
    else:
        df.to_csv(p, index=False)
    return p


@pytest.mark.parametrize("extra,target", [(True, "default payment next month"),
                                          (False, "default.payment.next.month")])
def test_loader_handles_both_layouts(tmp_path, extra, target):
    X, y, audit, meta = load_public_dataset(_csv(tmp_path, "default credit card clients.csv", extra, target))
    assert X.shape == (60, 20) and list(audit.columns) == AUDIT_COLUMNS and meta["rows"] == 60
    assert y.name == PUBLIC_TARGET and set(y.unique()) <= {0, 1}


def test_loader_errors_are_clear(tmp_path, monkeypatch):
    with pytest.raises(DatasetNotFoundError):
        find_dataset(tmp_path / "nope.xls")
    monkeypatch.setenv("CREDITLENS_DATA_DIR", str(tmp_path))
    with pytest.raises(DatasetNotFoundError) as e:
        find_dataset()
    assert "archive.ics.uci.edu" in str(e.value)
    bad = tmp_path / "default credit card bad.csv"
    pd.DataFrame({"ID": [1], "AGE": [30]}).to_csv(bad, index=False)
    with pytest.raises(ValueError):
        load_public_dataset(bad)


REAL = None
try:
    REAL = find_dataset()
except DatasetNotFoundError:
    pass


@pytest.mark.skipif(REAL is None, reason="UCI file not present in backend/data")
def test_real_uci_file_matches_published_description():
    X, y, audit, meta = load_public_dataset()
    assert meta["rows"] == 30000 and X.shape == (30000, 20)
    assert round(meta["positive_rate"], 4) == 0.2212
    assert len(build_public_features(X)) == 30000       # every real row passes validation


# ---------------- training / artifact (fixture data) ----------------
@pytest.fixture(scope="module")
def public_run(trained_dir):
    models, reports = trained_dir / "models", trained_dir / "public_reports"
    rep = train_public(models, reports, data=fixture_frame(3000, 0), seed=5)
    return rep, models, reports


def test_split_sizes_and_no_overlap():
    y = (np.random.default_rng(0).random(1000) < 0.2).astype(int)
    sp = split_indices(y, 3)
    allidx = np.concatenate(list(sp.values()))
    assert len(allidx) == len(set(allidx)) == 1000


def test_training_is_reproducible(tmp_path):
    a = train_public(tmp_path / "m1", tmp_path / "r1", data=fixture_frame(1500, 2), seed=9)
    b = train_public(tmp_path / "m2", tmp_path / "r2", data=fixture_frame(1500, 2), seed=9)
    assert a["test_metrics_selected"] == b["test_metrics_selected"] and a["selected"] == b["selected"]


def test_calibration_evaluated_and_selection_uses_validation(public_run):
    rep, _, reports = public_run
    assert {r["calibration"] for r in rep["validation_candidates"]} == {"none", "sigmoid", "isotonic"}
    assert rep["validation_candidates"][0]["brier"] == min(r["brier"] for r in rep["validation_candidates"])
    assert (reports / "calibration_public_test.png").exists() and "majority_baseline" in rep
    assert "not_used_for_selection" in " ".join(rep.keys())


def test_artifact_metadata_and_reload_consistency(public_run):
    _, models, _ = public_run
    b1, b2 = load_public_bundle(models), load_public_bundle(models)
    assert b1.metadata["excluded_from_model_inputs"][:3] == AUDIT_COLUMNS
    assert "PUBLIC" in b1.metadata["data_provenance"] and "CC BY 4.0" in b1.metadata["data_provenance"]
    assert predict_public(b1, GOOD)["default_probability_next_month"] == \
        predict_public(b2, GOOD)["default_probability_next_month"]


def test_public_schema_mismatch_rejected(public_run, tmp_path):
    _, models, _ = public_run
    data = joblib.load(models / config.PUBLIC_ARTIFACT_NAME)
    data["metadata"]["feature_schema"]["columns"] = PUBLIC_FEATURE_COLUMNS[::-1]
    joblib.dump(data, tmp_path / config.PUBLIC_ARTIFACT_NAME)
    with pytest.raises(ModelNotAvailableError):
        load_public_bundle(tmp_path)


# ---------------- API ----------------
def test_public_predict_api_valid(public_run):
    r = client.post("/api/v1/assessments/predict-public", json=GOOD)
    assert r.status_code == 200
    b = r.json()
    assert 0 <= b["default_probability_next_month"] <= 1 and b["model_track"] == "public_uci_credit_card"
    assert "PUBLIC" in b["data_provenance"] and b["explanation"]["status"] == "available"
    assert any("2005" in l for l in b["limitations"])


def test_public_predict_api_rejects_invalid(public_run):
    assert client.post("/api/v1/assessments/predict-public", json={**GOOD, "PAY_0": 12}).status_code == 422
    assert client.post("/api/v1/assessments/predict-public", json={**GOOD, "AGE": 10}).status_code == 422
    assert client.post("/api/v1/assessments/predict-public",
                       json={k: v for k, v in GOOD.items() if k != "LIMIT_BAL"}).status_code == 422


def test_public_model_info_endpoint(public_run):
    body = client.get("/api/v1/models/public/active").json()
    assert body["dataset"]["licence"] and "SEX" in body["excluded_from_model_inputs"]


def test_public_api_missing_artifact_503(tmp_path, monkeypatch):
    monkeypatch.setenv("CREDITLENS_MODELS_DIR", str(tmp_path))
    r = client.post("/api/v1/assessments/predict-public", json=GOOD)
    assert r.status_code == 503 and "public_train" in r.json()["detail"]
