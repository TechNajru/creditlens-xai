# Public-data model dictionary (schema public-1.0.0)

Raw inputs (20): `LIMIT_BAL` (NT$ credit limit), `AGE`, `PAY_0, PAY_2..PAY_6` (repayment status, Sept → April 2005),
`BILL_AMT1..6` (statement amounts, can be negative), `PAY_AMT1..6` (previous payments, >= 0). Month 1 = September 2005.

PAY codes: -1 = paid duly, 1..9 = months of delay (UCI). -2 and 0 occur in the data but are undefined by UCI; used as given.

Derived (computed only in `app/public_features.py`):
- `utilization_latest` = BILL_AMT1 / LIMIT_BAL (can be negative or > 1; not clipped)
- `months_delayed` = number of PAY_x with code >= 1
- `payment_ratio_latest` = PAY_AMT1 / BILL_AMT1 when BILL_AMT1 > 0, otherwise NaN (undefined, not 0).
  Extreme values exist (max ~11,454 on the full data); not clipped.

Not model inputs: `ID`, `SEX`, `EDUCATION`, `MARRIAGE` (kept for the fairness audit only), and the target.
