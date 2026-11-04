import json
import logging
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SAMPLES = Path(__file__).resolve().parents[2] / "sample_data"


def post(path, name="SYNTHETIC_salaried_stable.csv", filename=None, data=None, content=None):
    content = content if content is not None else (SAMPLES / name).read_bytes()
    return client.post(path, files={"file": (filename or name, content, "text/csv")}, data=data or {})


def test_preview_returns_rows_categories_and_provenance():
    r = post("/api/v1/uploads/preview")
    assert r.status_code == 200
    body = r.json()
    assert body["stats"]["rows_with_errors"] == 0 and body["date_format"] == "%Y-%m-%d"
    first = body["transactions"][0]
    assert {"key", "category", "category_source", "confidence"} <= set(first)


def test_preview_of_messy_file_reports_problems():
    body = post("/api/v1/uploads/preview", "SYNTHETIC_messy_for_validation_demo.csv").json()
    assert body["stats"]["rows_valid"] == 5 and body["stats"]["duplicates_excluded"] == 1
    assert any(i["severity"] == "error" for i in body["issues"])
    assert any("not recognised" in c["problem"] for c in body["category_issues"])


def test_corrections_flow_through_preview():
    r = post("/api/v1/uploads/preview", "SYNTHETIC_messy_for_validation_demo.csv",
             data={"corrections": json.dumps({"M-8": "income_other"})})
    row = next(t for t in r.json()["transactions"] if t["key"] == "M-8")
    assert row["category"] == "income_other" and row["category_source"] == "user_correction"


def test_analyze_endpoint_returns_summary_not_used_for_risk():
    body = post("/api/v1/cashflow/analyze").json()
    assert body["used_for_risk_model"] is False
    assert body["coverage"]["sufficient_for_analysis"] is True
    assert body["metrics"]["months_used"] == 4


def test_upload_error_codes(monkeypatch):
    assert post("/api/v1/uploads/preview", filename="x.xlsx").status_code == 415
    assert post("/api/v1/uploads/preview", content=b"\x00\x01").status_code == 422
    assert post("/api/v1/uploads/preview", content=b"foo,bar\n1,2\n").status_code == 422
    monkeypatch.setenv("CREDITLENS_MAX_UPLOAD_BYTES", "50")
    assert post("/api/v1/uploads/preview").status_code == 413


def test_bad_json_fields_rejected():
    assert post("/api/v1/uploads/preview", data={"mapping": "{not json"}).status_code == 422
    assert post("/api/v1/uploads/preview", data={"corrections": "[1,2]"}).status_code == 422


def test_logs_do_not_contain_raw_transaction_text(caplog):
    caplog.set_level(logging.INFO, logger="creditlens")
    post("/api/v1/cashflow/analyze")
    assert "ACME" not in caplog.text and "SALARY" not in caplog.text
    assert "cashflow analyzed" in caplog.text


def test_categories_endpoint():
    assert "income_salary" in client.get("/api/v1/transactions/categories").json()["categories"]
