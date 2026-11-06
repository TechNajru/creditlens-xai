import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.experiments import VARIANTS, ece, limited_features, run_experiments
from app.main import app
from app.public_features import InvalidPublicInputError
from tests.test_public import GOOD, fixture_frame

client = TestClient(app)


def row(**kw):
    return pd.DataFrame([{**GOOD, **kw}])


def test_hidden_months_are_really_absent():
    k1 = limited_features(row(), 1)
    assert not any(c in k1.columns for c in ("PAY_2", "PAY_6", "BILL_AMT2", "PAY_AMT6"))
    assert {"PAY_0", "BILL_AMT1", "PAY_AMT1"} <= set(k1.columns)
    k3 = limited_features(row(), 3)
    assert "PAY_3" in k3.columns and "PAY_4" not in k3.columns and "BILL_AMT4" not in k3.columns
    assert list(limited_features(row(), 0).columns) == ["LIMIT_BAL", "AGE"]


def test_derived_features_use_only_visible_months():
    r = row(PAY_0=0, PAY_2=3, PAY_3=0, PAY_4=0, PAY_5=0, PAY_6=0)
    assert limited_features(r, 1).iloc[0]["months_delayed"] == 0        # the delay in month 2 is hidden
    assert limited_features(r, 2).iloc[0]["months_delayed"] == 1
    assert limited_features(r, 6).iloc[0]["months_delayed"] == 1


def test_invalid_input_still_rejected():
    with pytest.raises(InvalidPublicInputError):
        limited_features(row(PAY_0=99), 1)


def test_ece_known_values():
    # 10 equal-count bins; bin i has probability 0.1*i and exactly i positives out of 10 (perfectly calibrated)
    p = np.repeat(np.arange(10) * 0.1, 10)
    y = np.concatenate([np.r_[np.ones(i), np.zeros(10 - i)] for i in range(10)])
    assert ece(y, p) == pytest.approx(0.0, abs=1e-9)
    assert ece(y, p + 0.04) == pytest.approx(0.04)


@pytest.fixture(scope="module")
def exp_report(tmp_path_factory):
    out = tmp_path_factory.mktemp("exp")
    return run_experiments(out, data=fixture_frame(2500, 3), seed=3), out


def test_experiment_report_is_labelled_and_complete(exp_report):
    rep, out = exp_report
    assert (out / "experiments_public.json").exists()
    assert "not a validated thin-file evaluation" in rep["label"] and rep["evaluated_on"] == "untouched test split"
    assert [v["months_visible"] for v in rep["variants"]] == [k for k, _ in VARIANTS]
    assert rep["variants"][0]["roc_auc_change_vs_full"] == 0
    for v in rep["variants"]:
        lo, hi = v["roc_auc_ci95"]
        assert lo <= v["roc_auc"] <= hi and 0 <= v["ece"] <= 1 and v["n_features"] == len(v["features"])
    assert rep["variants"][-1]["n_features"] == 2 and "no selection among variants" in rep["recipe"]


def test_experiments_are_reproducible(exp_report, tmp_path):
    rep, _ = exp_report
    again = run_experiments(tmp_path, data=fixture_frame(2500, 3), seed=3)
    assert json.dumps(again, sort_keys=True) == json.dumps(rep, sort_keys=True)


def test_experiments_api(exp_report, tmp_path, monkeypatch):
    _, out = exp_report
    monkeypatch.setenv("CREDITLENS_REPORTS_DIR", str(out))
    assert client.get("/api/v1/models/public/experiments").json()["variants"]
    monkeypatch.setenv("CREDITLENS_REPORTS_DIR", str(tmp_path))
    assert client.get("/api/v1/models/public/experiments").status_code == 404
