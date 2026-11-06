"""Fairness audit for the PUBLIC-DATA model (UCI credit-card default), using Fairlearn.

Run from backend/:   python -m app.fairness        (after python -m app.public_train)

Definitions (stated in the report and the UI)
- Positive prediction = the model FLAGS a client as high default risk (probability >= threshold).
- Favourable outcome for the client = NOT flagged (would pass a demo screen).
  Fairlearn's "selection rate" is therefore the FLAGGED rate; favourable rate = 1 - flagged rate.
- Harm that matters most: false positives (flagged but did not default), which could wrongly deny a client.
  False negatives (missed defaults) mostly burden a lender, but are reported too.
- The threshold is chosen on the VALIDATION split (max F1) and all group metrics are computed on the
  untouched TEST split. It is experimental, not a policy.

Honest limits: dropping SEX/EDUCATION/MARRIAGE from model inputs does not remove proxy bias; group
estimates from small groups are unreliable (flagged, with 95% Wilson intervals); no single metric proves
fairness; group-specific thresholds are evaluated only as an experiment and are NOT applied anywhere.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from fairlearn.metrics import (demographic_parity_difference, demographic_parity_ratio,
                               equalized_odds_difference, false_negative_rate, false_positive_rate,
                               selection_rate)
from fairlearn.postprocessing import ThresholdOptimizer
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, brier_score_loss, f1_score,
                             precision_score, recall_score)

from . import config
from .public_data import load_public_dataset
from .public_features import build_public_features
from .public_train import split_indices

MIN_GROUP_N = 100       # smaller groups are reported but excluded from disparity summaries
MIN_CLASS_N = 30        # FPR needs >= 30 non-defaulters, FNR needs >= 30 defaulters in the group
Z95 = 1.96

SEX = {1: "male", 2: "female"}
EDUCATION = {1: "graduate school", 2: "university", 3: "high school", 4: "others"}
MARRIAGE = {1: "married", 2: "single", 3: "others"}
LABEL_NOTE = ("Group labels follow the UCI variable documentation. Codes 0, 5 and 6 (EDUCATION) and 0 (MARRIAGE) "
              "occur in the data but are undefined by UCI; they are grouped as 'undocumented code'.")

DEFINITIONS = {
    "positive_prediction": "The model flags the client as high default risk (probability at or above the threshold).",
    "favourable_outcome": "Not flagged. Favourable rate = 1 - flagged rate.",
    "flagged_rate": "Fairlearn 'selection rate': share of the group that is flagged.",
    "false_positive_rate": "Among clients who did NOT default, the share who were flagged (possible wrongful denial).",
    "false_negative_rate": "Among clients who DID default, the share who were not flagged (missed defaults).",
    "calibration_gap": "Mean predicted probability minus observed default rate in the group (0 is ideal).",
    "demographic_parity_difference": "Largest gap between groups in flagged rate.",
    "equalized_odds_difference": "Larger of the largest gaps in false-positive rate and true-positive rate across groups.",
}


def wilson(k: int, n: int, z: float = Z95) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [max(0.0, centre - half), min(1.0, centre + half)]


def choose_threshold(y_val: np.ndarray, p_val: np.ndarray) -> float:
    grid = np.round(np.arange(0.05, 0.96, 0.01), 2)
    scores = [f1_score(y_val, (p_val >= t).astype(int), zero_division=0) for t in grid]
    return float(grid[int(np.argmax(scores))])


def group_series(audit: pd.DataFrame, age: pd.Series) -> dict[str, pd.Series]:
    def lab(col, mapping):
        return audit[col].map(lambda v: mapping.get(int(v), "undocumented code")).astype(object)
    bins = pd.cut(age, [17, 29, 39, 49, 200], labels=["under 30", "30-39", "40-49", "50+"]).astype(object)
    return {"SEX": lab("SEX", SEX), "EDUCATION": lab("EDUCATION", EDUCATION),
            "MARRIAGE": lab("MARRIAGE", MARRIAGE), "AGE_GROUP": bins}


def _rate(k, n):
    return {"value": k / n if n else None, "ci95": wilson(int(k), int(n)), "n": int(n)}


def group_table(y: np.ndarray, pred: np.ndarray, p: np.ndarray, groups: pd.Series) -> list[dict]:
    rows = []
    for g in sorted(groups.dropna().unique(), key=str):
        m = (groups == g).to_numpy()
        yy, pr, pp = y[m], pred[m], p[m]
        n, pos, neg = int(m.sum()), int(yy.sum()), int((1 - yy).sum())
        fp, fn, tp = int(((pr == 1) & (yy == 0)).sum()), int(((pr == 0) & (yy == 1)).sum()), int(((pr == 1) & (yy == 1)).sum())
        reliable_group = n >= MIN_GROUP_N
        fpr_ok, fnr_ok = neg >= MIN_CLASS_N, pos >= MIN_CLASS_N
        warnings = []
        if not reliable_group:
            warnings.append(f"small group (n={n} < {MIN_GROUP_N}): estimates are unreliable")
        if reliable_group and not fpr_ok:
            warnings.append("too few non-defaulters for a reliable false-positive rate")
        if reliable_group and not fnr_ok:
            warnings.append("too few defaulters for a reliable false-negative rate")
        rows.append({
            "group": str(g), "n": n, "defaulters": pos, "non_defaulters": neg,
            "reliable": bool(reliable_group),
            "flagged_rate": _rate(int(pr.sum()), n), "favourable_rate": _rate(n - int(pr.sum()), n),
            "observed_default_rate": _rate(pos, n),
            "false_positive_rate": {**_rate(fp, neg), "reliable": bool(fpr_ok)},
            "false_negative_rate": {**_rate(fn, pos), "reliable": bool(fnr_ok)},
            "recall": tp / pos if pos else None,
            "precision": tp / int(pr.sum()) if pr.sum() else None,
            "mean_predicted_probability": float(pp.mean()),
            "calibration_gap": float(pp.mean() - yy.mean()),
            "calibration_gap_reliable": bool(reliable_group and pos >= MIN_CLASS_N),
            "brier": float(brier_score_loss(yy, np.clip(pp, 0, 1))) if n else None,
            "warnings": warnings,
        })
    return rows


def disparity_summary(y, pred, groups: pd.Series) -> dict:
    sizes = groups.value_counts()
    keep = groups.isin(sizes[sizes >= MIN_GROUP_N].index).to_numpy()
    excluded = sorted(str(g) for g in sizes[sizes < MIN_GROUP_N].index)
    if len(set(groups[keep])) < 2:
        return {"computed": False, "reason": "fewer than two groups meet the minimum size", "groups_excluded_small": excluded}
    g, yy, pr = groups[keep], y[keep], pred[keep]
    return {
        "computed": True, "groups_included": sorted(str(x) for x in set(g)), "groups_excluded_small": excluded,
        "demographic_parity_difference": float(demographic_parity_difference(yy, pr, sensitive_features=g)),
        "demographic_parity_ratio": float(demographic_parity_ratio(yy, pr, sensitive_features=g)),
        "equalized_odds_difference": float(equalized_odds_difference(yy, pr, sensitive_features=g)),
        "false_positive_rate_difference": _gap(yy, pr, g, false_positive_rate),
        "false_negative_rate_difference": _gap(yy, pr, g, false_negative_rate),
    }


def _gap(y, pred, g, fn):
    vals = [fn(y[(g == x).to_numpy()], pred[(g == x).to_numpy()]) for x in set(g)]
    return float(max(vals) - min(vals))


class CalibratedScorer(BaseEstimator, ClassifierMixin):
    """Wraps the trained pipeline + calibrator so Fairlearn can post-process its probabilities."""

    def __init__(self, pipeline=None, calibrator=None):
        self.pipeline, self.calibrator = pipeline, calibrator
        self.classes_ = np.array([0, 1])

    def fit(self, X, y=None):
        return self

    def __sklearn_is_fitted__(self):
        return True

    def predict_proba(self, X):
        p = self.calibrator.transform(self.pipeline.predict_proba(X)[:, 1])
        return np.column_stack([1 - p, p])

    def predict(self, X):
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


def overall_metrics(y, pred, p=None) -> dict:
    out = {"accuracy": float(accuracy_score(y, pred)), "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
           "precision": float(precision_score(y, pred, zero_division=0)), "recall": float(recall_score(y, pred, zero_division=0)),
           "f1": float(f1_score(y, pred, zero_division=0)), "flagged_rate": float(pred.mean()),
           "favourable_rate": float(1 - pred.mean())}
    if p is not None:
        out["brier"] = float(brier_score_loss(y, np.clip(p, 0, 1)))
    return out


def run_fairness_audit(models_dir: Path | None = None, reports_dir: Path | None = None,
                       data=None, data_path=None, seed: int | None = None) -> dict:
    models_dir, reports_dir = Path(models_dir or config.models_dir()), Path(reports_dir or config.reports_dir())
    reports_dir.mkdir(parents=True, exist_ok=True)
    art = joblib.load(models_dir / config.PUBLIC_ARTIFACT_NAME)
    pipe, cal, meta = art["pipeline"], art["calibrator"], art["metadata"]
    seed = int(meta["seed"]) if seed is None else seed
    raw, y_s, audit, _ = data if data is not None else load_public_dataset(data_path)
    X, y = build_public_features(raw), y_s.to_numpy()
    sp = split_indices(y, seed)                      # identical to training splits (same seed)
    scorer = CalibratedScorer(pipe, cal)
    p_val = scorer.predict_proba(X.iloc[sp["validation"]])[:, 1]
    threshold = choose_threshold(y[sp["validation"]], p_val)

    te = sp["test"]
    X_te, y_te, p_te = X.iloc[te], y[te], scorer.predict_proba(X.iloc[te])[:, 1]
    pred_te = (p_te >= threshold).astype(int)
    groups = group_series(audit.iloc[te].reset_index(drop=True), raw.iloc[te]["AGE"].reset_index(drop=True))

    attributes = {}
    for name, g in groups.items():
        table = group_table(y_te, pred_te, p_te, g)
        attributes[name] = {"groups": table, "summary": disparity_summary(y_te, pred_te, g),
                            "warnings": sorted({w for r in table for w in r["warnings"]})}

    # ---- one mitigation experiment: equalized-odds post-processing on SEX (NOT deployed) ----
    sex_val = audit.iloc[sp["validation"]]["SEX"].map(lambda v: SEX.get(int(v), "undocumented code")).to_numpy()
    sex_te = groups["SEX"].to_numpy()
    scorer_t = CalibratedScorer(pipe, cal)
    opt = ThresholdOptimizer(estimator=scorer_t, constraints="equalized_odds", objective="balanced_accuracy_score",
                             prefit=True, predict_method="predict_proba")
    opt.fit(X.iloc[sp["validation"]], y[sp["validation"]], sensitive_features=sex_val)
    mit_pred = np.asarray(opt.predict(X_te, sensitive_features=sex_te, random_state=seed)).astype(int)
    mit_tables = group_table(y_te, mit_pred, p_te, groups["SEX"])
    mitigation = {
        "attribute": "SEX",
        "method": "Fairlearn ThresholdOptimizer: post-processing to equalized odds with randomized group-specific thresholds",
        "fit_on": "validation split", "evaluated_on": "test split", "deployed": False,
        "baseline": {"overall": overall_metrics(y_te, pred_te, p_te), "disparity": attributes["SEX"]["summary"],
                     "groups": attributes["SEX"]["groups"]},
        "mitigated": {"overall": overall_metrics(y_te, mit_pred), "disparity": disparity_summary(y_te, mit_pred, groups["SEX"]),
                      "groups": mit_tables,
                      "calibration": "Not applicable: mitigated output is a randomized yes/no decision, not a probability."},
        "implications": [
            "It needs each client's SEX at decision time. Using protected attributes to set decisions or "
            "thresholds may be unlawful or unethical in lending, depending on jurisdiction. This is an analysis only.",
            "Equalizing error rates between groups usually costs overall accuracy or changes how many clients are flagged "
            "(see trade-offs). Whether that trade is acceptable is a policy and legal decision, not a technical one.",
            "Decisions are randomized for some clients, so two identical clients in the same group can be treated differently.",
            "It does not remove proxy bias in the underlying model; it only adjusts final decisions.",
        ],
    }
    b, m = mitigation["baseline"], mitigation["mitigated"]
    mitigation["tradeoffs"] = [
        {"metric": "balanced_accuracy", "baseline": b["overall"]["balanced_accuracy"], "mitigated": m["overall"]["balanced_accuracy"]},
        {"metric": "accuracy", "baseline": b["overall"]["accuracy"], "mitigated": m["overall"]["accuracy"]},
        {"metric": "favourable_rate (coverage)", "baseline": b["overall"]["favourable_rate"], "mitigated": m["overall"]["favourable_rate"]},
        {"metric": "equalized_odds_difference (SEX)", "baseline": b["disparity"].get("equalized_odds_difference"),
         "mitigated": m["disparity"].get("equalized_odds_difference")},
        {"metric": "demographic_parity_difference (SEX)", "baseline": b["disparity"].get("demographic_parity_difference"),
         "mitigated": m["disparity"].get("demographic_parity_difference")},
    ]

    report = {
        "model_version": meta["model_version"], "data_provenance": meta["data_provenance"],
        "threshold": {"value": threshold, "chosen_on": "validation split", "criterion": "maximum F1",
                      "experimental": True},
        "evaluated_on": "untouched test split", "n_test": int(len(te)),
        "definitions": DEFINITIONS, "label_note": LABEL_NOTE,
        "limits": {"min_group_n": MIN_GROUP_N, "min_class_n": MIN_CLASS_N, "intervals": "95% Wilson score intervals"},
        "attributes": attributes, "mitigation": mitigation,
        "caveats": [
            "Dropping sensitive columns from the model's inputs does not remove proxy bias; this audit measures outcomes.",
            "No single metric proves fairness. Metrics can conflict, and differences smaller than the intervals may be noise.",
            "Small groups have unreliable estimates; they are flagged and excluded from disparity summaries.",
            "Group differences in observed default rates may reflect real differences, data collection effects or historical bias; this audit cannot tell which.",
            "2005 Taiwan credit-card data: results do not transfer to other populations or products.",
            "SEX, EDUCATION and MARRIAGE are used only for this audit and are not model inputs. AGE IS a model input and is also audited by age group; age-based credit decisions are restricted in some jurisdictions.",
            "Access to this report should be restricted (access control arrives with authentication).",
        ],
    }
    (reports_dir / "fairness_public.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    r = run_fairness_audit()
    print("Threshold (chosen on validation):", r["threshold"]["value"], "| test rows:", r["n_test"])
    for name, a in r["attributes"].items():
        s = a["summary"]
        print(f"{name}: groups={[(g['group'], g['n']) for g in a['groups']]}")
        if s["computed"]:
            print(f"   DPD={s['demographic_parity_difference']:.3f}  EOD={s['equalized_odds_difference']:.3f}")
    print("Mitigation trade-offs:", json.dumps(r["mitigation"]["tradeoffs"], indent=1))
    print("Saved:", config.reports_dir() / "fairness_public.json")
