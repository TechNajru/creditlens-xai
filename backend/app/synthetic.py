"""SYNTHETIC borrower generator (Track B simulation).

Everything produced here is fictional. The outcome label is produced by a
hand-written rule plus noise, so a model trained on it only learns that rule.
It does NOT show anything about real borrower behaviour.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .features import TARGET_COLUMN, build_features

DATA_PROVENANCE = "SYNTHETIC simulation data (fictional; not real borrowers)"


def generate_synthetic_applications(n: int = 20_000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    income = np.clip(rng.lognormal(mean=10.6, sigma=0.5, size=n), 8_000, 600_000).round(0)
    age = rng.integers(21, 66, size=n)
    employment_years = np.minimum(age - 18, rng.exponential(6, size=n)).round(1)
    num_loans = rng.poisson(0.9, size=n)
    existing_emi = np.where(num_loans > 0,
                            income * rng.beta(2, 8, size=n) * np.minimum(num_loans, 3) / 2,
                            0.0).round(0)
    tenure = rng.choice([12, 24, 36, 48, 60], size=n, p=[0.15, 0.25, 0.3, 0.15, 0.15])
    rate = rng.uniform(9, 24, size=n).round(2)
    loan_amount = (income * rng.uniform(1.5, 20, size=n)).round(0)
    history = rng.exponential(60, size=n).round(0)
    thin_file = rng.random(n) < 0.25
    history = np.where(thin_file, np.nan, history)

    raw = pd.DataFrame({
        "monthly_income": income, "loan_amount": loan_amount, "tenure_months": tenure,
        "annual_interest_rate": rate, "existing_emi": existing_emi, "age": age,
        "employment_years": employment_years, "num_existing_loans": num_loans,
        "credit_history_months": history,
    })

    feats = build_features(raw)
    logit = (-4.2
             + 4.5 * feats["total_emi_to_income"]
             + 0.15 * feats["num_existing_loans"]
             - 0.03 * feats["employment_years"]
             + 0.35 * feats["credit_history_missing"]
             - 0.004 * feats["credit_history_months"].fillna(0)
             + rng.normal(0, 0.6, size=n))
    prob = 1 / (1 + np.exp(-logit))
    raw[TARGET_COLUMN] = (rng.random(n) < prob).astype(int)
    return raw
