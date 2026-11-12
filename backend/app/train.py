"""Train, calibrate, select and evaluate the SIMULATION risk model.

Run from the backend/ folder:   python -m app.train

Splits (stratified, seeded):
  train 55%        -> fit model pipelines
  calibration 15%  -> fit probability calibrators
  validation 15%   -> choose model + calibrator (lowest Brier score)
  test 15%         -> untouched; evaluated ONCE for the selected combination

Preprocessing (imputer / scaler) lives inside each sklearn Pipeline and is
therefore fit on the training split only.
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
from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix,
                             f1_score, log_loss, precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from . import config
from .calibration import CALIBRATORS
from .explain import fit_explanation_assets
from .features import FEATURE_COLUMNS, TARGET_COLUMN, build_features, feature_schema
from .synthetic import DATA_PROVENANCE, generate_synthetic_applications

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

THRESHOLDS = [0.05, 0.10, 0.15, 0.20, 0.30, 0.50]


def make_candidates(seed: int) -> dict[str, Pipeline]:
    return {
        "logistic_regression": Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("model", LogisticRegression(max_iter=2000, random_state=seed)),
        ]),
        "random_forest": Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("model", RandomForestClassifier(n_estimators=200, min_samples_leaf=20,
                                             random_state=seed, n_jobs=-1)),
        ]),
        "hist_gradient_boosting": Pipeline([
            # HistGradientBoosting handles NaN natively; no imputer needed.
            ("model", HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05,
                                                     random_state=seed)),
        ]),
    }


def probability_metrics(y, p) -> dict:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return {
        "roc_auc": float(roc_auc_score(y, p)),
        "average_precision": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "log_loss": float(log_loss(y, p)),
    }


def threshold_metrics(y, p, threshold: float) -> dict:
    pred = (p >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "threshold": threshold,
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def split_data(raw: pd.DataFrame, seed: int):
    y = raw[TARGET_COLUMN].to_numpy()
    X = build_features(raw.drop(columns=[TARGET_COLUMN]))
    idx = np.arange(len(X))
    rest, test = train_test_split(idx, test_size=0.15, stratify=y, random_state=seed)
    rest, val = train_test_split(rest, test_size=0.15 / 0.85, stratify=y[rest], random_state=seed)
    train, calib = train_test_split(rest, test_size=0.15 / 0.70, stratify=y[rest], random_state=seed)
    return {name: (X.iloc[i], y[i]) for name, i in
            [("train", train), ("calibration", calib), ("validation", val), ("test", test)]}


def train(models_dir: Path | None = None, reports_dir: Path | None = None,
          n_samples: int = 20_000, seed: int | None = None) -> dict:
    seed = config.default_seed() if seed is None else seed
    models_dir = Path(models_dir or config.models_dir())
    reports_dir = Path(reports_dir or config.reports_dir())
    models_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    raw = generate_synthetic_applications(n_samples, seed)
    splits = split_data(raw, seed)
    X_tr, y_tr = splits["train"]
    X_ca, y_ca = splits["calibration"]
    X_va, y_va = splits["validation"]
    X_te, y_te = splits["test"]
    if TARGET_COLUMN in X_tr.columns or list(X_tr.columns) != FEATURE_COLUMNS:    # explicit check: asserts vanish under python -O
        raise ValueError("Leakage guard failed: the target is in the features, or the feature order changed.")

    # 1) fit models on train; 2) fit calibrators on calibration; 3) score on validation
    fitted, candidate_table = {}, []
    for model_name, pipe in make_candidates(seed).items():
        pipe.fit(X_tr, y_tr)
        raw_ca = pipe.predict_proba(X_ca)[:, 1]
        raw_va = pipe.predict_proba(X_va)[:, 1]
        for cal_name, cal_cls in CALIBRATORS.items():
            cal = cal_cls().fit(raw_ca, y_ca)
            m = probability_metrics(y_va, cal.transform(raw_va))
            fitted[(model_name, cal_name)] = (pipe, cal)
            candidate_table.append({"model": model_name, "calibration": cal_name, **m})

    best = min(candidate_table, key=lambda r: r["brier"])
    pipe, cal = fitted[(best["model"], best["calibration"])]

    # Untouched test set: evaluated once for the selected combination only.
    p_te = cal.transform(pipe.predict_proba(X_te)[:, 1])
    test_metrics = probability_metrics(y_te, p_te)
    base_rate_train = float(np.mean(y_tr))
    baseline = {
        "description": "Majority-class / constant base-rate predictor (fit on train labels)",
        "accuracy_always_negative": float(1 - np.mean(y_te)),
        "brier_constant_base_rate": float(brier_score_loss(y_te, np.full(len(y_te), base_rate_train))),
        "log_loss_constant_base_rate": float(log_loss(y_te, np.full(len(y_te), base_rate_train))),
    }
    frac_pos, mean_pred = calibration_curve(y_te, p_te, n_bins=10, strategy="quantile")

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], "--", color="gray", label="Perfect calibration")
    ax.plot(mean_pred, frac_pos, "o-", label=f"{best['model']} + {best['calibration']}")
    ax.set_xlabel("Mean predicted default probability")
    ax.set_ylabel("Observed default rate (simulated labels)")
    ax.set_title("Calibration on untouched test split (SIMULATION)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(reports_dir / "calibration_test.png", dpi=120)
    plt.close(fig)

    background, global_importance = fit_explanation_assets(pipe, X_tr, X_va, seed)
    model_version = f"sim-{best['model']}-{best['calibration']}-seed{seed}-fs{config.FEATURE_SCHEMA_VERSION}"
    metadata = {
        "model_version": model_version,
        "model_name": best["model"],
        "calibration_method": best["calibration"],
        "calibration_evaluated": True,
        "feature_schema": feature_schema(),
        "data_provenance": DATA_PROVENANCE,
        "target": TARGET_COLUMN,
        "target_definition": "Simulated default within 12 months, generated from a hand-written rule plus noise.",
        "seed": seed,
        "n_samples": n_samples,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "library_versions": {"python": platform.python_version(), "scikit-learn": sklearn.__version__,
                             "pandas": pd.__version__, "numpy": np.__version__},
        "selection_criterion": "lowest validation Brier score across model x calibrator combinations",
        "global_importance": global_importance,
        "limitations": [
            "Trained on synthetic data: performance says nothing about real borrowers.",
            "Not a credit-bureau score and not a loan-approval probability.",
            "Probability is the simulated 12-month default probability, not (1 - approval).",
            "Thresholds shown in reports are experimental.",
        ],
    }
    joblib.dump({"pipeline": pipe, "calibrator": cal, "metadata": metadata, "background": background},
                models_dir / config.ARTIFACT_NAME)

    report = {
        "model_version": model_version,
        "data_provenance": DATA_PROVENANCE,
        "split_sizes": {k: int(len(v[1])) for k, v in splits.items()},
        "positive_rate": {k: float(np.mean(v[1])) for k, v in splits.items()},
        "validation_candidates": sorted(candidate_table, key=lambda r: r["brier"]),
        "selected": {"model": best["model"], "calibration": best["calibration"]},
        "test_metrics": test_metrics,
        "test_threshold_tradeoffs": [threshold_metrics(y_te, p_te, t) for t in THRESHOLDS],
        "majority_baseline": baseline,
        "calibration_curve_test": {"mean_predicted": mean_pred.tolist(), "fraction_positive": frac_pos.tolist()},
        "global_importance": global_importance,
        "limitations": metadata["limitations"],
        "notes": "Test split used once, after selection on the validation split.",
    }
    (reports_dir / "evaluation.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    rep = train()
    print("Model version:", rep["model_version"])
    print("Selected:", rep["selected"])
    print("Test metrics (SIMULATION data):", json.dumps(rep["test_metrics"], indent=2))
    print("Artifact saved to:", config.models_dir() / config.ARTIFACT_NAME)
    print("Reports saved to:", config.reports_dir())
