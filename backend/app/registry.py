"""Model version registry: versioned artifact copies, SHA-256 integrity, one active version per track.

Artifacts are pickles: only register files you trained yourself.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import joblib
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .audit import log_event
from .db import utcnow
from .models import ModelVersion
from .predict import ModelBundle, ModelNotAvailableError, load_bundle_from_path

ARTIFACTS = {"simulation": config.ARTIFACT_NAME, "public": config.PUBLIC_ARTIFACT_NAME}
SUMMARY_KEYS = ("model_version", "model_name", "calibration_method", "calibration_evaluated", "data_provenance",
                "target_definition", "selection_criterion", "trained_at_utc", "seed", "library_versions", "limitations")
_cache: dict[str, ModelBundle] = {}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def register_artifact(db: Session, track: str, actor=None, source: Path | None = None) -> tuple[ModelVersion, bool]:
    if track not in ARTIFACTS:
        raise ValueError("track must be 'simulation' or 'public'")
    src = Path(source or config.models_dir() / ARTIFACTS[track])
    if not src.exists():
        raise FileNotFoundError(f"No trained {track} model found at {src}. Train it first.")
    sha = sha256_file(src)
    existing = db.scalar(select(ModelVersion).where(ModelVersion.track == track, ModelVersion.artifact_sha256 == sha))
    if existing:
        return existing, False
    dest_dir = config.registry_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{track}-{sha[:12]}.joblib"
    if not dest.exists():
        shutil.copy2(src, dest)
    meta = joblib.load(dest)["metadata"]
    summary = {k: meta.get(k) for k in SUMMARY_KEYS}
    summary["feature_schema_version"] = meta["feature_schema"]["version"]
    mv = ModelVersion(track=track, version=meta["model_version"], artifact_sha256=sha, artifact_path=str(dest),
                      metadata_json=summary, is_active=False, registered_at=utcnow())
    db.add(mv)
    db.flush()
    log_event(db, actor, "model.registered", "model_version", mv.id, details={"track": track, "model_version": mv.version})
    return mv, True


def activate(db: Session, mv: ModelVersion, actor=None) -> ModelVersion:
    for other in db.scalars(select(ModelVersion).where(ModelVersion.track == mv.track, ModelVersion.is_active.is_(True))):
        other.is_active = False
    mv.is_active, mv.activated_at, mv.activated_by = True, utcnow(), getattr(actor, "id", None)
    db.flush()
    log_event(db, actor, "model.activated", "model_version", mv.id, details={"track": mv.track, "model_version": mv.version})
    return mv


def active_version(db: Session, track: str = "simulation") -> ModelVersion | None:
    return db.scalar(select(ModelVersion).where(ModelVersion.track == track, ModelVersion.is_active.is_(True)))


def load_active_bundle(db: Session, track: str = "simulation") -> tuple[ModelBundle, ModelVersion]:
    mv = active_version(db, track)
    if mv is None:
        raise ModelNotAvailableError(f"No active '{track}' model version. An administrator must register and activate one.")
    if mv.artifact_sha256 not in _cache:
        path = Path(mv.artifact_path)
        if not path.exists() or sha256_file(path) != mv.artifact_sha256:
            raise ModelNotAvailableError("The active model file is missing or does not match its recorded checksum.")
        _cache[mv.artifact_sha256] = load_bundle_from_path(path)
    return _cache[mv.artifact_sha256], mv


def clear_cache() -> None:
    _cache.clear()
