# Architecture

Diagrams are written in Mermaid, which GitHub renders automatically.

## 1. System context

```mermaid
flowchart LR
    subgraph Browser
      UI["Next.js pages (React 19)\nAuthProvider keeps the CSRF token in memory"]
    end
    subgraph Vercel
      NEXT["Next.js server\nrewrites /api/* to the backend"]
    end
    subgraph Render
      API["FastAPI (Uvicorn)\nrouters + dependencies"]
      ML["ML layer\nfeatures, calibration, SHAP,\nscenarios, fairness"]
      DB[("PostgreSQL\n(SQLite locally)")]
      REG["Model registry\nversioned .joblib + SHA-256"]
    end
    UI -- "same-origin HTTPS, HttpOnly cookie + X-CSRF-Token" --> NEXT
    NEXT -- "proxied /api/*" --> API
    API --> ML
    API --> DB
    ML --> REG
    REG -. "active version per track" .-> DB
```

Locally there is no proxy: the page on `localhost:3000` calls the API on `localhost:8000` directly (CORS with credentials; both are the same *site*).

## 2. Layers inside the backend (`backend/app`)

| Layer | Modules | Responsibility |
|---|---|---|
| HTTP | `main.py`, `routes_auth.py`, `routes_applications.py`, `routes_reviews.py`, `routes_admin.py` | Validate input (Pydantic), call services, shape responses. No business rules here. |
| Security | `deps.py`, `security.py` | Session lookup, CSRF + Origin checks, role guards, Argon2id hashing. |
| Domain / workflow | `app_service.py`, `workflow.py`, `policy.py`, `audit.py`, `monitoring.py` | State machine, review routing, submission pipeline, demo policy, hash-chained audit. |
| ML | `features.py`, `public_features.py`, `train.py`, `public_train.py`, `calibration.py`, `explain.py`, `scenarios.py`, `fairness.py`, `experiments.py` | Shared feature code, training, calibration, SHAP, what-if/counterfactuals, fairness, experiments. |
| Data input | `ingestion.py`, `categorizer.py`, `cashflow.py` | CSV validation, categories, cash-flow analytics. |
| Persistence | `db.py`, `models.py`, `migrations/` | SQLAlchemy models, engine, Alembic migrations. |
| Operations | `registry.py`, `admin.py`, `model_card.py`, `config.py` | Model versions, CLI (`init`, `bootstrap`, `create-user`), model cards, environment config. |

Rule of thumb: **routes call services; services call ML and the database; ML code never touches HTTP or the database.**

## 3. One submission, end to end

```mermaid
sequenceDiagram
    participant B as Browser
    participant V as Vercel proxy
    participant A as FastAPI
    participant D as Dependencies
    participant S as app_service
    participant R as Registry
    participant M as Model + SHAP
    participant DB as Database
    B->>V: POST /api/v1/applications/{id}/submit (cookie + X-CSRF-Token)
    V->>A: forwarded request
    A->>D: authenticated_user, applicant_user
    D->>DB: find session by SHA-256(token); check expiry, active user
    D-->>A: user (or 401/403); CSRF + Origin verified
    A->>S: submit_application
    S->>R: load_active_bundle (checksum verified)
    S->>DB: draft -> submitted -> validation (audited)
    S->>M: predict_one + explanation (additivity checked)
    S->>DB: Assessment + FeatureSnapshot + Explanation
    S->>DB: assessed -> manual_review, review reasons (audited)
    A-->>B: application view (applicant-safe: no full SHAP table)
```

## 4. Application state machine

```mermaid
stateDiagram-v2
    [*] --> draft
    draft --> submitted: applicant submits
    submitted --> validation
    validation --> draft: validation fails
    validation --> assessed: official assessment stored
    assessed --> manual_review
    manual_review --> info_requested: reviewer asks a question
    info_requested --> submitted: applicant answers and resubmits
    manual_review --> final_demo_decision: reviewer records decision
    final_demo_decision --> [*]
```
Applicants can edit only in `draft` and `info_requested`. They can delete in `draft`, `info_requested` and `final_demo_decision` (not while a reviewer may be working).

## 5. Data model

```mermaid
erDiagram
    users ||--o{ sessions : has
    users ||--o{ consent_records : accepts
    users ||--o{ applications : owns
    applications ||--o| uploads : has
    uploads ||--o{ transactions : contains
    applications ||--o{ assessments : "model output"
    assessments ||--o| feature_snapshots : snapshot
    assessments ||--o| explanations : explained_by
    applications ||--o{ info_requests : receives
    applications ||--o{ review_decisions : "human decision"
    model_versions ||--o{ assessments : scored_by
    users ||--o{ model_versions : activates
    audit_events { int id string action string application_id string prev_hash string event_hash }
```
`audit_events` deliberately has **no foreign keys**: the audit record must survive deleting an application or user.

## 6. ML pipeline (training time)

```mermaid
flowchart TD
    A["Raw data\n(synthetic generator or UCI file)"] --> B["Shared feature functions\nvalidate, no silent clipping"]
    B --> C["Stratified split\n55% train / 15% calibration / 15% validation / 15% test"]
    C --> D["Fit pipelines on TRAIN only\nLR, Random Forest, Hist Gradient Boosting"]
    D --> E["Fit calibrators on CALIBRATION\nnone, sigmoid, isotonic"]
    E --> F["Score 9 combinations on VALIDATION\nchoose lowest Brier score"]
    F --> G["Evaluate ONCE on TEST\nmetrics, baseline, calibration curve"]
    F --> H["SHAP assets\nbackground rows + global importance"]
    G --> I["Artifact (.joblib) + evaluation.json + model card"]
    H --> I
    I --> J["Registry: SHA-256, version, activate"]
```

## 7. Design decisions in one line each
- **One feature function** for training, serving and scenarios, so train/serve skew cannot exist.
- **Model, policy, human** are three separate things: model output (`assessments`), rules (`policy.py`), decision (`review_decisions`).
- **Unknown is never zero**: missing credit history and undefined ratios are `null`/`NaN` with explicit indicators.
- **Server-side authorization for everything**; UI guards are convenience only.
- **Sessions in the database, not JWTs**: revocable, role changes take effect immediately.
- **Tamper-evident audit**: each event hashes the previous one.
