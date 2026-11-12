"""Checks that the repo is complete and tells you the next step. Uses only the standard library.

Run from the backend folder (venv NOT required for the file check):   python check_setup.py
"""
import importlib
import importlib.metadata as metadata
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
ROOT = BACKEND.parent

APP = ["__init__", "admin", "app_service", "audit", "calibration", "cashflow", "categories_api", "categorizer", "config",
       "db", "deps", "experiments", "explain", "fairness", "features", "ingestion", "main", "model_card", "models",
       "monitoring", "notice", "policy", "predict", "public_data", "public_features", "public_predict", "public_train",
       "reason_codes", "registry", "routes_admin", "routes_applications", "routes_auth", "routes_reviews", "sample_data",
       "scenarios", "schemas", "security", "synthetic", "train", "workflow"]
TESTS = ["__init__", "conftest", "helpers", "api_helpers", "test_api", "test_cashflow", "test_e2e_flow", "test_experiments",
         "test_explain", "test_fairness", "test_features", "test_ingestion", "test_migrations", "test_ml", "test_public",
         "test_bootstrap",
         "test_scenarios", "test_security", "test_upload_api", "test_workflow"]
REQUIRED = ([BACKEND / "app" / f"{n}.py" for n in APP] + [BACKEND / "tests" / f"{n}.py" for n in TESTS] +
            [BACKEND / "requirements.txt", BACKEND / "pytest.ini", BACKEND / "alembic.ini",
             BACKEND / "migrations" / "env.py", BACKEND / "migrations" / "versions" / "0001_initial_schema.py",
             ROOT / "frontend" / "package.json", ROOT / "frontend" / "src" / "components" / "ApplicationWorkflow.tsx",
             ROOT / "frontend" / "src" / "app" / "page.tsx", ROOT / "sample_data" / "SYNTHETIC_stressed.csv"])
PACKAGES = {"numpy": "numpy", "pandas": "pandas", "sklearn": "scikit-learn", "scipy": "scipy", "fastapi": "fastapi",
            "pydantic": "pydantic", "shap": "shap", "fairlearn": "fairlearn", "xlrd": "xlrd", "sqlalchemy": "SQLAlchemy",
            "alembic": "alembic", "argon2": "argon2-cffi", "pytest": "pytest"}


def main() -> int:
    print(f"Python {sys.version.split()[0]} | repo: {ROOT}")
    missing = [p for p in REQUIRED if not p.exists()]
    if missing:
        print(f"\nMISSING FILES ({len(missing)}):")
        for p in missing:
            print("  -", p.relative_to(ROOT))
        print("\nExtract creditlens-xai-full.zip over this folder again (see the setup steps), then re-run.")
        return 1
    print(f"OK: all {len(REQUIRED)} required files are present.")

    bad = []
    for name, dist in PACKAGES.items():
        try:
            importlib.import_module(name)
            print(f"  {name:<12} {metadata.version(dist)}")
        except (ImportError, metadata.PackageNotFoundError):
            bad.append(name)
    if bad:
        print("\nNot installed in this Python:", ", ".join(bad))
        print("Activate the venv (.\\venv\\Scripts\\Activate.ps1) and run: pip install -r requirements.txt")

    data = list((BACKEND / "data").glob("default*credit*card*.xls*")) + list((BACKEND / "data").glob("default*credit*card*.csv"))
    print("\nUCI dataset in backend\\data:", data[0].name if data else "NOT FOUND (needed for the public-data model)")
    for label, path in [("simulation model", BACKEND / "models" / "creditlens_model.joblib"),
                        ("public-data model", BACKEND / "models" / "creditlens_public_model.joblib"),
                        ("application database", BACKEND / "data" / "creditlens.db"),
                        ("fairness report", BACKEND / "reports" / "fairness_public.json"),
                        ("experiments report", BACKEND / "reports" / "experiments_public.json")]:
        print(f"  {label:<20}", "found" if path.exists() else "not generated yet")
    print("\nNext: python -m pytest -q   then   python -m app.admin init   (creates the database and demo staff accounts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
