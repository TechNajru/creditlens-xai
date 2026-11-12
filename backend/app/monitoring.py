"""System-level monitoring from the application database.

Input drift (what people submit) can be watched from inputs alone. Performance degradation (are predictions
still right?) CANNOT be measured here: the demo never observes repayment outcomes.
"""
from __future__ import annotations

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Application, Assessment, ReviewDecision

NOTES = [
    "Input and prediction distributions can show drift in WHO is applying; they do not show whether predictions are correct.",
    "Performance degradation cannot be measured without repayment outcomes, which this demonstration does not collect.",
    "Counts include only data currently in the database (deleted applications are gone).",
]


def monitoring_summary(db: Session) -> dict:
    by_status = {s: n for s, n in db.execute(select(Application.status, func.count()).group_by(Application.status))}
    rows = db.execute(select(Assessment.is_preview, Assessment.model_version, Assessment.default_probability)).all()
    official = [r for r in rows if not r[0]]
    probs = np.array([r[2] for r in official], dtype=float)
    by_model: dict[str, int] = {}
    for r in official:
        by_model[r[1]] = by_model.get(r[1], 0) + 1
    dist = None
    if len(probs):
        hist, _ = np.histogram(probs, bins=10, range=(0, 1))
        dist = {"n": int(len(probs)), "mean": float(probs.mean()),
                "p10": float(np.percentile(probs, 10)), "p50": float(np.percentile(probs, 50)),
                "p90": float(np.percentile(probs, 90)), "histogram_10_bins": [int(x) for x in hist]}
    submitted = db.scalars(select(Application).where(Application.submitted_at.is_not(None))).all()
    n = len(submitted)
    missing = {"submitted_applications": n,
               "credit_history_unknown_share": (sum(1 for a in submitted if a.loan_inputs.get("credit_history_months") is None) / n) if n else None,
               "no_cashflow_file_share": (sum(1 for a in submitted if a.upload is None) / n) if n else None}
    decisions = db.scalars(select(ReviewDecision)).all()
    d = len(decisions)
    review = {"decisions": d,
              "approved_share": (sum(1 for x in decisions if x.decision == "demo_approved") / d) if d else None,
              "override_share": (sum(1 for x in decisions if x.is_override) / d) if d else None}
    return {"applications_by_status": by_status,
            "assessments": {"official": len(official), "preview": len(rows) - len(official), "official_by_model_version": by_model},
            "prediction_distribution": dist, "input_missingness": missing, "review": review, "notes": NOTES}
