"""Feature schema for the PUBLIC-DATA model (UCI Default of Credit Card Clients).

This is a different product from the loan-application schema in features.py (credit-card payment
history, NT dollars, Taiwan 2005). The two models are never mixed.

Rules
- SEX, EDUCATION, MARRIAGE are NOT model inputs; they are kept for the fairness audit only.
  (Dropping them does not remove proxy bias; the audit measures outcomes, not just inputs.)
- PAY_x codes are used exactly as given. UCI documents -1 (paid duly) and 1..9 (months delayed);
  the values -2 and 0 occur in the data but are not defined by UCI, so we assign them no meaning.
- Negative BILL_AMT values exist in the data and are kept (not clipped).
- Unknown is NaN: payment_ratio_latest is undefined when the latest bill is <= 0.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PAY_COLS = ["PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6"]
BILL_COLS = [f"BILL_AMT{i}" for i in range(1, 7)]
PAYAMT_COLS = [f"PAY_AMT{i}" for i in range(1, 7)]
RAW_PUBLIC = ["LIMIT_BAL", "AGE"] + PAY_COLS + BILL_COLS + PAYAMT_COLS
DERIVED = ["utilization_latest", "months_delayed", "payment_ratio_latest"]
PUBLIC_FEATURE_COLUMNS = RAW_PUBLIC + DERIVED
AUDIT_COLUMNS = ["SEX", "EDUCATION", "MARRIAGE"]
PUBLIC_TARGET = "default_next_month"

LIMITS = {"LIMIT_BAL": (1, 10_000_000), "AGE": (18, 100), "PAY": (-2, 9),
          "BILL": (-10_000_000, 10_000_000), "PAYAMT": (0, 10_000_000)}


class InvalidPublicInputError(ValueError):
    pass


def validate_public_raw(raw: pd.DataFrame) -> None:
    missing = [c for c in RAW_PUBLIC if c not in raw.columns]
    if missing:
        raise InvalidPublicInputError(f"Missing required fields: {missing}")
    num = raw[RAW_PUBLIC].apply(pd.to_numeric, errors="coerce")
    if num.isna().any().any():
        bad = [c for c in RAW_PUBLIC if num[c].isna().any()]
        raise InvalidPublicInputError(f"Fields must be numeric and present: {bad}")
    groups = [(["LIMIT_BAL"], "LIMIT_BAL"), (["AGE"], "AGE"), (PAY_COLS, "PAY"),
              (BILL_COLS, "BILL"), (PAYAMT_COLS, "PAYAMT")]
    for cols, key in groups:
        lo, hi = LIMITS[key]
        if ((num[cols] < lo) | (num[cols] > hi)).any().any():
            raise InvalidPublicInputError(f"{cols[0]}.. must be between {lo} and {hi}")


def build_public_features(raw: pd.DataFrame) -> pd.DataFrame:
    validate_public_raw(raw)
    x = raw[RAW_PUBLIC].apply(pd.to_numeric).astype(float).reset_index(drop=True)
    x["utilization_latest"] = x["BILL_AMT1"] / x["LIMIT_BAL"]          # LIMIT_BAL >= 1 (validated)
    x["months_delayed"] = (x[PAY_COLS] >= 1).sum(axis=1).astype(float)   # documented delay codes only
    bill = x["BILL_AMT1"].to_numpy()
    ratio = np.full(len(x), np.nan)
    pos = bill > 0
    ratio[pos] = x["PAY_AMT1"].to_numpy()[pos] / bill[pos]
    x["payment_ratio_latest"] = ratio                                   # NaN = undefined, not 0
    return x[PUBLIC_FEATURE_COLUMNS]
