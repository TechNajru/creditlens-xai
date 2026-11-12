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


def max_upload_bytes() -> int:
    return int(os.getenv("CREDITLENS_MAX_UPLOAD_BYTES", str(2_000_000)))


def max_upload_rows() -> int:
    return int(os.getenv("CREDITLENS_MAX_UPLOAD_ROWS", "5000"))


PUBLIC_SCHEMA_VERSION = "public-1.0.0"
PUBLIC_ARTIFACT_NAME = "creditlens_public_model.joblib"


def data_dir() -> Path:
    return Path(os.getenv("CREDITLENS_DATA_DIR", BASE_DIR / "data"))


# ---------------- Stage 5: database, sessions, registry ----------------
def normalize_database_url(url: str) -> str:
    """Hosting providers hand out postgres:// or postgresql:// URLs; SQLAlchemy needs the driver name (psycopg 3)."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def database_url() -> str:
    default = f"sqlite:///{(BASE_DIR / 'data' / 'creditlens.db').as_posix()}"
    return normalize_database_url(os.getenv("CREDITLENS_DATABASE_URL", default))


def registry_dir() -> Path:
    return Path(os.getenv("CREDITLENS_REGISTRY_DIR", models_dir() / "registry"))


def session_hours() -> int:
    return int(os.getenv("CREDITLENS_SESSION_HOURS", "8"))


def cookie_secure() -> bool:
    """Set CREDITLENS_COOKIE_SECURE=true when serving over HTTPS (required in any real deployment)."""
    return os.getenv("CREDITLENS_COOKIE_SECURE", "false").strip().lower() in ("1", "true", "yes")


def max_failed_logins() -> int:
    return int(os.getenv("CREDITLENS_MAX_FAILED_LOGINS", "5"))


def lockout_minutes() -> int:
    return int(os.getenv("CREDITLENS_LOCKOUT_MINUTES", "15"))
