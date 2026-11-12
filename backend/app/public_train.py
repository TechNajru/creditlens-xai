"""Train, calibrate, select and evaluate the PUBLIC-DATA risk model (UCI credit-card default).

Run from backend/:   python -m app.public_train

Same protocol as the simulation model, but a SEPARATE model and artifact:
  train 55% -> fit pipelines | calibration 15% -> fit calibrators |
  validation 15% -> choose model + calibrator by Brier score | test 15% -> untouched until the end
Random stratified splits only: the dataset is a single snapshot, so no temporal split is possible
(this limits how far the metrics can be trusted for the future).
"""
from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib
import numpy as np
import pandas as pd
import sklearn
from sklearn.calibration import calibration_curve
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from . import config
from .calibration import CALIBRATORS
from .explain import fit_explanation_assets
from .public_data import SOURCE, load_public_dataset
from .public_features import AUDIT_COLUMNS, PUBLIC_FEATURE_COLUMNS, build_public_features
from .train import THRESHOLDS, probability_metrics, threshold_metrics

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def make_public_candidates(seed: int) -> dict[str, Pipeline]:
    return {
        "logistic_regression": Pipeline([
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
            ("model", LogisticRegression(max_iter=3000, random_state=seed)),
        ]),
        "random_forest": Pipeline([
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("model", RandomForestClassifier(n_estimators=300, min_samples_leaf=30,
                                             random_state=seed, n_jobs=-1)),
        ]),
        "hist_gradient_boosting": Pipeline([
            ("model", HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05,
                                                     max_leaf_nodes=15, random_state=seed)),
        ]),
    }


def split_indices(y: np.ndarray, seed: int) -> dict[str, np.ndarray]:
    idx = np.arange(len(y))
    rest, test = train_test_split(idx, test_size=0.15, stratify=y, random_state=seed)
    rest, val = train_test_split(rest, test_size=0.15 / 0.85, stratify=y[rest], random_state=seed)
    train, calib = train_test_split(rest, test_size=0.15 / 0.70, stratify=y[rest], random_state=seed)
    return {"train": train, "calibration": calib, "validation": val, "test": test}


def train_public(models_dir: Path | None = None, reports_dir: Path | None = None,
                 data=None, data_path=None, seed: int | None = None) -> dict:
    """`data` may be a (raw_features, y, audit, meta) tuple (used by tests); otherwise the real file is loaded."""
    seed = config.default_seed() if seed is None else seed
    models_dir = Path(models_dir or config.models_dir()); reports_dir = Path(reports_dir or config.reports_dir())
    models_dir.mkdir(parents=True, exist_ok=True); reports_dir.mkdir(parents=True, exist_ok=True)

    raw, y_s, audit, meta = data if data is not None else load_public_dataset(data_path)
    X = build_public_features(raw)
    y = y_s.to_numpy()
    if list(X.columns) != PUBLIC_FEATURE_COLUMNS or set(AUDIT_COLUMNS) & set(X.columns):    # explicit check: asserts vanish under python -O
        raise ValueError("Leakage guard failed: sensitive audit columns are in the features, or the feature order changed.")
    sp = split_indices(y, seed)
    X_tr, y_tr = X.iloc[sp["train"]], y[sp["train"]]
    X_ca, y_ca = X.iloc[sp["calibration"]], y[sp["calibration"]]
    X_va, y_va = X.iloc[sp["validation"]], y[sp["validation"]]
    X_te, y_te = X.iloc[sp["test"]], y[sp["test"]]

    fitted, table = {}, []
    for name, pipe in make_public_candidates(seed).items():
        pipe.fit(X_tr, y_tr)
        p_ca, p_va = pipe.predict_proba(X_ca)[:, 1], pipe.predict_proba(X_va)[:, 1]
        for cname, cls in CALIBRATORS.items():
            cal = cls().fit(p_ca, y_ca)
            fitted[(name, cname)] = (pipe, cal)
            table.append({"model": name, "calibration": cname,
                          **probability_metrics(y_va, cal.transform(p_va))})
    best = min(table, key=lambda r: r["brier"])
    pipe, cal = fitted[(best["model"], best["calibration"])]

    # Test split: used only after selection. Each model's own best-on-validation calibrator is
    # reported for comparison; this is NOT used to choose anything.
    test_all = {}
    for name in make_public_candidates(seed):
        bc = min((r for r in table if r["model"] == name), key=lambda r: r["brier"])
        pp, cc = fitted[(name, bc["calibration"])]
        test_all[name] = {"calibration": bc["calibration"],
                          **probability_metrics(y_te, cc.transform(pp.predict_proba(X_te)[:, 1]))}
    p_te = cal.transform(pipe.predict_proba(X_te)[:, 1])
    base = float(np.mean(y_tr))
    baseline = {"description": "Majority-class / constant base-rate predictor (fit on train labels)",
                "accuracy_always_negative": float(1 - np.mean(y_te)),
                "brier_constant_base_rate": float(brier_score_loss(y_te, np.full(len(y_te), base))),
                "log_loss_constant_base_rate": float(log_loss(y_te, np.full(len(y_te), base)))}
    frac, mean_p = calibration_curve(y_te, p_te, n_bins=10, strategy="quantile")
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], "--", color="gray", label="Perfect calibration")
    ax.plot(mean_p, frac, "o-", label=f"{best['model']} + {best['calibration']}")
    ax.set_xlabel("Mean predicted default probability"); ax.set_ylabel("Observed default rate")
    ax.set_title("Calibration, untouched test split (UCI public data)"); ax.legend(); fig.tight_layout()
    fig.savefig(reports_dir / "calibration_public_test.png", dpi=120); plt.close(fig)

    background, global_importance = fit_explanation_assets(pipe, X_tr, X_va, seed)
    version = f"uci-{best['model']}-{best['calibration']}-seed{seed}-{config.PUBLIC_SCHEMA_VERSION}"
    metadata = {
        "model_version": version, "model_name": best["model"], "calibration_method": best["calibration"],
        "calibration_evaluated": True,
        "feature_schema": {"version": config.PUBLIC_SCHEMA_VERSION, "columns": PUBLIC_FEATURE_COLUMNS},
        "data_provenance": f"PUBLIC data: UCI {SOURCE['name']} ({SOURCE['creator']}), {SOURCE['licence']}",
        "dataset": {k: meta.get(k) for k in ("name", "creator", "url", "doi", "licence", "population",
                                              "label", "rows", "positive_rate", "duplicate_rows_excluding_id")},
        "target_definition": "Default payment in the month after the 6-month observation window (1 = yes).",
        "excluded_from_model_inputs": AUDIT_COLUMNS + ["ID"], "seed": seed,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "library_versions": {"python": platform.python_version(), "scikit-learn": sklearn.__version__,
                             "pandas": pd.__version__, "numpy": np.__version__},
        "selection_criterion": "lowest validation Brier score across model x calibrator combinations",
        "global_importance": global_importance,
        "limitations": [
            "Trained on 2005 Taiwan credit-card clients (NT dollars); not validated for other populations, "
            "years, currencies or loan products.",
            "Predicts a credit-card payment default in the next month, not a loan default or approval.",
            "Random stratified split of a single snapshot: no temporal validation was possible.",
            "Not a credit-bureau score. Thresholds in reports are experimental.",
            "SEX, EDUCATION and MARRIAGE are excluded from inputs, but proxy bias can remain.",
        ],
    }
    joblib.dump({"pipeline": pipe, "calibrator": cal, "metadata": metadata, "background": background},
                models_dir / config.PUBLIC_ARTIFACT_NAME)
    report = {
        "model_version": version, "data_provenance": metadata["data_provenance"], "dataset": metadata["dataset"],
        "split_sizes": {k: int(len(v)) for k, v in sp.items()},
        "positive_rate": {k: float(np.mean(y[v])) for k, v in sp.items()},
        "validation_candidates": sorted(table, key=lambda r: r["brier"]),
        "selected": {"model": best["model"], "calibration": best["calibration"]},
        "test_metrics_selected": probability_metrics(y_te, p_te),
        "test_metrics_all_models_not_used_for_selection": test_all,
        "test_threshold_tradeoffs": [threshold_metrics(y_te, p_te, t) for t in THRESHOLDS],
        "majority_baseline": baseline,
        "calibration_curve_test": {"mean_predicted": mean_p.tolist(), "fraction_positive": frac.tolist()},
        "global_importance": global_importance,
        "limitations": metadata["limitations"],
        "notes": "Test split used once, after selection on the validation split.",
    }
    (reports_dir / "evaluation_public.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    rep = train_public()
    print("Model version:", rep["model_version"])
    print("Dataset rows:", rep["dataset"]["rows"], "| positive rate:", round(rep["dataset"]["positive_rate"], 4))
    print("Selected:", rep["selected"])
    print("Test metrics (selected, UCI public data):", json.dumps(rep["test_metrics_selected"], indent=2))
    print("Saved:", config.models_dir() / config.PUBLIC_ARTIFACT_NAME)
