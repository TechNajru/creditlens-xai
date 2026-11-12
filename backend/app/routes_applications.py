"""Applicant workflow: drafts, uploads, transaction corrections, previews, submission, history, deletion."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import app_service as svc
from . import config
from .audit import log_event
from .categories_api import allowed_categories
from .categorizer import assign_categories
from .db import get_db, utcnow
from .deps import applicant_user
from .ingestion import UploadError, parse_csv
from .models import Application, Assessment, InfoRequest, Transaction, User
from .predict import ModelNotAvailableError
from .schemas import LoanApplication

router = APIRouter(prefix="/api/v1/applications", tags=["applications"])
MAX_LIST = 200


class CategoryIn(BaseModel):
    category: str = Field(max_length=40)


class RespondIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


def _changed_fields(old: dict, new: dict) -> list[str]:
    return [k for k in new if old.get(k) != new.get(k)]


@router.post("", status_code=201)
def create_application(body: LoanApplication, user: User = Depends(applicant_user), db: Session = Depends(get_db)):
    app = Application(id=svc.new_application_id(), user_id=user.id, status="draft", loan_inputs=body.model_dump())
    db.add(app)
    db.flush()
    log_event(db, user, "application.created", "application", app.id, app.id)
    db.commit()
    return svc.applicant_view(db, app)


@router.get("")
def list_applications(user: User = Depends(applicant_user), db: Session = Depends(get_db)):
    apps = db.scalars(select(Application).where(Application.user_id == user.id)
                      .order_by(Application.created_at.desc()).limit(MAX_LIST)).all()
    return {"applications": [svc.summary_row(a) for a in apps]}


@router.get("/{app_id}")
def get_application(app_id: str, user: User = Depends(applicant_user), db: Session = Depends(get_db)):
    return svc.applicant_view(db, svc.get_owned_application(db, user, app_id))


@router.patch("/{app_id}")
def update_application(app_id: str, body: LoanApplication, user: User = Depends(applicant_user), db: Session = Depends(get_db)):
    app = svc.get_owned_application(db, user, app_id)
    svc.require_editable(app)
    new = body.model_dump()
    changed = _changed_fields(app.loan_inputs, new)
    app.loan_inputs = new
    app.updated_at = utcnow()
    # previews no longer describe these inputs
    for a in [a for a in app.assessments if a.is_preview]:
        app.assessments.remove(a)
    log_event(db, user, "application.updated", "application", app.id, app.id, {"changed_fields": changed})
    db.commit()
    return svc.applicant_view(db, app)


@router.delete("/{app_id}")
def delete_application(app_id: str, user: User = Depends(applicant_user), db: Session = Depends(get_db)):
    app = svc.get_owned_application(db, user, app_id)
    from .workflow import DELETABLE
    if app.status not in DELETABLE:
        raise HTTPException(status_code=409, detail=f"An application that is '{app.status}' cannot be deleted right now.")
    log_event(db, user, "application.deleted", "application", app.id, app.id, {"status_from": app.status})
    db.delete(app)       # cascades to upload, transactions, assessments, explanations, decisions
    db.commit()
    return {"deleted": True}


@router.post("/{app_id}/uploads", status_code=201)
async def upload_transactions(app_id: str, file: UploadFile = File(...), user: User = Depends(applicant_user),
                              db: Session = Depends(get_db)):
    app = svc.get_owned_application(db, user, app_id)
    svc.require_editable(app)
    data = await file.read(config.max_upload_bytes() + 1)
    try:
        parsed = parse_csv(data, file.filename)
    except UploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    tx, cat_report = assign_categories(parsed.transactions)
    up = svc.store_upload(db, app, file.filename or "upload.csv", len(data), parsed, tx)
    for a in [a for a in app.assessments if a.is_preview]:
        app.assessments.remove(a)
    app.updated_at = utcnow()
    log_event(db, user, "upload.created", "upload", up.id, app.id,
              {"rows_valid": parsed.stats["rows_valid"], "rows_total": parsed.stats["rows_total"]})
    db.commit()
    return {"upload": svc.upload_view(up), "category_issues": cat_report,
            "transactions": [svc.tx_view(t) for t in up.transactions[:MAX_LIST]],
            "truncated": len(up.transactions) > MAX_LIST}


@router.get("/{app_id}/transactions")
def list_transactions(app_id: str, user: User = Depends(applicant_user), db: Session = Depends(get_db),
                      limit: int = Query(500, ge=1, le=500)):
    app = svc.get_owned_application(db, user, app_id)
    txs = app.upload.transactions[:limit] if app.upload else []
    return {"transactions": [svc.tx_view(t) for t in txs], "credit_categories": allowed_categories("credit"),
            "debit_categories": allowed_categories("debit")}


@router.patch("/{app_id}/transactions/{tx_id}")
def correct_transaction(app_id: str, tx_id: int, body: CategoryIn, user: User = Depends(applicant_user),
                        db: Session = Depends(get_db)):
    app = svc.get_owned_application(db, user, app_id)
    svc.require_editable(app)
    tx = db.get(Transaction, tx_id)
    if tx is None or app.upload is None or tx.upload_id != app.upload.id:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    if body.category not in allowed_categories(tx.direction):
        raise HTTPException(status_code=422, detail=f"Category '{body.category}' is not allowed for a {tx.direction} transaction.")
    tx.category, tx.category_source, tx.confidence = body.category, "user_correction", "high"
    for a in [a for a in app.assessments if a.is_preview]:
        app.assessments.remove(a)
    app.updated_at = utcnow()
    log_event(db, user, "transaction.category_corrected", "transaction", tx.id, app.id, {"category_to": body.category})
    db.commit()
    return svc.tx_view(tx)


@router.get("/{app_id}/cashflow")
def get_cashflow(app_id: str, user: User = Depends(applicant_user), db: Session = Depends(get_db)):
    app = svc.get_owned_application(db, user, app_id)
    result = svc.cashflow_for(app)
    if result is None:
        raise HTTPException(status_code=404, detail="No transactions have been uploaded for this application.")
    return result


@router.post("/{app_id}/assessments/preview", status_code=201)
def preview_assessment(app_id: str, user: User = Depends(applicant_user), db: Session = Depends(get_db)):
    app = svc.get_owned_application(db, user, app_id)
    svc.require_editable(app)
    try:
        a = svc.run_assessment(db, user, app, is_preview=True)
    except ModelNotAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.commit()
    return svc.assessment_view(a, internal=False)


@router.post("/{app_id}/submit")
def submit(app_id: str, user: User = Depends(applicant_user), db: Session = Depends(get_db)):
    app = svc.get_owned_application(db, user, app_id)
    try:
        svc.submit_application(db, user, app)
    except ModelNotAvailableError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    db.commit()
    return svc.applicant_view(db, app)


@router.post("/{app_id}/info-requests/{request_id}/respond")
def respond_to_info_request(app_id: str, request_id: int, body: RespondIn, user: User = Depends(applicant_user),
                            db: Session = Depends(get_db)):
    app = svc.get_owned_application(db, user, app_id)
    req = db.get(InfoRequest, request_id)
    if req is None or req.application_id != app.id:
        raise HTTPException(status_code=404, detail="Information request not found.")
    if app.status != "info_requested" or req.responded_at is not None:
        raise HTTPException(status_code=409, detail="This request is not waiting for a response.")
    req.response, req.responded_at = body.message.strip(), utcnow()
    log_event(db, user, "info_request.responded", "info_request", req.id, app.id)
    db.commit()
    return svc.applicant_view(db, app)
