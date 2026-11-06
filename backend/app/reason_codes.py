"""Plain-language labels and value formatting for explanation output (no model logic here)."""
from __future__ import annotations

import math

LOAN_LABELS = {
    "monthly_income": ("Monthly income", "money"),
    "loan_amount": ("Requested loan amount", "money"),
    "tenure_months": ("Loan tenure", "months"),
    "annual_interest_rate": ("Interest rate", "rate"),
    "existing_emi": ("Existing monthly EMI", "money"),
    "age": ("Age", "int"),
    "employment_years": ("Years in current employment", "years"),
    "num_existing_loans": ("Number of existing loans", "int"),
    "credit_history_months": ("Credit history length", "months"),
    "credit_history_missing": ("Credit history availability", "flag_missing"),
    "new_loan_emi": ("EMI of the requested loan", "money"),
    "total_emi": ("Total monthly EMI (new + existing)", "money"),
    "total_emi_to_income": ("Total EMI as a share of monthly income", "pct"),
    "loan_to_annual_income": ("Loan amount relative to annual income", "ratio"),
}

_MONTHS = {1: "Sep 2005", 2: "Aug 2005", 3: "Jul 2005", 4: "Jun 2005", 5: "May 2005", 6: "Apr 2005"}
PUBLIC_LABELS = {
    "LIMIT_BAL": ("Credit limit", "money"),
    "AGE": ("Age", "int"),
    "utilization_latest": ("Latest bill as a share of credit limit", "pct"),
    "months_delayed": ("Months with a payment delay (of the last 6)", "int"),
    "payment_ratio_latest": ("Latest payment as a share of latest bill", "pct"),
}
for _pay, _i in zip(["PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6"], range(1, 7)):
    PUBLIC_LABELS[_pay] = (f"Repayment status, {_MONTHS[_i]}", "pay")
for _i in range(1, 7):
    PUBLIC_LABELS[f"BILL_AMT{_i}"] = (f"Bill statement, {_MONTHS[_i]}", "money")
    PUBLIC_LABELS[f"PAY_AMT{_i}"] = (f"Payment made, {_MONTHS[_i]}", "money")


def format_value(value, kind: str, currency: str = "") -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "unknown (not treated as zero)"
    v = float(value)
    if kind == "money":
        return f"{currency}{v:,.0f}"
    if kind == "pct":
        return f"{v * 100:.0f}%"
    if kind == "ratio":
        return f"{v:.1f}x"
    if kind == "months":
        return f"{v:.0f} months"
    if kind == "years":
        return f"{v:.1f} years"
    if kind == "rate":
        return f"{v:.1f}% per year"
    if kind == "flag_missing":
        return "not available" if v == 1 else "available"
    if kind == "pay":
        if v == -1:
            return "paid duly (-1)"
        if v >= 1:
            return f"{v:.0f} month(s) delayed"
        return f"code {v:.0f} (not defined by the dataset source)"
    return f"{v:.0f}"


def make_describer(labels: dict, currency: str = ""):
    def describe(feature: str, value) -> tuple[str, str]:
        label, kind = labels.get(feature, (feature, "float"))
        return label, format_value(value, kind, currency)
    return describe


describe_loan = make_describer(LOAN_LABELS)
describe_public = make_describer(PUBLIC_LABELS, "NT$")
