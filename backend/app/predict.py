"""Load the versioned model artifact and score one applicant.

SECURITY NOTE: joblib/pickle files can run code when loaded. Only load
artifacts you trained yourself. Never load a model file from an untrusted source.
"""
from __future__ import annotations

from pathlib import Path

import joblib

from . import config
from .explain import safe_explanation
from .features import build_features_single, feature_schema, FEATURE_COLUMNS
from .reason_codes import describe_loan


class ModelNotAvailableError(RuntimeError):
    """The model artifact is missing or incompatible with the current feature schema."""


class ModelBundle:
    def __init__(self, pipeline, calibrator, metadata: dict, background=None):
        self.pipeline, self.calibrator, self.metadata = pipeline, calibrator, metadata
        self.background = background  # training-row sample used by the explainer


def load_bundle_from_path(path: Path) -> ModelBundle:
    path = Path(path)
    if not path.exists():
        raise ModelNotAvailableError("Model artifact not found. Train it first: python -m app.train")
    data = joblib.load(path)
    meta = data["metadata"]
    if meta["feature_schema"]["columns"] != FEATURE_COLUMNS or \
            meta["feature_schema"]["version"] != feature_schema()["version"]:
        raise ModelNotAvailableError(
            "Model feature schema does not match the application's schema. Retrain the model.")
    return ModelBundle(data["pipeline"], data["calibrator"], meta, data.get("background"))


def load_bundle(models_dir: Path | None = None) -> ModelBundle:
    return load_bundle_from_path(Path(models_dir or config.models_dir()) / config.ARTIFACT_NAME)


def predict_one(bundle: ModelBundle, raw_input: dict, detail: str = "summary") -> dict:
    X = build_features_single(raw_input)  # same function used in training
    raw_p = float(bundle.pipeline.predict_proba(X)[:, 1][0])
    cal_p = float(bundle.calibrator.transform([raw_p])[0])
    row = X.iloc[0]
    meta = bundle.metadata
    return {
        "default_probability_simulated": cal_p,
        "uncalibrated_model_score": raw_p,
        "calibration_method": meta["calibration_method"],
        "calibration_evaluated": meta["calibration_evaluated"],
        "model_version": meta["model_version"],
        "feature_schema_version": meta["feature_schema"]["version"],
        "data_provenance": meta["data_provenance"],
        "derived_values": {
            "new_loan_emi": float(row["new_loan_emi"]),
            "total_emi": float(row["total_emi"]),
            "total_emi_to_income": float(row["total_emi_to_income"]),
            "credit_history_missing": bool(row["credit_history_missing"]),
        },
        "explanation": safe_explanation(bundle, X, describe_loan, detail),
        "limitations": meta["limitations"],
    }
