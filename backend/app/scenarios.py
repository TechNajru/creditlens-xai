"""What-if simulator and constrained counterfactual search (loan simulation model only).

Rules enforced here
- Only directly controllable application terms may change: loan_amount, tenure_months, annual_interest_rate.
  existing_emi may change only as an explicitly HYPOTHETICAL debt-reduction scenario.
- Income, age, employment history, number of loans and credit history are historical facts or personal
  characteristics: they can never be changed (the code rejects them and tests prove they stay fixed).
- Every alternative is re-scored through the shared feature pipeline, so EMI, total EMI ratio and
  interest are recalculated, never patched.
- A model-output change is an association from a model trained on synthetic data, not a proven causal
  effect, and says nothing about real-world approval.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .features import RAW_COLUMNS, build_features
from .policy import DemoPolicy
from .predict import ModelBundle

MUTABLE = ("loan_amount", "tenure_months", "annual_interest_rate", "existing_emi")
HYPOTHETICAL = frozenset({"existing_emi"})
IMMUTABLE = tuple(c for c in RAW_COLUMNS if c not in MUTABLE)

NOTES = [
    "Model-output changes are associations from a model trained on synthetic data, not proven causal effects.",
    "Real-world approval is not guaranteed. The policy here is an experimental demonstration.",
]
AMOUNT_WEIGHT, TENURE_WEIGHT, DEBT_WEIGHT = 1.0, 0.5, 2.0   # design choices for ranking, see docs/scenarios.md


class ScenarioError(ValueError):
    pass


def apply_changes(base: dict, changes: dict) -> dict:
    unknown = [k for k in changes if k not in RAW_COLUMNS]
    if unknown:
        raise ScenarioError(f"Unknown fields: {unknown}")
    locked = [k for k in changes if k in IMMUTABLE]
    if locked:
        raise ScenarioError(f"These inputs cannot be changed in a scenario (historical facts or personal "
                            f"characteristics): {locked}. Allowed: {list(MUTABLE)}")
    return {**base, **changes}


def _evaluate(bundle: ModelBundle, rows: list[dict], policy: DemoPolicy) -> list[dict]:
    X = build_features(pd.DataFrame(rows))          # shared feature code: EMI and ratios recalculated
    raw_p = bundle.pipeline.predict_proba(X)[:, 1]
    cal_p = bundle.calibrator.transform(raw_p)
    out = []
    for row, (_, f), p in zip(rows, X.iterrows(), cal_p):
        emi, tenure, amount = float(f["new_loan_emi"]), float(row["tenure_months"]), float(row["loan_amount"])
        pol = policy.evaluate(float(p), float(f["total_emi_to_income"]))
        issues = policy.feasibility_issues(amount, tenure)
        out.append({
            "inputs": {k: row[k] for k in RAW_COLUMNS},
            "metrics": {"new_loan_emi": emi, "total_emi": float(f["total_emi"]),
                        "total_emi_to_income": float(f["total_emi_to_income"]),
                        "total_interest": emi * tenure - amount, "default_probability_simulated": float(p)},
            "policy": pol, "feasibility_issues": issues, "meets_policy": bool(pol["passes"] and not issues),
        })
    return out


def _describe_change(base: dict, new: dict) -> dict:
    changed = {k: {"from": base[k], "to": new[k]} for k in MUTABLE if base[k] != new[k]}
    return {"changed_inputs": changed,
            "unchanged_inputs": [k for k in RAW_COLUMNS if k not in changed],
            "hypothetical": sorted(k for k in changed if k in HYPOTHETICAL)}


def _delta(base_eval: dict, ev: dict) -> dict:
    b, m = base_eval["metrics"], ev["metrics"]
    return {k: m[k] - b[k] for k in b}


def what_if(bundle: ModelBundle, base: dict, scenarios: list[dict], policy: DemoPolicy) -> dict:
    merged = [apply_changes(base, s["changes"]) for s in scenarios]
    evals = _evaluate(bundle, [base] + merged, policy)
    result = []
    for s, row, ev in zip(scenarios, merged, evals[1:]):
        result.append({"name": s["name"], **_describe_change(base, row), **ev, "delta_vs_base": _delta(evals[0], ev)})
    return {"policy": policy.describe(), "base": evals[0], "scenarios": result, "notes": NOTES}


def _grid(base: dict, policy: DemoPolicy, allow_debt: bool):
    amount0, tenure0, debt0 = float(base["loan_amount"]), int(base["tenure_months"]), float(base["existing_emi"])
    step = 1000.0 if amount0 >= 100_000 else 100.0
    amounts = {amount0}
    for f in np.arange(0.95, 0.20, -0.05):
        a = round(amount0 * f / step) * step
        if policy.min_loan_amount <= a < amount0:
            amounts.add(float(a))
    tenures = {tenure0} | set(range(policy.min_tenure_months, policy.max_tenure_months + 1, 6))
    debts = {debt0}
    if allow_debt and debt0 > 0:
        debts |= {round(debt0 * f, 2) for f in (0.75, 0.5, 0.25, 0.0)}
    return sorted(amounts, reverse=True), sorted(tenures), sorted(debts, reverse=True)


def _cost(base: dict, row: dict) -> float:
    amount_cut = max(0.0, (base["loan_amount"] - row["loan_amount"]) / base["loan_amount"])
    tenure_change = abs(row["tenure_months"] - base["tenure_months"]) / 78.0
    debt_cut = (base["existing_emi"] - row["existing_emi"]) / base["existing_emi"] if base["existing_emi"] > 0 else 0.0
    return AMOUNT_WEIGHT * amount_cut + TENURE_WEIGHT * tenure_change + DEBT_WEIGHT * max(0.0, debt_cut)


def counterfactuals(bundle: ModelBundle, base: dict, policy: DemoPolicy,
                    allow_hypothetical_debt_reduction: bool = False, max_results: int = 3) -> dict:
    base_eval = _evaluate(bundle, [base], policy)[0]
    common = {"policy": policy.describe(), "base": base_eval, "notes": NOTES,
              "search": {"mutable_inputs": list(MUTABLE[:3]) + (["existing_emi (hypothetical)"] if allow_hypothetical_debt_reduction else []),
                         "never_changed": list(IMMUTABLE),
                         "searched_range": {"loan_amount": [round(max(policy.min_loan_amount, base["loan_amount"] * 0.25)), base["loan_amount"]],
                                            "tenure_months": [policy.min_tenure_months, policy.max_tenure_months]},
                         "ranking": "smaller loan reductions and tenure changes rank first; hypothetical debt "
                                    "reduction is penalised"}}
    if base_eval["meets_policy"]:
        return {**common, "status": "already_meets_policy", "alternatives": [], "closest_attempt": None,
                "message": "The requested terms already meet every demonstration rule. No alternative is needed."}

    amounts, tenures, debts = _grid(base, policy, allow_hypothetical_debt_reduction)
    rows = [{**base, "loan_amount": a, "tenure_months": t, "existing_emi": d}
            for a in amounts for t in tenures for d in debts]
    rows = [r for r in rows if (r["loan_amount"], r["tenure_months"], r["existing_emi"]) !=
            (base["loan_amount"], base["tenure_months"], base["existing_emi"])]
    searched = len(rows)
    evals = _evaluate(bundle, rows, policy)
    for r, e in zip(rows, evals):
        e["_cost"] = _cost(base, r)
    ok = sorted((e for e in evals if e["meets_policy"]), key=lambda e: e["_cost"])[:max_results]

    def pack(e):
        row = e["inputs"]
        return {**_describe_change(base, row), "inputs": row, "metrics": e["metrics"], "policy": e["policy"],
                "feasibility_issues": e["feasibility_issues"], "meets_policy": e["meets_policy"],
                "delta_vs_base": _delta(base_eval, e), "change_cost": round(e["_cost"], 4)}

    if ok:
        return {**common, "status": "found", "alternatives": [pack(e) for e in ok], "closest_attempt": None,
                "search": {**common["search"], "candidates_evaluated": searched},
                "message": f"Found {len(ok)} alternative(s) that meet every demonstration rule."}
    valid = [e for e in evals if not e["feasibility_issues"]]
    closest = min(valid, key=lambda e: e["metrics"]["default_probability_simulated"]) if valid else None
    return {**common, "status": "no_feasible_alternative", "alternatives": [],
            "closest_attempt": pack(closest) if closest else None,
            "search": {**common["search"], "candidates_evaluated": searched},
            "message": "No alternative within the allowed changes meets every demonstration rule. "
                       "The closest attempt (lowest simulated probability) is shown for transparency; it does not pass."}
