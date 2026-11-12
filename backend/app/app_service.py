"""Business logic shared by applicant, reviewer and admin routes."""
from __future__ import annotations

import math
import uuid
from datetime import datetime

import pandas as pd
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import event_view, log_event
from .cashflow import analyze
from .db import utcnow
from .explain import safe_explanation  # noqa: F401  (kept for symmetry with predict module)
from .features import InvalidInputError, build_features_single
from .models import (Application, Assessment, Explanation, FeatureSnapshot, ModelVersion, ReviewDecision, Transaction,
                     Upload)
from .policy import DemoPolicy
from .predict import predict_one
from .registry import load_active_bundle
from .schemas import LoanApplication
from .workflow import EDITABLE, InvalidTransition, VISIBLE_TO_REVIEWERS, transition

POLICY = DemoPolicy()
INTERNAL_ONLY_EXPLANATION_KEYS = ("contributions", "global_importance")
APPLICANT_TIMELINE_ACTIONS = {"application.created", "application.status_changed", "application.updated", "upload.created",
                              "info_request.created", "info_request.responded", "review.decision_recorded"}
APPLICANT_TIMELINE_DETAIL_KEYS = ("status_from", "status_to", "decision")


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") + "Z" if dt else None


def clean_json(value):
    """Make numpy/NaN values JSON-safe (NaN -> None)."""
    if isinstance(value, dict):
        return {k: clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


# ---------------- access helpers ----------------
def get_owned_application(db: Session, user, app_id: str) -> Application:
    """404 (not 403) for other people's applications, so ids cannot be probed."""
    app = db.get(Application, app_id)
    if app is None or app.user_id != user.id:
        raise HTTPException(status_code=404, detail="Application not found.")
    return app


def get_reviewable_application(db: Session, reviewer, app_id: str) -> Application:
    app = db.get(Application, app_id)
    if app is None or app.status not in VISIBLE_TO_REVIEWERS:
        raise HTTPException(status_code=404, detail="Application not found.")
    if app.user_id == reviewer.id:
        raise HTTPException(status_code=403, detail="You cannot review your own application.")
    return app


def require_editable(app: Application) -> None:
    if app.status not in EDITABLE:
        raise HTTPException(status_code=409, detail=f"This application cannot be changed while it is '{app.status}'.")


def move(db, app, new_status, actor, details=None):
    try:
        transition(db, app, new_status, actor, details)
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ---------------- transactions / cash flow ----------------
def transactions_dataframe(upload: Upload) -> pd.DataFrame:
    rows = [{"key": t.key, "row": t.row, "transaction_id": t.transaction_id, "date": pd.Timestamp(t.date),
             "description": t.description, "amount": t.amount, "direction": t.direction, "balance": t.balance,
             "due_date": pd.Timestamp(t.due_date) if t.due_date else pd.NaT,
             "payment_date": pd.Timestamp(t.payment_date) if t.payment_date else pd.NaT,
             "category": t.category, "category_source": t.category_source, "confidence": t.confidence}
            for t in upload.transactions]
    return pd.DataFrame(rows)


def cashflow_for(app: Application) -> dict | None:
    if app.upload is None or not app.upload.transactions:
        return None
    return clean_json(analyze(transactions_dataframe(app.upload)))


def tx_view(t: Transaction) -> dict:
    return {"id": t.id, "key": t.key, "row": t.row, "date": t.date.isoformat(), "description": t.description,
            "amount": t.amount, "direction": t.direction, "category": t.category,
            "category_source": t.category_source, "confidence": t.confidence}


def store_upload(db: Session, app: Application, filename: str, size: int, parsed, tx_df: pd.DataFrame) -> Upload:
    if app.upload is not None:
        db.delete(app.upload)
        db.flush()
    up = Upload(application_id=app.id, filename=(filename or "upload.csv").replace("\\", "/").split("/")[-1][:255],
                size_bytes=size, rows_total=parsed.stats["rows_total"], rows_valid=parsed.stats["rows_valid"],
                rows_with_errors=parsed.stats["rows_with_errors"], duplicates_excluded=parsed.stats["duplicates_excluded"],
                date_format=parsed.date_format, issues=parsed.issues)
    for r in tx_df.itertuples():
        up.transactions.append(Transaction(
            key=str(r.key)[:120], row=int(r.row), transaction_id=r.transaction_id if isinstance(r.transaction_id, str) else None,
            date=r.date.date(), description=str(r.description)[:500], amount=float(r.amount), direction=r.direction,
            balance=None if r.balance is None or pd.isna(r.balance) else float(r.balance),
            due_date=None if pd.isna(r.due_date) else r.due_date.date(),
            payment_date=None if pd.isna(r.payment_date) else r.payment_date.date(),
            category=r.category, category_source=r.category_source, confidence=r.confidence))
    app.upload = up
    db.flush()
    return up


# ---------------- assessments ----------------
def run_assessment(db: Session, user, app: Application, is_preview: bool) -> Assessment:
    bundle, mv = load_active_bundle(db, "simulation")
    inputs = dict(app.loan_inputs)
    try:
        result = predict_one(bundle, inputs, detail="full")
    except InvalidInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    explanation = result.pop("explanation")
    prob, ratio = result["default_probability_simulated"], result["derived_values"]["total_emi_to_income"]
    policy = POLICY.evaluate(prob, ratio)
    feats = build_features_single(inputs).iloc[0].to_dict()
    a = Assessment(application_id=app.id, is_preview=is_preview, model_version_id=mv.id, model_version=mv.version,
                   feature_schema_version=result["feature_schema_version"], policy_version=POLICY.version,
                   calibration_method=result["calibration_method"], default_probability=prob,
                   uncalibrated_score=result["uncalibrated_model_score"], policy_result=policy,
                   result=clean_json(result), created_by=user.id)
    a.feature_snapshot = FeatureSnapshot(input_snapshot=clean_json(inputs), features=clean_json(feats),
                                         cashflow_summary=cashflow_for(app))
    a.explanation = Explanation(status=explanation["status"], method=explanation.get("method"),
                                version=explanation.get("version"), payload=clean_json(explanation))
    app.assessments.append(a)
    db.flush()
    log_event(db, user, "assessment.created", "assessment", a.id, app.id,
              {"is_preview": is_preview, "model_version": mv.version, "policy_version": POLICY.version})
    return a


def explanation_for(payload: dict, internal: bool) -> dict:
    if internal or payload.get("status") != "available":
        return payload
    out = {k: v for k, v in payload.items() if k not in INTERNAL_ONLY_EXPLANATION_KEYS}
    out["detail"] = "summary"
    return out


def assessment_view(a: Assessment, internal: bool) -> dict:
    return {"id": a.id, "is_preview": a.is_preview, "created_at": iso(a.created_at), "model_version": a.model_version,
            "feature_schema_version": a.feature_schema_version, "policy_version": a.policy_version,
            "policy_result": a.policy_result,
            "result": {**a.result, "explanation": explanation_for(a.explanation.payload, internal)}}


def official_assessment(app: Application) -> Assessment | None:
    official = [a for a in app.assessments if not a.is_preview]
    return official[-1] if official else None


def latest_assessment(app: Application) -> Assessment | None:
    return app.assessments[-1] if app.assessments else None


# ---------------- submission ----------------
def review_reasons(app: Application, assessment: Assessment, cashflow: dict | None) -> list[dict]:
    reasons = [{"code": "demo_policy_all_cases_reviewed",
                "message": "Demonstration policy: every submission is reviewed by a human."}]
    if app.loan_inputs.get("credit_history_months") is None:
        reasons.append({"code": "credit_history_unknown", "message": "Credit history length is unknown (not treated as zero)."})
    if cashflow is None:
        reasons.append({"code": "cashflow_not_provided", "message": "No transaction file was provided."})
    else:
        if not cashflow["coverage"]["sufficient_for_analysis"]:
            reasons.append({"code": "cashflow_coverage_insufficient",
                            "message": "; ".join(cashflow["coverage"]["reasons"]) or "Insufficient statement coverage."})
        share = (cashflow.get("missingness") or {}).get("low_confidence_value_share")
        if share is not None and share > 0.3:
            reasons.append({"code": "cashflow_uncertain_categories",
                            "message": f"{share:.0%} of transaction value is in low-confidence categories."})
        if app.upload and app.upload.rows_with_errors > 0:
            reasons.append({"code": "upload_row_errors", "message": f"{app.upload.rows_with_errors} uploaded row(s) had errors and were excluded."})
    if not assessment.policy_result["passes"]:
        reasons.append({"code": "policy_rules_not_met", "message": "One or more demonstration policy rules were not met."})
    return reasons


def submission_problems(app: Application) -> list[str]:
    problems = []
    try:
        LoanApplication(**app.loan_inputs)
        build_features_single(app.loan_inputs)
    except Exception as exc:  # pydantic or feature validation
        problems.append(f"Loan details are invalid: {str(exc).splitlines()[0][:160]}")
    return problems


def submit_application(db: Session, user, app: Application) -> Application:
    if app.status not in EDITABLE:
        raise HTTPException(status_code=409, detail=f"An application in status '{app.status}' cannot be submitted.")
    load_active_bundle(db, "simulation")          # fail early (503 via caller) if no active model
    if any(r.responded_at is None for r in app.info_requests):
        # Checked BEFORE any state change so the application stays 'info_requested' and can still be answered.
        raise HTTPException(status_code=422, detail="Please respond to the reviewer's information request before resubmitting.")
    move(db, app, "submitted", user)
    move(db, app, "validation", user)
    problems = submission_problems(app)
    if problems:
        move(db, app, "draft", user, {"reason_count": len(problems)})
        db.commit()
        raise HTTPException(status_code=422, detail={"message": "The application did not pass validation.", "problems": problems})
    assessment = run_assessment(db, user, app, is_preview=False)
    move(db, app, "assessed", user)
    reasons = review_reasons(app, assessment, assessment.feature_snapshot.cashflow_summary)
    app.review_reasons = reasons
    app.submitted_at = utcnow()
    move(db, app, "manual_review", user, {"reason_count": len(reasons)})
    return app


# ---------------- views ----------------
def decision_view(d: ReviewDecision, internal: bool) -> dict:
    out = {"id": d.id, "decision": d.decision, "reason": d.reason, "created_at": iso(d.created_at)}
    if internal:
        out.update({"policy_recommendation": d.policy_recommendation, "is_override": d.is_override,
                    "override_reason": d.override_reason, "assessment_id": d.assessment_id})
    return out


def info_request_view(r) -> dict:
    return {"id": r.id, "message": r.message, "created_at": iso(r.created_at), "response": r.response,
            "responded_at": iso(r.responded_at)}


def summary_row(app: Application) -> dict:
    off = official_assessment(app)
    last = app.decisions[-1] if app.decisions else None
    return {"id": app.id, "status": app.status, "created_at": iso(app.created_at), "updated_at": iso(app.updated_at),
            "submitted_at": iso(app.submitted_at), "loan_amount": app.loan_inputs.get("loan_amount"),
            "tenure_months": app.loan_inputs.get("tenure_months"),
            "probability": off.default_probability if off else None, "decision": last.decision if last else None}


def upload_view(up: Upload | None) -> dict | None:
    if up is None:
        return None
    return {"filename": up.filename, "size_bytes": up.size_bytes, "rows_total": up.rows_total, "rows_valid": up.rows_valid,
            "rows_with_errors": up.rows_with_errors, "duplicates_excluded": up.duplicates_excluded,
            "date_format": up.date_format, "issues": up.issues, "uploaded_at": iso(up.uploaded_at)}


def timeline(db: Session, app_id: str, applicant_view: bool) -> list[dict]:
    from .models import AuditEvent
    events = db.scalars(select(AuditEvent).where(AuditEvent.application_id == app_id).order_by(AuditEvent.id)).all()
    if not applicant_view:
        return [event_view(e) for e in events]
    return [{"ts": iso(e.ts), "action": e.action,
             "details": {k: v for k, v in e.details.items() if k in APPLICANT_TIMELINE_DETAIL_KEYS}}
            for e in events if e.action in APPLICANT_TIMELINE_ACTIONS]


def applicant_view(db: Session, app: Application) -> dict:
    latest = latest_assessment(app)
    return {**summary_row(app), "loan_inputs": app.loan_inputs, "upload": upload_view(app.upload),
            "editable": app.status in EDITABLE,
            "assessment": assessment_view(latest, internal=False) if latest else None,
            "info_requests": [info_request_view(r) for r in app.info_requests],
            "final_decision": decision_view(app.decisions[-1], internal=False) if app.decisions else None,
            "timeline": timeline(db, app.id, applicant_view=True)}


def input_quality(app: Application, cashflow: dict | None) -> dict:
    return {"credit_history": "unknown" if app.loan_inputs.get("credit_history_months") is None else "provided",
            "cashflow_provided": cashflow is not None,
            "cashflow_sufficient": None if cashflow is None else cashflow["coverage"]["sufficient_for_analysis"],
            "upload_rows_with_errors": app.upload.rows_with_errors if app.upload else None,
            "upload_duplicates_excluded": app.upload.duplicates_excluded if app.upload else None,
            "low_confidence_value_share": None if cashflow is None else (cashflow.get("missingness") or {}).get("low_confidence_value_share")}


def reviewer_view(db: Session, app: Application) -> dict:
    off = official_assessment(app)
    cashflow = off.feature_snapshot.cashflow_summary if off and off.feature_snapshot else None
    txs = sorted(app.upload.transactions, key=lambda t: ({"low": 0, "medium": 1, "high": 2}[t.confidence], t.row)) if app.upload else []
    return {**summary_row(app), "applicant_ref": f"U{app.user_id}", "loan_inputs": app.loan_inputs,
            "review_reasons": app.review_reasons, "input_quality": input_quality(app, cashflow),
            "upload": upload_view(app.upload), "transactions": [tx_view(t) for t in txs[:500]],
            "cashflow": cashflow,
            "assessment": assessment_view(off, internal=True) if off else None,
            "preview_assessments": sum(1 for a in app.assessments if a.is_preview),
            "policy_recommendation": ("demo_approved" if off and off.policy_result["passes"] else "demo_declined") if off else None,
            "info_requests": [info_request_view(r) for r in app.info_requests],
            "decisions": [decision_view(d, internal=True) for d in app.decisions],
            "timeline": timeline(db, app.id, applicant_view=False)}


def new_application_id() -> str:
    return str(uuid.uuid4())
