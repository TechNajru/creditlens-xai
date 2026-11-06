"""Demonstration policy engine (kept SEPARATE from the risk model).

The model estimates a (simulated) default probability. The policy turns that estimate plus
transparent rules into a pass/fail on each rule. All thresholds are EXPERIMENTAL demonstration
values, not a validated lending policy, and nothing here approves or denies a real loan.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

POLICY_DISCLAIMER = ("Experimental demonstration thresholds. Not a validated lending policy; "
                     "passing every rule does not mean a real lender would approve.")


@dataclass(frozen=True)
class DemoPolicy:
    version: str = "demo-policy-1.0"
    max_default_probability: float = 0.20
    max_total_emi_to_income: float = 0.50
    min_loan_amount: float = 10_000.0
    min_tenure_months: int = 6
    max_tenure_months: int = 84

    def describe(self) -> dict:
        return {**asdict(self), "disclaimer": POLICY_DISCLAIMER}

    def feasibility_issues(self, loan_amount: float, tenure_months: float) -> list[str]:
        """Product limits (can the request even be offered?), independent of risk."""
        issues = []
        if loan_amount < self.min_loan_amount:
            issues.append(f"loan amount is below the demo minimum of {self.min_loan_amount:,.0f}")
        if not self.min_tenure_months <= tenure_months <= self.max_tenure_months:
            issues.append(f"tenure must be {self.min_tenure_months}-{self.max_tenure_months} months in this demo")
        return issues

    def evaluate(self, probability: float, total_emi_to_income: float) -> dict:
        rules = [
            {"rule": "simulated default probability at or below limit", "threshold": self.max_default_probability,
             "value": probability, "passed": probability <= self.max_default_probability},
            {"rule": "total EMI as a share of income at or below limit", "threshold": self.max_total_emi_to_income,
             "value": total_emi_to_income, "passed": total_emi_to_income <= self.max_total_emi_to_income},
        ]
        return {"policy_version": self.version, "passes": all(r["passed"] for r in rules), "rules": rules}
