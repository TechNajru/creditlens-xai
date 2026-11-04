import io

import pandas as pd

from app.categorizer import assign_categories
from app.ingestion import parse_csv


def csv_bytes(rows: list[dict]) -> bytes:
    return pd.DataFrame(rows).to_csv(index=False).encode()


def tx_from_rows(rows: list[dict], corrections=None):
    parsed = parse_csv(csv_bytes(rows), "t.csv")
    tx, report = assign_categories(parsed.transactions, corrections)
    return tx, report


def r(date, desc, amt, direction, cat="", tid=None, **extra):
    row = {"date": date, "description": desc, "amount": amt, "direction": direction,
           "category": cat, "transaction_id": tid or f"T-{date}-{desc[:6]}-{amt}"}
    row.update(extra)
    return row


SALARY = "SALARY CREDIT ACME PVT LTD"


def hand_checked_rows() -> list[dict]:
    """Jan & May are edge months with huge decoys. Feb-Apr are the usable interior months."""
    return [
        r("2026-01-31", SALARY, 999999, "credit", "income_salary"),
        r("2026-02-01", SALARY, 50000, "credit", "income_salary"),
        r("2026-02-05", "RENT PAYMENT", 15000, "debit"),
        r("2026-02-07", "HOME LOAN EMI", 5000, "debit"),
        r("2026-02-10", "UPI-BIGBASKET GROCERY", 3000, "debit"),
        r("2026-02-15", "UPI-FRIEND", 2000, "credit", tid="FRIEND-1"),
        r("2026-03-01", SALARY, 50000, "credit", "income_salary"),
        r("2026-03-05", "RENT PAYMENT", 15000, "debit"),
        r("2026-03-07", "HOME LOAN EMI", 5000, "debit"),
        r("2026-03-10", "UPI-BIGBASKET GROCERY", 4000, "debit"),
        r("2026-03-12", "TRANSFER TO OWN SAVINGS ACCOUNT", 10000, "debit"),
        r("2026-03-13", "TRANSFER FROM OWN SAVINGS ACCOUNT", 10000, "credit"),
        r("2026-04-01", SALARY, 50000, "credit", "income_salary"),
        r("2026-04-05", "RENT PAYMENT", 15000, "debit"),
        r("2026-04-07", "HOME LOAN EMI", 5000, "debit"),
        r("2026-04-10", "UPI-BIGBASKET GROCERY", 3000, "debit"),
        r("2026-04-20", "UPI-MERCHANT", 60000, "debit"),
        r("2026-05-02", "UPI-ZOMATO FOOD", 888888, "debit"),
    ]
