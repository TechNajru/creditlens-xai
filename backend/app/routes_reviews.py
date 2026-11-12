"""Reviewer workflow. Model output (Assessment) and human decision (ReviewDecision) are separate records.

Reviewers see a pseudonymous applicant reference, never an email. Overriding the policy recommendation requires a
written reason. A reviewer cannot review their own application.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import app_service as svc
from .audit import log_event
from .db import get_db
from .deps import reviewer_user
from .models import Application, InfoRequest, ReviewDecision, User
from .workflow import VISIBLE_TO_REVIEWERS

router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])
MIN_TEXT = 10


class InfoRequestIn(BaseModel):
    message: str = Field(min_length=MIN_TEXT, max_length=1000)


class DecisionIn(BaseModel):
    decision: Literal["demo_approved", "demo_declined"]
    reason: str = Field(min_length=MIN_TEXT, max_length=2000)
    override_reason: str | None = Field(default=None, max_length=2000)


@router.get("/queue")
def queue(status: Literal["manual_review", "info_requested", "final_demo_decision", "all"] = Query("manual_review"),
          reviewer: User = Depends(reviewer_user), db: Session = Depends(get_db)):
    wanted = VISIBLE_TO_REVIEWERS if status == "all" else {status}
    apps = db.scalars(select(Application).where(Application.status.in_(wanted), Application.user_id != reviewer.id)
                      .order_by(Application.submitted_at.asc()).limit(200)).all()
    rows = []
    for a in apps:
        row = svc.summary_row(a)
        off = svc.official_assessment(a)
        row.update({"applicant_ref": f"U{a.user_id}", "review_reason_codes": [r["code"] for r in a.review_reasons],
                    "policy_passes": off.policy_result["passes"] if off else None})
        rows.append(row)
    return {"applications": rows}


@router.get("/{app_id}")
def review_detail(app_id: str, reviewer: User = Depends(reviewer_user), db: Session = Depends(get_db)):
    app = svc.get_reviewable_application(db, reviewer, app_id)
    log_event(db, reviewer, "review.viewed", "application", app.id, app.id)
    db.commit()
    return svc.reviewer_view(db, app)


@router.post("/{app_id}/request-info")
def request_info(app_id: str, body: InfoRequestIn, reviewer: User = Depends(reviewer_user), db: Session = Depends(get_db)):
    app = svc.get_reviewable_application(db, reviewer, app_id)
    if app.status != "manual_review":
        raise HTTPException(status_code=409, detail=f"Information cannot be requested while the application is '{app.status}'.")
    req = InfoRequest(application_id=app.id, reviewer_id=reviewer.id, message=body.message.strip())
    app.info_requests.append(req)
    db.flush()
    svc.move(db, app, "info_requested", reviewer)
    log_event(db, reviewer, "info_request.created", "info_request", req.id, app.id)
    db.commit()
    return svc.reviewer_view(db, app)


@router.post("/{app_id}/decision")
def record_decision(app_id: str, body: DecisionIn, reviewer: User = Depends(reviewer_user), db: Session = Depends(get_db)):
    app = svc.get_reviewable_application(db, reviewer, app_id)
    if app.status != "manual_review":
        raise HTTPException(status_code=409, detail=f"A decision cannot be recorded while the application is '{app.status}'.")
    off = svc.official_assessment(app)
    if off is None:
        raise HTTPException(status_code=409, detail="This application has no official assessment.")
    recommendation = "demo_approved" if off.policy_result["passes"] else "demo_declined"
    is_override = body.decision != recommendation
    if is_override and len((body.override_reason or "").strip()) < MIN_TEXT:
        raise HTTPException(status_code=422, detail=(
            f"This decision differs from the policy recommendation ({recommendation}). "
            f"An override reason of at least {MIN_TEXT} characters is required."))
    d = ReviewDecision(application_id=app.id, assessment_id=off.id, reviewer_id=reviewer.id, decision=body.decision,
                       reason=body.reason.strip(), policy_recommendation=recommendation, is_override=is_override,
                       override_reason=(body.override_reason or "").strip() or None)
    app.decisions.append(d)
    db.flush()
    svc.move(db, app, "final_demo_decision", reviewer, {"decision": body.decision, "is_override": is_override})
    log_event(db, reviewer, "review.decision_recorded", "review_decision", d.id, app.id,
              {"decision": body.decision, "is_override": is_override})
    db.commit()
    return svc.reviewer_view(db, app)
