import json
from pathlib import Path

import pytest

from app.ingestion import UploadError, detect_mapping, parse_amount, parse_csv
from tests.helpers import csv_bytes, r

SAMPLES = Path(__file__).resolve().parents[2] / "sample_data"


def test_valid_sample_parses_cleanly():
    p = parse_csv((SAMPLES / "SYNTHETIC_salaried_stable.csv").read_bytes(), "a.csv")
    assert p.stats["rows_with_errors"] == 0 and p.stats["duplicates_excluded"] == 0
    assert p.stats["rows_valid"] == p.stats["rows_total"] > 20
    assert p.date_format == "%Y-%m-%d"


def test_messy_file_reports_invalid_rows_and_duplicates_without_echoing_descriptions():
    p = parse_csv((SAMPLES / "SYNTHETIC_messy_for_validation_demo.csv").read_bytes(), "m.csv")
    assert p.stats["rows_total"] == 9
    assert p.stats["rows_with_errors"] == 3          # bad date (4), bad amount (5), no description (6)
    assert p.stats["duplicates_excluded"] == 1       # row 3 repeats transaction_id M-2
    assert p.stats["rows_valid"] == 5
    error_rows = {i["row"] for i in p.issues if i["severity"] == "error"}
    assert error_rows == {4, 5, 6}
    assert "IMPOSSIBLE" not in json.dumps(p.issues)  # reports use row numbers, not raw text


@pytest.mark.parametrize("raw,expected", [
    ("1,234.50", 1234.5), ("₹1,234.50", 1234.5), ("Rs.1,000.50", 1000.5), ("(500)", -500.0),
    ("-200", -200.0), ("abc", None), ("1.2.3", None), ("", None),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw)[0] == expected


def test_cr_dr_suffix_gives_direction():
    assert parse_amount("1,000.00 Cr") == (1000.0, "credit")
    assert parse_amount("250 DR") == (250.0, "debit")


def test_missing_columns_listed():
    with pytest.raises(UploadError) as e:
        parse_csv(b"foo,bar\n1,2\n", "x.csv")
    assert "Missing required columns" in e.value.message and "date" in e.value.message


def test_bank_style_headers_and_separate_debit_credit_columns():
    data = (b"Txn Date,Narration,Withdrawal,Deposit\n"
            b"2026-01-01,SALARY,,50000\n2026-01-02,RENT,15000,\n")
    p = parse_csv(data, "bank.csv")
    assert list(p.transactions["direction"]) == ["credit", "debit"]
    assert list(p.transactions["amount"]) == [50000.0, 15000.0]


def test_signed_amounts_without_direction_column():
    p = parse_csv(b"date,description,amount\n2026-01-01,SALARY,50000\n2026-01-02,RENT,-15000\n", "s.csv")
    assert list(p.transactions["direction"]) == ["credit", "debit"]
    assert list(p.transactions["amount"]) == [50000.0, 15000.0]


def test_user_mapping_overrides_detection_and_validates_columns():
    data = b"when,what,how_much,kind\n2026-01-01,SALARY,500,credit\n"
    p = parse_csv(data, "m.csv", {"date": "when", "description": "what", "amount": "how_much",
                                  "direction": "kind"})
    assert len(p.transactions) == 1
    with pytest.raises(UploadError):
        detect_mapping(["a", "b"], {"date": "nope"})


def test_non_csv_extension_rejected():
    with pytest.raises(UploadError) as e:
        parse_csv(b"a,b\n1,2\n", "data.xlsx")
    assert e.value.status_code == 415


def test_binary_and_empty_files_rejected():
    with pytest.raises(UploadError):
        parse_csv(b"\x00\x01\x02binary", "x.csv")
    with pytest.raises(UploadError):
        parse_csv(b"date,description,amount,direction\n", "x.csv")


def test_file_size_and_row_limits(monkeypatch):
    big = csv_bytes([r("2026-01-01", "X", 1, "credit", tid=str(i)) for i in range(50)])
    monkeypatch.setenv("CREDITLENS_MAX_UPLOAD_BYTES", "100")
    with pytest.raises(UploadError) as e:
        parse_csv(big, "big.csv")
    assert e.value.status_code == 413
    monkeypatch.delenv("CREDITLENS_MAX_UPLOAD_BYTES")
    monkeypatch.setenv("CREDITLENS_MAX_UPLOAD_ROWS", "10")
    with pytest.raises(UploadError) as e:
        parse_csv(big, "big.csv")
    assert "Too many rows" in e.value.message


def test_content_duplicates_detected_without_ids():
    data = (b"date,description,amount,direction\n2026-01-01,RENT,100,debit\n"
            b"2026-01-01,rent,100,debit\n")
    p = parse_csv(data, "d.csv")
    assert p.stats["duplicates_excluded"] == 1 and len(p.transactions) == 1
