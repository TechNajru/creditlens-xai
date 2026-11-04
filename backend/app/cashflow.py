"""Cash-flow summary from categorized transactions.

IMPORTANT: these outputs are descriptive analytics. They are NOT inputs to the risk model
(no labelled dataset links transaction behaviour to repayment outcomes). The result says so.

Key rules
- Internal transfers are excluded from income and spending.
- Income tiers: confirmed (supplied/user-corrected income categories), likely (keyword-guessed
  salary), unverified (UPI inflows and uncategorized credits). UPI inflow is never "verified income".
- Interior months only: the first and last calendar month of a statement may be partial, so
  metrics use months strictly between them that contain data. Gap months are unknown, not zero.
- Unknown is None, never 0. "0 observed debt payments" is reported as an observation, not as
  "no debt".
- Payment timeliness is computed only when due_date AND payment_date exist.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .categorizer import ESSENTIAL

MIN_USABLE_MONTHS = 3
STOP = {"upi", "neft", "imps", "ref", "txn", "to", "from", "by", "cr", "credit", "payment", "pvt", "ltd"}


def _bucket(category: str, source: str, direction: str) -> str:
    if category == "transfer_internal":
        return "transfer_in" if direction == "credit" else "transfer_out"
    if direction == "credit":
        if category in ("income_salary", "income_other"):
            return "income_confirmed" if source in ("supplied", "user_correction") else "income_likely"
        if category == "refund":
            return "refunds"
        return "inflow_unverified"
    if category == "emi_debt":
        return "outflow_debt"
    if category in ESSENTIAL:
        return "outflow_essential"
    if category in ("dining_shopping", "entertainment", "transport"):
        return "outflow_discretionary"
    return "outflow_other"


BUCKETS = ["income_confirmed", "income_likely", "inflow_unverified", "refunds", "outflow_essential",
           "outflow_debt", "outflow_discretionary", "outflow_other", "transfer_in", "transfer_out"]
INFLOW = ["income_confirmed", "income_likely", "inflow_unverified", "refunds"]
OUTFLOW = ["outflow_essential", "outflow_debt", "outflow_discretionary", "outflow_other"]


def _f(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), 2)


def _pattern(desc: str) -> str:
    toks = [t for t in re.sub(r"[^a-z ]", " ", desc.lower()).split() if len(t) >= 3 and t not in STOP]
    return " ".join(toks[:3])


def _recurring(tx: pd.DataFrame, usable_months: list) -> list[dict]:
    cr = tx[tx["bucket"].isin(["income_confirmed", "income_likely", "inflow_unverified"])].copy()
    cr["pattern"] = cr["description"].map(_pattern)
    cr = cr[cr["pattern"] != ""]
    out = []
    for (pat, bucket), g in cr.groupby(["pattern", "bucket"]):
        per_month = g.groupby("month")["amount"].sum()
        if len(per_month) < MIN_USABLE_MONTHS:
            continue
        mean = per_month.mean()
        cv = float(per_month.std(ddof=0) / mean) if mean > 0 else None
        if cv is not None and cv < 0.25:
            out.append({"pattern": pat, "bucket": bucket, "months_seen": int(len(per_month)),
                        "avg_monthly_amount": _f(mean), "amount_cv": _f(cv)})
    return out


def analyze(tx: pd.DataFrame) -> dict:
    if tx.empty:
        return {"used_for_risk_model": False, "coverage": {"sufficient_for_analysis": False,
                "reasons": ["no valid transactions"]}, "monthly": [], "metrics": None}
    t = tx.copy()
    t["bucket"] = [_bucket(c, s, d) for c, s, d in zip(t["category"], t["category_source"], t["direction"])]
    t["month"] = t["date"].dt.to_period("M")

    first, last = t["date"].min(), t["date"].max()
    months = pd.period_range(first.to_period("M"), last.to_period("M"), freq="M")
    pivot = (t.pivot_table(index="month", columns="bucket", values="amount", aggfunc="sum", fill_value=0.0)
             .reindex(months).reindex(columns=BUCKETS))
    has_data = t.groupby("month").size().reindex(months).fillna(0) > 0
    pivot = pivot.fillna(0.0)
    pivot["net_cashflow"] = pivot[INFLOW].sum(axis=1) - pivot[OUTFLOW].sum(axis=1)

    interior = [m for m in months if m != months[0] and m != months[-1]]
    usable = [m for m in interior if has_data[m]]
    gap = [str(m) for m in interior if not has_data[m]]

    monthly = []
    for m in months:
        row = {"month": str(m), "has_data": bool(has_data[m]),
               "role": "edge_partial_possible" if m in (months[0], months[-1]) and len(months) > 1
               else ("usable" if m in usable else "gap")}
        row.update({b: _f(pivot.at[m, b]) for b in BUCKETS + ["net_cashflow"]})
        monthly.append(row)

    reasons = []
    if len(usable) < MIN_USABLE_MONTHS:
        reasons.append(f"fewer than {MIN_USABLE_MONTHS} usable interior months (found {len(usable)})")
    if gap:
        reasons.append(f"gap months with no data: {gap}")
    coverage = {
        "first_date": first.date().isoformat(), "last_date": last.date().isoformat(),
        "span_days": int((last - first).days) + 1, "calendar_months_in_span": len(months),
        "months_with_data": int(has_data.sum()), "usable_interior_months": len(usable),
        "gap_months": gap, "sufficient_for_analysis": len(reasons) == 0, "reasons": reasons,
        "note": "First and last calendar months are excluded because they may be partial.",
    }

    metrics = None
    if usable:
        u = pivot.loc[usable]
        income = u[["income_confirmed", "income_likely"]].sum(axis=1)
        out_tot = u[OUTFLOW].sum(axis=1)
        inc_mean = float(income.mean())
        cv = float(income.std(ddof=1) / inc_mean) if len(usable) >= MIN_USABLE_MONTHS and inc_mean > 0 else None
        debt_mean = float(u["outflow_debt"].mean())
        metrics = {
            "months_used": len(usable),
            "avg_monthly_income_confirmed_or_likely": _f(inc_mean),
            "avg_monthly_income_confirmed_only": _f(u["income_confirmed"].mean()),
            "avg_monthly_unverified_inflow": _f(u["inflow_unverified"].mean()),
            "avg_monthly_outflow": _f(out_tot.mean()),
            "avg_monthly_net_cashflow": _f(u["net_cashflow"].mean()),
            "negative_net_cashflow_months": int((u["net_cashflow"] < 0).sum()),
            "income_variability_cv": _f(cv),
            "avg_monthly_essential_spend": _f(u["outflow_essential"].mean()),
            "observed_monthly_debt_payments": _f(debt_mean),
            "observed_debt_payments_note": "Observed in this statement only. 0 does not prove the "
                                           "applicant has no debt.",
            "observed_debt_to_income": _f(debt_mean / inc_mean) if inc_mean > 0 else None,
        }

    rec = _recurring(t[t["month"].isin(usable)], usable) if usable else []
    recurring_income = sum(r["avg_monthly_amount"] for r in rec if r["bucket"].startswith("income"))

    pay = tx[tx["due_date"].notna() & tx["payment_date"].notna()]
    if len(pay):
        timeliness = {"computed": True, "n_obligations": int(len(pay)),
                      "on_time_rate": _f((pay["payment_date"] <= pay["due_date"]).mean())}
    else:
        timeliness = {"computed": False,
                      "reason": "Requires both due_date and payment_date. Not inferred from transaction dates."}

    non_transfer = t[~t["bucket"].isin(["transfer_in", "transfer_out"])]
    total_val = float(non_transfer["amount"].sum())
    low_val = float(non_transfer.loc[non_transfer["confidence"] == "low", "amount"].sum())
    missingness = {
        "balance_missing_share": _f(t["balance"].isna().mean()),
        "transaction_id_missing_share": _f(t["transaction_id"].isna().mean()),
        "category_not_supplied_share": _f((t["category_source"] != "supplied").mean()),
        "low_confidence_value_share": _f(low_val / total_val) if total_val > 0 else None,
    }
    return {
        "used_for_risk_model": False,
        "purpose": "Descriptive cash-flow analytics. Not used by the risk model.",
        "coverage": coverage, "monthly": monthly, "metrics": metrics,
        "recurring_income_groups": rec,
        "identified_recurring_income_monthly": _f(recurring_income) if rec else None,
        "payment_timeliness": timeliness, "missingness": missingness,
    }
