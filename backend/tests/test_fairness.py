import json

import numpy as np
import pandas as pd
import pytest
from fairlearn.metrics import (demographic_parity_difference, equalized_odds_difference, false_negative_rate,
                               false_positive_rate, selection_rate)
from fastapi.testclient import TestClient

from app import fairness
from app.fairness import (MIN_GROUP_N, choose_threshold, disparity_summary, group_table, group_series, run_fairness_audit,
                          wilson)
from app.main import app
from app.public_train import split_indices
from tests.test_public import fixture_frame, public_run  # noqa: F401

client = TestClient(app)


def toy(n=800, seed=1):
    rng = np.random.default_rng(seed)
    g = pd.Series(rng.choice(["a", "b"], n, p=[0.6, 0.4]))
    p = np.clip(rng.beta(2, 5, n) + 0.1 * (g == "b"), 0, 1)
    y = (rng.random(n) < p).astype(int)
    return y, (p >= 0.3).astype(int), p, g


def test_wilson_interval_known_values():
    lo, hi = wilson(50, 100)
    assert lo == pytest.approx(0.4038, abs=1e-3) and hi == pytest.approx(0.5962, abs=1e-3)
    assert wilson(0, 0) is None
    lo0, hi0 = wilson(0, 50)
    assert lo0 == 0.0 and 0 < hi0 < 0.1


def test_threshold_is_the_f1_maximiser_on_given_data():
    y = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    p = np.array([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9])
    t = choose_threshold(y, p)
    assert 0.41 <= t <= 0.60            # any cut between 0.4 and 0.6 separates the classes perfectly


def test_group_metrics_match_fairlearn():
    y, pred, p, g = toy()
    rows = {r["group"]: r for r in group_table(y, pred, p, g)}
    for grp in ("a", "b"):
        m = (g == grp).to_numpy()
        assert rows[grp]["flagged_rate"]["value"] == pytest.approx(selection_rate(y[m], pred[m]))
        assert rows[grp]["false_positive_rate"]["value"] == pytest.approx(false_positive_rate(y[m], pred[m]))
        assert rows[grp]["false_negative_rate"]["value"] == pytest.approx(false_negative_rate(y[m], pred[m]))
        assert rows[grp]["favourable_rate"]["value"] == pytest.approx(1 - rows[grp]["flagged_rate"]["value"])
        assert rows[grp]["calibration_gap"] == pytest.approx(p[m].mean() - y[m].mean())
        lo, hi = rows[grp]["flagged_rate"]["ci95"]
        assert lo <= rows[grp]["flagged_rate"]["value"] <= hi
    assert sum(r["n"] for r in rows.values()) == len(y)


def test_disparity_summary_matches_fairlearn_and_ignores_small_groups():
    y, pred, p, g = toy(900)
    g = g.copy()
    g.iloc[:20] = "tiny"                                     # a group far below MIN_GROUP_N
    s = disparity_summary(y, pred, g)
    keep = (g != "tiny").to_numpy()
    assert s["groups_excluded_small"] == ["tiny"] and "tiny" not in s["groups_included"]
    assert s["demographic_parity_difference"] == pytest.approx(demographic_parity_difference(y[keep], pred[keep], sensitive_features=g[keep]))
    assert s["equalized_odds_difference"] == pytest.approx(equalized_odds_difference(y[keep], pred[keep], sensitive_features=g[keep]))
    rows = {r["group"]: r for r in group_table(y, pred, p, g)}
    assert rows["tiny"]["reliable"] is False and any("small group" in w for w in rows["tiny"]["warnings"])
    assert rows["a"]["reliable"] is True


def test_single_group_cannot_produce_disparity():
    y, pred, p, g = toy()
    s = disparity_summary(y, pred, pd.Series(["only"] * len(y)))
    assert s["computed"] is False


def test_group_labels_and_age_bins():
    audit = pd.DataFrame({"SEX": [1, 2, 2], "EDUCATION": [1, 5, 0], "MARRIAGE": [1, 0, 3]})
    g = group_series(audit, pd.Series([25, 35, 61]))
    assert list(g["SEX"]) == ["male", "female", "female"]
    assert list(g["EDUCATION"]) == ["graduate school", "undocumented code", "undocumented code"]
    assert list(g["MARRIAGE"]) == ["married", "undocumented code", "others"]
    assert list(g["AGE_GROUP"]) == ["under 30", "30-39", "50+"]


@pytest.fixture(scope="module")
def audit_run(public_run, tmp_path_factory):  # noqa: F811
    _, models, _ = public_run
    raw, y, audit, meta = fixture_frame(3000, 0)
    audit = audit.copy()
    audit.loc[:25, "EDUCATION"] = 5                          # rare undocumented code -> small group
    out = tmp_path_factory.mktemp("fair")
    rep = run_fairness_audit(models, out, data=(raw, y, audit, meta), seed=5)
    return rep, models, out, (raw, y, audit, meta)


def test_report_structure_and_definitions(audit_run):
    rep, _, out, _ = audit_run
    assert (out / "fairness_public.json").exists()
    assert set(rep["attributes"]) == {"SEX", "EDUCATION", "MARRIAGE", "AGE_GROUP"}
    assert "flags the client" in rep["definitions"]["positive_prediction"]
    assert rep["evaluated_on"] == "untouched test split" and rep["threshold"]["experimental"] is True
    assert any("proxy bias" in c for c in rep["caveats"]) and any("No single metric" in c for c in rep["caveats"])
    for a in rep["attributes"].values():
        assert sum(g["n"] for g in a["groups"]) == rep["n_test"]


def test_small_groups_are_flagged_in_the_report(audit_run):
    rep, *_ = audit_run
    edu = rep["attributes"]["EDUCATION"]
    small = [g for g in edu["groups"] if g["n"] < MIN_GROUP_N]
    assert small and all(not g["reliable"] and g["warnings"] for g in small)
    assert set(g["group"] for g in small) <= set(edu["summary"]["groups_excluded_small"])


def test_threshold_comes_from_validation_and_metrics_from_test(audit_run):
    rep, models, _, (raw, y, audit, meta) = audit_run
    from app.predict import ModelBundle  # noqa: F401
    from app.public_features import build_public_features
    from app.public_predict import load_public_bundle
    b = load_public_bundle(models)
    sp = split_indices(y.to_numpy(), 5)
    X = build_public_features(raw)
    p_val = b.calibrator.transform(b.pipeline.predict_proba(X.iloc[sp["validation"]])[:, 1])
    assert rep["threshold"]["value"] == choose_threshold(y.to_numpy()[sp["validation"]], p_val)
    assert rep["n_test"] == len(sp["test"]) and rep["threshold"]["chosen_on"] == "validation split"


def test_mitigation_is_labelled_experimental_and_not_deployed(audit_run):
    rep, *_ = audit_run
    m = rep["mitigation"]
    assert m["deployed"] is False and m["attribute"] == "SEX" and "ThresholdOptimizer" in m["method"]
    assert any("protected attributes" in i for i in m["implications"])
    assert "Not applicable" in m["mitigated"]["calibration"]
    assert {t["metric"] for t in m["tradeoffs"]} >= {"balanced_accuracy", "favourable_rate (coverage)", "equalized_odds_difference (SEX)"}
    assert 0 <= m["mitigated"]["overall"]["accuracy"] <= 1


def test_audit_is_reproducible(audit_run, tmp_path):
    rep, models, _, data = audit_run
    again = run_fairness_audit(models, tmp_path, data=data, seed=5)
    assert json.dumps(again, sort_keys=True) == json.dumps(rep, sort_keys=True)


def test_fairness_api(audit_run, tmp_path, monkeypatch):
    _, _, out, _ = audit_run
    monkeypatch.setenv("CREDITLENS_REPORTS_DIR", str(out))
    body = client.get("/api/v1/fairness/public").json()
    assert body["mitigation"]["deployed"] is False
    monkeypatch.setenv("CREDITLENS_REPORTS_DIR", str(tmp_path))
    r = client.get("/api/v1/fairness/public")
    assert r.status_code == 404 and "python -m app.fairness" in r.json()["detail"]


def test_module_constants_are_sane():
    assert fairness.MIN_GROUP_N >= 50 and fairness.MIN_CLASS_N >= 20


def test_model_card_reflects_the_fairness_audit(audit_run, trained_dir):
    import shutil
    from app.model_card import render_model_card
    _, models, out, _ = audit_run
    shutil.copy(trained_dir / "public_reports" / "evaluation_public.json", out / "evaluation_public.json")
    card = render_model_card("public", models, out)
    assert "A Fairlearn audit exists" in card and "NOT deployed" in card and "does not show the model is fair" in card
    assert "SEX: demographic parity difference" in card
    sim = render_model_card("simulation", models, trained_dir / "reports")
    assert "No fairness assessment has been performed" in sim


def test_caveats_state_that_age_is_a_model_input(audit_run):
    rep, *_ = audit_run
    assert any("AGE IS a model input" in c for c in rep["caveats"])
