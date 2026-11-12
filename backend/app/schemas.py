"""Shared request schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .features import LIMITS


class LoanApplication(BaseModel):
    monthly_income: float = Field(gt=0, le=LIMITS["monthly_income"][1])
    loan_amount: float = Field(gt=0, le=LIMITS["loan_amount"][1])
    tenure_months: int = Field(ge=LIMITS["tenure_months"][0], le=LIMITS["tenure_months"][1])
    annual_interest_rate: float = Field(ge=0, le=LIMITS["annual_interest_rate"][1])
    existing_emi: float = Field(ge=0, le=LIMITS["existing_emi"][1])
    age: int = Field(ge=LIMITS["age"][0], le=LIMITS["age"][1])
    employment_years: float = Field(ge=0, le=LIMITS["employment_years"][1])
    num_existing_loans: int = Field(ge=0, le=LIMITS["num_existing_loans"][1])
    credit_history_months: float | None = Field(
        default=None, ge=0, le=LIMITS["credit_history_months"][1],
        description="Leave null if unknown. Unknown is NOT the same as zero.")
