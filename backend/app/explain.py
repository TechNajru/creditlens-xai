"""Model explanations with SHAP (PermutationExplainer, model-agnostic).

What the numbers mean (and do not mean)
- The explained quantity is the model's UNCALIBRATED risk score (a probability-scale number from the
  fitted pipeline). baseline + sum(contributions) == that score, which we verify for every explanation.
- The probability shown to users is a monotone recalibration of that score. So contributions are NOT
  percentage-point changes to the displayed probability.
- SHAP describes how the model uses its inputs relative to a background sample of training rows.
  It does not show causation, and correlated inputs share credit.
- If the explainer cannot run or fails its consistency check, we return status "unavailable".
  We never invent an explanation.
"""
from __future__ import annotations

import logging
import os

import numpy as np
import pandas as pd
import shap

logger = logging.getLogger("creditlens")

EXPLANATION_VERSION = "shap-permutation-v1"
METHOD = "SHAP PermutationExplainer (model-agnostic, independent background samples)"
SCALE = "uncalibrated model risk score (probability scale, before calibration)"
BACKGROUND_ROWS = 100
CONSISTENCY_TOL = 1e-6
MIN_REASON_CONTRIBUTION = 1e-4

NOTES = [
    "Contributions add up to the model's raw risk score, starting from a baseline (the average raw score "
    "on a background sample of training rows).",
    "The displayed probability is a calibrated version of that raw score, so contributions are not "
    "percentage-point changes to it.",
    "These are associations learned by the model, not causes. Correlated inputs share credit.",
]


class ExplanationUnavailable(RuntimeError):
    pass


def global_rows() -> int:
    return int(os.getenv("CREDITLENS_GLOBAL_SHAP_ROWS", "200"))


def _make_explainer(pipeline, background: pd.DataFrame, columns: list[str], seed: int):
    def predict(data):
        return pipeline.predict_proba(pd.DataFrame(data, columns=columns))[:, 1]
    return shap.PermutationExplainer(predict, shap.maskers.Independent(background), seed=seed), predict


def fit_explanation_assets(pipeline, X_train: pd.DataFrame, X_eval: pd.DataFrame, seed: int):
    """Called at training time. Returns (background rows, global importance summary)."""
    columns = list(X_train.columns)
    background = X_train.sample(min(BACKGROUND_ROWS, len(X_train)), random_state=seed).reset_index(drop=True)
    sample = X_eval.sample(min(global_rows(), len(X_eval)), random_state=seed)
    explainer, _ = _make_explainer(pipeline, background, columns, seed)
    sv = explainer(sample.to_numpy(dtype=float), max_evals=2 * len(columns) + 1)
    imp = np.abs(sv.values).mean(axis=0)
    values = sorted(({"feature": c, "mean_abs_shap": float(v)} for c, v in zip(columns, imp)),
                    key=lambda r: -r["mean_abs_shap"])
    return background, {"method": METHOD, "version": EXPLANATION_VERSION, "scale": SCALE,
                        "n_rows": int(len(sample)), "computed_on": "sample of the validation split",
                        "note": "Mean absolute contribution per feature. It describes the model, not causes.",
                        "values": values}


def explain_row(bundle, X: pd.DataFrame, describe, detail: str = "summary") -> dict:
    if getattr(bundle, "background", None) is None:
        raise ExplanationUnavailable("This model artifact has no explanation background. Retrain to enable explanations.")
    columns = bundle.metadata["feature_schema"]["columns"]
    seed = int(bundle.metadata.get("seed", 0))
    explainer, predict = _make_explainer(bundle.pipeline, bundle.background, columns, seed)
    x = X[columns].to_numpy(dtype=float)
    sv = explainer(x, max_evals=2 * len(columns) + 1)
    base, values = float(sv.base_values[0]), sv.values[0]
    output = float(predict(x)[0])
    if abs(base + float(values.sum()) - output) > CONSISTENCY_TOL:
        raise ExplanationUnavailable("Explanation failed its additivity check and was withheld.")

    items = []
    for name, c in zip(columns, values):
        label, shown = describe(name, X.iloc[0][name])
        items.append({"feature": name, "label": label, "value_display": shown, "contribution": float(c),
                      "direction": "increases_risk_score" if c > 0 else "decreases_risk_score"})
    items.sort(key=lambda r: -abs(r["contribution"]))
    up = [i for i in items if i["contribution"] > MIN_REASON_CONTRIBUTION]
    down = [i for i in items if i["contribution"] < -MIN_REASON_CONTRIBUTION]
    reasons = [f"{i['label']}: {i['value_display']} — "
               f"{'raised' if i['contribution'] > 0 else 'lowered'} the model's risk score"
               for i in (up[:3] + down[:3])]
    out = {"status": "available", "method": METHOD, "version": EXPLANATION_VERSION,
           "shap_version": shap.__version__, "scale": SCALE, "baseline": base, "model_output": output,
           "top_risk_increasing": up[:3], "top_risk_reducing": down[:3], "reason_codes": reasons,
           "notes": NOTES, "detail": detail}
    if detail == "full":
        out["contributions"] = items
        out["global_importance"] = bundle.metadata.get("global_importance")
    return out


def safe_explanation(bundle, X: pd.DataFrame, describe, detail: str = "summary") -> dict:
    try:
        return explain_row(bundle, X, describe, detail)
    except ExplanationUnavailable as exc:
        return {"status": "unavailable", "reason": str(exc)}
    except Exception as exc:  # explainer failure must never break prediction or invent output
        logger.warning("explanation failed: %s", type(exc).__name__)
        return {"status": "unavailable", "reason": "The explanation could not be computed for this input."}
