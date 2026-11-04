# Data dictionary (feature schema 1.0.0)

| Field | Type | Allowed range | Notes |
|---|---|---|---|
| monthly_income | float | 1 – 10,000,000 | Must be > 0 |
| loan_amount | float | 1 – 100,000,000 | Principal |
| tenure_months | int | 3 – 360 | |
| annual_interest_rate | float (%) | 0 – 60 | 0 uses principal / tenure |
| existing_emi | float | 0 – 10,000,000 | Monthly obligations already running |
| age | int | 18 – 100 | |
| employment_years | float | 0 – 60 | |
| num_existing_loans | int | 0 – 50 | |
| credit_history_months | float or null | 0 – 1200 | null = unknown (not zero, not bad) |

Derived (computed only in `app/features.py`):
- credit_history_missing = 1 if credit_history_months is unknown
- new_loan_emi = reducing-balance EMI of the requested loan
- total_emi = new_loan_emi + existing_emi
- total_emi_to_income = total_emi / monthly_income (can exceed 1; not clipped)
- loan_to_annual_income = loan_amount / (12 * monthly_income)

Out-of-range values are rejected with an error, never silently clipped.
