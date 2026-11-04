"""Central configuration. Paths are resolved at call time so tests can override them."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

FEATURE_SCHEMA_VERSION = "1.0.0"
ARTIFACT_NAME = "creditlens_model.joblib"


def models_dir() -> Path:
    return Path(os.getenv("CREDITLENS_MODELS_DIR", BASE_DIR / "models"))


def reports_dir() -> Path:
    return Path(os.getenv("CREDITLENS_REPORTS_DIR", BASE_DIR / "reports"))


def default_seed() -> int:
    return int(os.getenv("CREDITLENS_SEED", "42"))


def cors_origins() -> list[str]:
    raw = os.getenv("CREDITLENS_CORS_ORIGINS", "http://localhost:3000")
    return [o.strip() for o in raw.split(",") if o.strip()]
