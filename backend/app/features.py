"""Shared feature engineering.

This is the ONLY place features are computed. Training, evaluation, API
inference and (later) what-if scenarios all call build_features(), which
removes the training/prediction mismatch of the first prototype
(new_loan_emi / income vs (new_loan_emi + existing_emi) / income).

Design rules:
- No silent clipping. Invalid values raise InvalidInputError.
- Unknown is not zero: credit_history_months may be missing (NaN/None) and is
  represented by NaN plus an explicit credit_history_missing indicator.
  Missing credit history is NOT treated as bad credit history.
- Total EMI ratio = (new loan EMI + existing EMI) / monthly income.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import FEATURE_SCHEMA_VERSION

# Allowed ranges (documented, enforced by validation, never silently clipped)
LIMITS = {
    "monthly_income": (1.0, 10_000_000.0),
    "loan_amount": (1.0, 100_000_000.0),
    "tenure_months": (3, 360),
    "annual_interest_rate": (0.0, 60.0),
    "existing_emi": (0.0, 10_000_000.0),
    "age": (18, 100),
    "employment_years": (0.0, 60.0),
    "num_existing_loans": (0, 50),
    "credit_history_months": (0.0, 1200.0),  # optional; may be missing
}

REQUIRED_RAW = [
    "monthly_income", "loan_amount", "tenure_months", "annual_interest_rate",
    "existing_emi", "age", "employment_years", "num_existing_loans",
]
OPTIONAL_RAW = ["credit_history_months"]
RAW_COLUMNS = REQUIRED_RAW + OPTIONAL_RAW

# Order matters: models are trained and served with exactly this order.
FEATURE_COLUMNS = [
    "monthly_income", "loan_amount", "tenure_months", "annual_interest_rate",
    "existing_emi", "age", "employment_years", "num_existing_loans",
    "credit_history_months", "credit_history_missing",
    "new_loan_emi", "total_emi", "total_emi_to_income", "loan_to_annual_income",
]

TARGET_COLUMN = "default_12m_simulated"  # must never appear in FEATURE_COLUMNS


class InvalidInputError(ValueError):
    """Raised when raw inputs are missing, non-numeric or out of range."""


def calculate_emi(principal, annual_rate_percent, tenure_months):
    """Standard reducing-balance EMI. Works on scalars or arrays.

    EMI = P*r*(1+r)^n / ((1+r)^n - 1), r = annual_rate/12/100.
    Zero interest => P / n. Tenure must be >= 1 and principal > 0.
    """
    p = np.asarray(principal, dtype=float)
    rate = np.asarray(annual_rate_percent, dtype=float)
    n = np.asarray(tenure_months, dtype=float)
    if np.any(n < 1):
        raise InvalidInputError("tenure_months must be at least 1")
    if np.any(p <= 0):
        raise InvalidInputError("principal must be positive")
    if np.any(rate < 0):
        raise InvalidInputError("interest rate cannot be negative")
    r = rate / 12.0 / 100.0
    zero = r == 0
    r_safe = np.where(zero, 1.0, r)
    growth = (1.0 + r_safe) ** n
    emi = np.where(zero, p / n, p * r_safe * growth / (growth - 1.0))
    return float(emi) if emi.ndim == 0 else emi


def validate_raw(raw: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_RAW if c not in raw.columns]
    if missing:
        raise InvalidInputError(f"Missing required fields: {missing}")
    for col in REQUIRED_RAW:
        vals = pd.to_numeric(raw[col], errors="coerce")
        if vals.isna().any():
            raise InvalidInputError(f"Field '{col}' must be a number and cannot be missing")
        lo, hi = LIMITS[col]
        if ((vals < lo) | (vals > hi)).any():
            raise InvalidInputError(f"Field '{col}' must be between {lo} and {hi}")
    if "credit_history_months" in raw.columns:
        vals = pd.to_numeric(raw["credit_history_months"], errors="coerce")
        lo, hi = LIMITS["credit_history_months"]
        present = vals.dropna()
        if ((present < lo) | (present > hi)).any():
            raise InvalidInputError(
                f"Field 'credit_history_months' must be between {lo} and {hi} when provided")


def build_features(raw: pd.DataFrame) -> pd.DataFrame:
    """Raw applicant rows -> model features in the fixed FEATURE_COLUMNS order."""
    validate_raw(raw)
    df = raw.copy()
    if "credit_history_months" not in df.columns:
        df["credit_history_months"] = np.nan
    for col in RAW_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)

    out = df[RAW_COLUMNS].copy()
    out["credit_history_missing"] = out["credit_history_months"].isna().astype(int)
    out["new_loan_emi"] = calculate_emi(out["loan_amount"].to_numpy(),
                                        out["annual_interest_rate"].to_numpy(),
                                        out["tenure_months"].to_numpy())
    out["total_emi"] = out["new_loan_emi"] + out["existing_emi"]
    out["total_emi_to_income"] = out["total_emi"] / out["monthly_income"]
    out["loan_to_annual_income"] = out["loan_amount"] / (12.0 * out["monthly_income"])
    return out[FEATURE_COLUMNS].reset_index(drop=True)


def build_features_single(raw: dict) -> pd.DataFrame:
    return build_features(pd.DataFrame([raw]))


def feature_schema() -> dict:
    return {
        "version": FEATURE_SCHEMA_VERSION,
        "columns": FEATURE_COLUMNS,
        "raw_required": REQUIRED_RAW,
        "raw_optional": OPTIONAL_RAW,
        "limits": {k: list(v) for k, v in LIMITS.items()},
    }
