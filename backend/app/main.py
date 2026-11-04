"""FastAPI app. Run from backend/:  uvicorn app.main:app --reload

Stage 1 exposes health, model metadata and prediction. /predict is kept for
compatibility with the first prototype's frontend; /api/v1/assessments/predict
is the versioned route (same behaviour). Authentication arrives in a later stage,
so do NOT expose this server publicly.
"""
from __future__ import annotations

import json
import logging

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import config
from .categorizer import ALL_CATEGORIES, assign_categories
from .cashflow import analyze
from .ingestion import UploadError, parse_csv
from .features import InvalidInputError, LIMITS
from .predict import ModelNotAvailableError, load_bundle, predict_one

logger = logging.getLogger("creditlens")  # never log raw financial inputs

app = FastAPI(title="CreditLens XAI API", version="0.1.0",
              description="Educational credit-risk decision-support prototype. Not a lender, "
                          "not a credit score, not a loan approval.")
app.add_middleware(CORSMiddleware, allow_origins=config.cors_origins(),
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


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


def _bundle():
    try:
        return load_bundle()
    except ModelNotAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/models/active")
def active_model():
    meta = _bundle().metadata
    return {k: meta[k] for k in ("model_version", "model_name", "calibration_method",
                                 "calibration_evaluated", "data_provenance", "target_definition",
                                 "selection_criterion", "limitations", "trained_at_utc")}


def _score(application: LoanApplication) -> dict:
    bundle = _bundle()
    try:
        result = predict_one(bundle, application.model_dump())
    except InvalidInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    logger.info("prediction served model_version=%s", result["model_version"])
    return result


@app.post("/predict")
def predict_compat(application: LoanApplication):
    return _score(application)


@app.post("/api/v1/assessments/predict")
def predict_v1(application: LoanApplication):
    return _score(application)


# ---------------------------------------------------------------------------
# Stage 2: CSV upload + cash-flow analytics (stateless; no auth or DB yet, so
# upload ownership checks arrive with authentication in Stage 5).
# ---------------------------------------------------------------------------
PREVIEW_ROWS = 200


def _json_field(raw: str | None, name: str) -> dict | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"'{name}' must be valid JSON") from exc
    if not isinstance(value, dict):
        raise HTTPException(status_code=422, detail=f"'{name}' must be a JSON object")
    return value


async def _read_and_parse(file: UploadFile, mapping: str | None):
    data = await file.read(config.max_upload_bytes() + 1)
    try:
        return parse_csv(data, file.filename, _json_field(mapping, "mapping"))
    except UploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


def _rows(tx) -> list[dict]:
    return [{"key": r.key, "row": int(r.row), "date": r.date.date().isoformat(),
             "description": r.description, "amount": float(r.amount), "direction": r.direction,
             "category": r.category, "category_source": r.category_source,
             "confidence": r.confidence} for r in tx.itertuples()]


@app.get("/api/v1/transactions/categories")
def categories():
    return {"categories": ALL_CATEGORIES}


@app.post("/api/v1/uploads/preview")
async def upload_preview(file: UploadFile = File(...), mapping: str | None = Form(None),
                         corrections: str | None = Form(None)):
    parsed = await _read_and_parse(file, mapping)
    tx, cat_report = assign_categories(parsed.transactions, _json_field(corrections, "corrections"))
    logger.info("upload previewed rows_valid=%s rows_total=%s", parsed.stats["rows_valid"],
                parsed.stats["rows_total"])
    return {"stats": parsed.stats, "detected_mapping": parsed.mapping, "date_format": parsed.date_format,
            "issues": parsed.issues, "category_issues": cat_report,
            "transactions": _rows(tx.head(PREVIEW_ROWS)), "truncated": len(tx) > PREVIEW_ROWS,
            "note": "Rule-based categories are guesses (see category_source / confidence). Correct them "
                    "by resubmitting with a 'corrections' JSON object {key: category}."}


@app.post("/api/v1/cashflow/analyze")
async def cashflow_analyze(file: UploadFile = File(...), mapping: str | None = Form(None),
                           corrections: str | None = Form(None)):
    parsed = await _read_and_parse(file, mapping)
    tx, cat_report = assign_categories(parsed.transactions, _json_field(corrections, "corrections"))
    result = analyze(tx)
    logger.info("cashflow analyzed rows_valid=%s", parsed.stats["rows_valid"])
    return {"stats": parsed.stats, "issues": parsed.issues, "category_issues": cat_report, **result}
