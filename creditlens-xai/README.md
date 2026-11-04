# CreditLens XAI

An **educational** credit-risk decision-support prototype: shared feature engineering, calibrated
risk modelling, evaluation reports and an API — with explainability, fairness, counterfactuals,
cash-flow analysis and reviewer workflows planned in later stages.

**Honest scope:** not a bank, not a lender, not a credit score, not a loan approval. Stage 1 models
are trained on **synthetic** data, so their metrics say nothing about real borrowers.

## Status
| Stage | Content | State |
|---|---|---|
| 1 | Shared features, simulation model, calibration, evaluation, FastAPI `/predict` | Implemented, backend tests pass (30) |
| 2A | CSV upload, validation, categories + corrections, cash-flow analytics (Track B) | Implemented, 69 backend tests pass in total |
| 2B | Real public dataset (UCI, Track A), separate public-data model, calibration + evaluation | Implemented, 93 backend tests pass |
| 3 | SHAP explanations, model card, result UI | Not started |
| 4 | Counterfactuals, fairness audit | Not started |
| 5 | Auth, database, reviewer workflow, audit trail | Not started |
| 6 | E2E test, security review, docs, deploy | Not started |

## Setup (Windows PowerShell) — run from the `backend` folder
```powershell
cd creditlens-xai\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest -q          # run tests
python -m app.train          # train + write models/ and reports/
uvicorn app.main:app --reload  # API at http://127.0.0.1:8000/docs
```
If activation is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## Example request
```powershell
$body = '{"monthly_income":50000,"loan_amount":300000,"tenure_months":36,"annual_interest_rate":12,"existing_emi":5000,"age":32,"employment_years":5,"num_existing_loans":1,"credit_history_months":null}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/predict -ContentType "application/json" -Body $body
```

## Stage 2 endpoints (no auth yet — do not expose publicly)
- `POST /api/v1/uploads/preview` — multipart `file` (+ optional `mapping`, `corrections` JSON) -> parsed rows, issues, categories
- `POST /api/v1/cashflow/analyze` — same inputs -> coverage, monthly table, metrics, recurring income, missingness
- `GET /api/v1/transactions/categories`
Samples are in `sample_data/` (all synthetic). Method: `docs/cashflow_methodology.md`.

## Public-data model (Track A) — dataset not committed
1. Download the UCI file (CC BY 4.0): https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients
2. Put `default of credit card clients.xls` in `backend\data\` (gitignored).
3. `python -m app.public_train` (from `backend`), then `POST /api/v1/assessments/predict-public`.
Details: `docs/dataset_provenance.md`, `docs/public_data_dictionary.md`, `docs/public_model_evaluation.md`.
Without the file, the rest of the test suite still runs (one real-file test is skipped).

## Data attribution
Public-data model uses *Default of Credit Card Clients* by I-Cheng Yeh (2009), UCI Machine Learning Repository,
CC BY 4.0 — https://doi.org/10.24432/C55S3H

## Key design points
- One feature function (`app/features.py`) is used by training and inference (fixes the old EMI-ratio mismatch).
- Four splits: train / calibration / validation / untouched test. Model and calibrator are chosen on validation Brier score; test is evaluated once.
- Unknown credit history is represented explicitly, never as zero.
- The API returns `explanation: unavailable` until real SHAP is implemented — no fake explanations.
- Model files are pickles: only load artifacts you trained yourself.

## Not implemented yet / known limits
No authentication (do not expose publicly), no database, no real-data model, no explanations,
no fairness analysis, no frontend in this repo snapshot, CI workflow not yet run on GitHub.
See `docs/` for the data dictionary and dataset provenance.
