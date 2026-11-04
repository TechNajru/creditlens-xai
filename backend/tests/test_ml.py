import joblib
import numpy as np
import pytest

from app import config, train as train_module
from app.features import FEATURE_COLUMNS, TARGET_COLUMN
from app.predict import ModelNotAvailableError, load_bundle, predict_one
from app.synthetic import generate_synthetic_applications
from tests.conftest import VALID_APPLICATION


def test_splits_have_no_target_and_no_overlap():
    raw = generate_synthetic_applications(1000, seed=5)
    splits = train_module.split_data(raw, seed=5)
    assert sum(len(v[1]) for v in splits.values()) == 1000
    for X, _ in splits.values():
        assert list(X.columns) == FEATURE_COLUMNS and TARGET_COLUMN not in X.columns


def test_training_is_reproducible(tmp_path):
    a = train_module.train(tmp_path / "m1", tmp_path / "r1", n_samples=1500, seed=11)
    b = train_module.train(tmp_path / "m2", tmp_path / "r2", n_samples=1500, seed=11)
    assert a["test_metrics"] == b["test_metrics"]
    assert a["selected"] == b["selected"]


def test_calibration_was_evaluated_on_validation_not_test(trained_dir):
    import json
    rep = json.loads((trained_dir / "reports" / "evaluation.json").read_text())
    combos = {(r["model"], r["calibration"]) for r in rep["validation_candidates"]}
    assert {c for _, c in combos} == {"none", "sigmoid", "isotonic"}
    best_brier = min(r["brier"] for r in rep["validation_candidates"])
    selected = [r for r in rep["validation_candidates"]
                if (r["model"], r["calibration"]) == (rep["selected"]["model"], rep["selected"]["calibration"])][0]
    assert selected["brier"] == best_brier
    assert "majority_baseline" in rep and rep["test_metrics"]["brier"] > 0


def test_artifact_has_schema_and_provenance(trained_dir):
    bundle = load_bundle(trained_dir / "models")
    assert bundle.metadata["feature_schema"]["columns"] == FEATURE_COLUMNS
    assert "SYNTHETIC" in bundle.metadata["data_provenance"]
    assert bundle.metadata["calibration_evaluated"] is True


def test_artifact_reload_gives_identical_predictions(trained_dir):
    first = predict_one(load_bundle(trained_dir / "models"), VALID_APPLICATION)
    second = predict_one(load_bundle(trained_dir / "models"), VALID_APPLICATION)
    assert first["default_probability_simulated"] == second["default_probability_simulated"]
    assert 0.0 <= first["default_probability_simulated"] <= 1.0


def test_schema_mismatch_is_rejected(trained_dir, tmp_path):
    data = joblib.load(trained_dir / "models" / config.ARTIFACT_NAME)
    data["metadata"]["feature_schema"]["columns"] = FEATURE_COLUMNS[::-1]
    joblib.dump(data, tmp_path / config.ARTIFACT_NAME)
    with pytest.raises(ModelNotAvailableError):
        load_bundle(tmp_path)


def test_missing_artifact_raises(tmp_path):
    with pytest.raises(ModelNotAvailableError):
        load_bundle(tmp_path)
