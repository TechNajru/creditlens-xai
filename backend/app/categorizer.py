"""Transparent keyword categorization with provenance and confidence.

category_source: supplied (from the CSV) | user_correction | rule (keyword match) | default
confidence:      high (supplied/user_correction) | medium (rule) | low (default / unverified UPI)

Rule-based categories are GUESSES. They are labelled as such and users can correct them.
"""
from __future__ import annotations

import re

import pandas as pd

CREDIT_CATEGORIES = ["income_salary", "income_other", "upi_inflow_unverified", "refund",
                     "transfer_internal", "credit_uncategorized"]
DEBIT_CATEGORIES = ["emi_debt", "rent", "utilities", "groceries", "healthcare", "transport",
                    "dining_shopping", "entertainment", "transfer_internal", "debit_uncategorized"]
ALL_CATEGORIES = sorted(set(CREDIT_CATEGORIES + DEBIT_CATEGORIES))

# Assumption (documented in docs/cashflow_methodology.md): "essential" spending.
ESSENTIAL = {"rent", "utilities", "groceries", "healthcare"}

_TRANSFER = ["self transfer", "own account", "to own", "from own", "own savings", "transfer to savings",
             "transfer from savings"]
CREDIT_RULES = [
    ("transfer_internal", _TRANSFER),
    ("refund", ["refund", "reversal", "cashback"]),
    ("income_salary", ["salary", "payroll", "sal credit", "stipend"]),
]
DEBIT_RULES = [
    ("transfer_internal", _TRANSFER),
    ("emi_debt", ["emi", "loan repay", "loan instal", "credit card bill", "card payment"]),
    ("rent", ["rent"]),
    ("utilities", ["electricity", "water bill", "gas bill", "broadband", "mobile recharge", "dth"]),
    ("groceries", ["grocery", "groceries", "bigbasket", "supermarket", "vegetable"]),
    ("healthcare", ["pharmacy", "hospital", "clinic", "medical"]),
    ("transport", ["fuel", "petrol", "metro", "uber", "ola", "bus"]),
    ("dining_shopping", ["zomato", "swiggy", "restaurant", "amazon", "flipkart", "shopping"]),
    ("entertainment", ["netflix", "movie", "spotify", "cinema", "gaming"]),
]


def _match(desc: str, rules) -> str | None:
    d = desc.lower()
    for cat, words in rules:
        for w in words:
            if re.search(r"\b" + re.escape(w), d):
                return cat
    return None


def categorize(description: str, direction: str) -> tuple[str, str, str]:
    if direction == "credit":
        cat = _match(description, CREDIT_RULES)
        if cat:
            return cat, "rule", "medium"
        if "upi" in description.lower():
            return "upi_inflow_unverified", "rule", "low"
        return "credit_uncategorized", "default", "low"
    cat = _match(description, DEBIT_RULES)
    return (cat, "rule", "medium") if cat else ("debit_uncategorized", "default", "low")


def _allowed(direction: str) -> list[str]:
    return CREDIT_CATEGORIES if direction == "credit" else DEBIT_CATEGORIES


def assign_categories(tx: pd.DataFrame, corrections: dict | None = None):
    """Returns (transactions with category columns, report of supplied/correction problems)."""
    corrections = corrections or {}
    cats, sources, confs, report = [], [], [], []
    for r in tx.itertuples():
        cat, src, conf = categorize(r.description, r.direction)
        sup = r.category_supplied
        if sup:
            if sup in _allowed(r.direction):
                cat, src, conf = sup, "supplied", "high"
            else:
                report.append({"row": int(r.row), "problem": "supplied category not recognised for "
                               "this direction; using rule-based guess", "severity": "warning"})
        cats.append(cat); sources.append(src); confs.append(conf)
    out = tx.copy()
    out["category"], out["category_source"], out["confidence"] = cats, sources, confs

    keys = set(out["key"])
    for k, c in corrections.items():
        if k not in keys:
            report.append({"key": k, "problem": "correction refers to an unknown transaction",
                           "severity": "error"})
            continue
        i = out.index[out["key"] == k][0]
        if c not in _allowed(out.at[i, "direction"]):
            report.append({"key": k, "problem": f"category '{c}' is not allowed for a "
                           f"{out.at[i, 'direction']} transaction", "severity": "error"})
            continue
        out.loc[i, ["category", "category_source", "confidence"]] = [c, "user_correction", "high"]
    return out, report
