"""Score one client with the PUBLIC-DATA model. Only load artifacts you trained yourself (pickle)."""
from __future__ import annotations

from pathlib import Path

import joblib

from . import config
from .predict import ModelBundle, ModelNotAvailableError
from .public_features import PUBLIC_FEATURE_COLUMNS, build_public_features
import pandas as pd


def load_public_bundle(models_dir: Path | None = None) -> ModelBundle:
    path = Path(models_dir or config.models_dir()) / config.PUBLIC_ARTIFACT_NAME
    if not path.exists():
        raise ModelNotAvailableError(
            "Public-data model not found. Download the UCI dataset into backend/data and run: "
            "python -m app.public_train")
    data = joblib.load(path)
    schema = data["metadata"]["feature_schema"]
    if schema["columns"] != PUBLIC_FEATURE_COLUMNS or schema["version"] != config.PUBLIC_SCHEMA_VERSION:
        raise ModelNotAvailableError("Public model feature schema mismatch. Retrain the model.")
    return ModelBundle(data["pipeline"], data["calibrator"], data["metadata"])


def predict_public(bundle: ModelBundle, raw_input: dict) -> dict:
    X = build_public_features(pd.DataFrame([raw_input]))
    raw_p = float(bundle.pipeline.predict_proba(X)[:, 1][0])
    cal_p = float(bundle.calibrator.transform([raw_p])[0])
    row, meta = X.iloc[0], bundle.metadata
    return {
        "model_track": "public_uci_credit_card",
        "default_probability_next_month": cal_p,
        "uncalibrated_model_score": raw_p,
        "calibration_method": meta["calibration_method"],
        "calibration_evaluated": meta["calibration_evaluated"],
        "model_version": meta["model_version"],
        "feature_schema_version": meta["feature_schema"]["version"],
        "data_provenance": meta["data_provenance"],
        "derived_values": {
            "utilization_latest": float(row["utilization_latest"]),
            "months_delayed": int(row["months_delayed"]),
            "payment_ratio_latest": None if pd.isna(row["payment_ratio_latest"]) else float(row["payment_ratio_latest"]),
        },
        "explanation": {"status": "unavailable", "reason": "Explanations (SHAP) are implemented in a later stage."},
        "limitations": meta["limitations"],
    }
