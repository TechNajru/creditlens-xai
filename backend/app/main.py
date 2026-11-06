"""FastAPI app. Run from backend/:  uvicorn app.main:app --reload

Stage 1 exposes health, model metadata and prediction. /predict is kept for
compatibility with the first prototype's frontend; /api/v1/assessments/predict
is the versioned route (same behaviour). Authentication arrives in a later stage,
so do NOT expose this server publicly.
"""
from __future__ import annotations

import json
import logging
from typing import Literal

import joblib
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import config
from .categorizer import ALL_CATEGORIES, CREDIT_CATEGORIES, DEBIT_CATEGORIES, assign_categories
from .cashflow import analyze
from .ingestion import UploadError, parse_csv
from .features import InvalidInputError, LIMITS
from .policy import DemoPolicy
from .predict import ModelNotAvailableError, load_bundle, predict_one
from .scenarios import ScenarioError, counterfactuals, what_if
from .public_features import InvalidPublicInputError
from .public_predict import load_public_bundle, predict_public

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


Detail = Literal["summary", "full"]


def _score(application: LoanApplication, detail: str = "summary") -> dict:
    bundle = _bundle()
    try:
        result = predict_one(bundle, application.model_dump(), detail)
    except InvalidInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    logger.info("prediction served model_version=%s", result["model_version"])
    return result


@app.post("/predict")
def predict_compat(application: LoanApplication, detail: Detail = Query("summary")):
    return _score(application, detail)


@app.post("/api/v1/assessments/predict")
def predict_v1(application: LoanApplication, detail: Detail = Query("summary")):
    return _score(application, detail)


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
    return {"categories": ALL_CATEGORIES, "credit": CREDIT_CATEGORIES, "debit": DEBIT_CATEGORIES}


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


# ---------------------------------------------------------------------------
# Stage 2B: PUBLIC-DATA model (UCI Default of Credit Card Clients). Separate from the
# loan-application simulation model above; the two are never mixed.
# ---------------------------------------------------------------------------
class PublicClient(BaseModel):
    LIMIT_BAL: float = Field(gt=0, le=10_000_000, description="Credit limit, NT dollars")
    AGE: int = Field(ge=18, le=100)
    PAY_0: int = Field(ge=-2, le=9); PAY_2: int = Field(ge=-2, le=9); PAY_3: int = Field(ge=-2, le=9)
    PAY_4: int = Field(ge=-2, le=9); PAY_5: int = Field(ge=-2, le=9); PAY_6: int = Field(ge=-2, le=9)
    BILL_AMT1: float; BILL_AMT2: float; BILL_AMT3: float
    BILL_AMT4: float; BILL_AMT5: float; BILL_AMT6: float
    PAY_AMT1: float = Field(ge=0); PAY_AMT2: float = Field(ge=0); PAY_AMT3: float = Field(ge=0)
    PAY_AMT4: float = Field(ge=0); PAY_AMT5: float = Field(ge=0); PAY_AMT6: float = Field(ge=0)


def _public_bundle():
    try:
        return load_public_bundle()
    except ModelNotAvailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/v1/models/public/active")
def public_model_info():
    meta = _public_bundle().metadata
    return {k: meta[k] for k in ("model_version", "model_name", "calibration_method", "calibration_evaluated",
                                 "data_provenance", "dataset", "target_definition", "selection_criterion",
                                 "excluded_from_model_inputs", "limitations", "trained_at_utc")}


@app.post("/api/v1/assessments/predict-public")
def predict_public_route(client: PublicClient, detail: Detail = Query("summary")):
    bundle = _public_bundle()
    try:
        result = predict_public(bundle, client.model_dump(), detail)
    except InvalidPublicInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    logger.info("public prediction served model_version=%s", result["model_version"])
    return result


# ---------------------------------------------------------------------------
# Stage 3: evaluation reports for the dashboard
# ---------------------------------------------------------------------------
_TRACKS = {"simulation": ("evaluation.json", config.ARTIFACT_NAME),
           "public": ("evaluation_public.json", config.PUBLIC_ARTIFACT_NAME)}


@app.get("/api/v1/models/{track}/evaluation")
def model_evaluation(track: Literal["simulation", "public"]):
    report_name, artifact_name = _TRACKS[track]
    path = config.reports_dir() / report_name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No evaluation report for '{track}'. Train the model first.")
    report = json.loads(path.read_text())
    meta_path = config.models_dir() / artifact_name
    limitations = []
    if meta_path.exists():
        limitations = joblib.load(meta_path)["metadata"].get("limitations", [])
    return {"track": track, "report": report, "limitations": limitations}


# ---------------------------------------------------------------------------
# Stage 4: what-if simulator and constrained counterfactuals (loan simulation model)
# ---------------------------------------------------------------------------
class PolicyOverride(BaseModel):
    max_default_probability: float | None = Field(default=None, gt=0, le=1)
    max_total_emi_to_income: float | None = Field(default=None, gt=0, le=5)


class ScenarioInput(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    changes: dict[str, float | int] = Field(
        description="Only loan_amount, tenure_months, annual_interest_rate and (hypothetical) existing_emi may change.")


class WhatIfRequest(BaseModel):
    application: LoanApplication
    scenarios: list[ScenarioInput] = Field(min_length=1, max_length=5)
    policy: PolicyOverride | None = None


class CounterfactualRequest(BaseModel):
    application: LoanApplication
    policy: PolicyOverride | None = None
    allow_hypothetical_debt_reduction: bool = False
    max_results: int = Field(default=3, ge=1, le=5)


def _policy(override: PolicyOverride | None) -> DemoPolicy:
    values = override.model_dump(exclude_none=True) if override else {}
    return DemoPolicy(**values)


@app.post("/api/v1/scenarios/what-if")
def scenarios_what_if(req: WhatIfRequest):
    bundle = _bundle()
    try:
        result = what_if(bundle, req.application.model_dump(),
                         [s.model_dump() for s in req.scenarios], _policy(req.policy))
    except (ScenarioError, InvalidInputError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    logger.info("what-if evaluated scenarios=%s", len(req.scenarios))
    return result


@app.post("/api/v1/scenarios/counterfactuals")
def scenarios_counterfactuals(req: CounterfactualRequest):
    bundle = _bundle()
    try:
        result = counterfactuals(bundle, req.application.model_dump(), _policy(req.policy),
                                 req.allow_hypothetical_debt_reduction, req.max_results)
    except (ScenarioError, InvalidInputError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    logger.info("counterfactual search status=%s", result["status"])
    return result


# ---------------------------------------------------------------------------
# Stage 4: fairness audit + limited-information experiments (read generated reports)
# NOTE: the fairness report uses sensitive attributes for AUDIT ONLY. Access control arrives with
# authentication (Stage 5); until then do not expose this API publicly.
# ---------------------------------------------------------------------------
def _read_report(name: str, hint: str) -> dict:
    path = config.reports_dir() / name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Report not found. Run: {hint}")
    return json.loads(path.read_text())


@app.get("/api/v1/fairness/public")
def fairness_public():
    return _read_report("fairness_public.json", "python -m app.fairness")


@app.get("/api/v1/models/public/experiments")
def public_experiments():
    return _read_report("experiments_public.json", "python -m app.experiments")
