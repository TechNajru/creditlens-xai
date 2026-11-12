# CreditLens XAI: the complete project guide

*Written for the person who built it, so you can explain every part in an interview. Read it once end to end, then use `INTERVIEW_QA.md` to practise.*

Contents: 1 Pitch · 2 The problem and the business · 3 What makes it distinctive · 4 Project structure · 5 Tech stack and why · 6 Concepts: data and machine learning · 7 Concepts: backend, security, database · 8 Concepts: frontend, testing, delivery · 9 Business view and use cases · 10 Future improvements · 11 Glossary

---

## 1. Pitch

**One sentence.** CreditLens XAI is an educational credit-risk decision-support platform that scores loan applications with a *calibrated* model, *explains* every score, checks *fairness*, lets a *human reviewer* make the final call, and keeps a *tamper-evident audit trail*.

**Thirty seconds.** "Most student credit projects stop at a model with a high accuracy number. In real lending a score alone is useless: the probability must be trustworthy (calibrated), the applicant and the regulator need reasons (explainability), the system must not treat groups unfairly (fairness), a person must be accountable for the decision (human review), and everything must be reproducible and auditable. I built that whole chain end to end: FastAPI backend, Next.js frontend, PostgreSQL, 296 automated tests, with a documented and tested deployment path to Vercel and Render. [Update this sentence with your live URL only after you have really deployed it.] And it is honest about its limits: the loan model uses synthetic data and nothing in it is a real lending decision."

**What it is not** (say this proactively; it earns trust): not a bank, not a lender, not a credit-bureau score, no real approval, not validated on real borrowers, and the UCI public-data model reflects 2005 Taiwan credit-card clients only.

## 2. The problem and the business

### 2.1 Credit-risk basics (what you must be able to explain)
- **Credit risk**: the chance a borrower does not repay. Lenders estimate it before lending.
- **Probability of default (PD)**: the model's output, a number between 0 and 1. Meaningful only with a stated **horizon** ("default within 12 months") and **default definition**.
- **Thin-file applicant**: someone with little or no credit history. Bureau scores cannot rate them, so lenders either reject them (financial exclusion) or guess. Alternative data (bank cash-flow, UPI payments) is one proposed answer, which is why this project includes a cash-flow engine.
- **EMI** (equated monthly instalment): fixed monthly repayment. **EMI-to-income** ratio is a classic affordability measure.
- **Decision-support vs decision-making**: here the software *supports* a human; it never approves or denies anyone.

### 2.2 Why lenders need more than a score
| Need | Why it matters | How the project addresses it |
|---|---|---|
| Trustworthy probabilities | Pricing, provisioning and limits use the probability itself, not just the ranking | **Calibration** compared before use; reliability curve; calibration error reported |
| Explanations | Applicants and regulators expect reasons; reviewers need to challenge the model | **SHAP** contributions + plain-language reason codes, additivity-checked |
| Fairness | Biased outcomes harm people and create legal and reputational risk | **Fairlearn audit** with confidence intervals, small-group warnings, a mitigation experiment |
| Human accountability | A model should not be the last word | **Reviewer workflow**; overrides need a written reason |
| Auditability | "Who decided what, using which model version?" must be answerable later | **Versioned artifacts**, stored input snapshots, **hash-chained audit trail** |
| Data minimisation and consent | Financial data is sensitive | Consent notice, pseudonymous reviewer view, deletion, audit without raw content |

Regulatory context, stated carefully: in many jurisdictions lenders must be able to explain adverse decisions and avoid discrimination, and regulators increasingly look at automated decisions (examples include adverse-action rules in the US, automated-decision provisions in the EU's data-protection law, and digital-lending guidelines issued by India's RBI). Do not claim this project satisfies any of them; say it *demonstrates the engineering building blocks* those expectations imply.

### 2.3 Business value (honest version)
A real lender or fintech would care about: lower credit losses at the same approval rate, more approvals at the same loss rate (inclusion of thin-file customers), faster review (reviewers see quality flags and explanations up front), lower compliance cost (explanations and audit are built in, not bolted on), and safer model operations (versioning, monitoring, controlled activation). This project shows how those capabilities fit together; it does not measure the business outcome, because that needs real outcome data.

## 3. What makes it distinctive

State these as *engineering and responsibility* strengths, never as "first of its kind":
1. **One feature function** for training, serving and scenarios. The original prototype computed EMI-to-income differently in training and prediction (a classic train/serve skew bug); the redesign removes the class of bug and has a parity test.
2. **Calibration is a first-class deliverable**, not an afterthought: nine model x calibrator combinations are compared on a validation split and the choice is documented.
3. **Explanations that are verified**: SHAP values must add up to the model score (tolerance 1e-6) or the explanation is withheld. It never fabricates an explanation.
4. **Two separated data tracks**: public labelled data (real default labels, UCI) and a synthetic simulation. The project refuses to attach synthetic transaction features to real labels and claim improvement.
5. **Unknown is never zero**: missing credit history, undefined payment ratios and gap months are explicit unknowns.
6. **Policy, model, human are separate** things stored in separate records, so you can always answer "what did the model say, what did the rules say, and what did the person decide, and why?"
7. **Fairness with uncertainty**: intervals and small-group flags, a mitigation that is analysed but deliberately **not deployed**, and a clear statement of what the audit cannot show.
8. **Constrained counterfactuals**: alternatives only change controllable terms (amount, tenure); income, age and history can never change; debt reduction is labelled hypothetical; "no feasible alternative" is a valid answer.
9. **Tamper-evident audit** and a **model registry** with checksums.
10. **Quality evidence**: 296 tests including black-box sweeps of every route, database tests on PostgreSQL as well as SQLite, a real-browser end-to-end run, and documented security review.
11. **Honesty as a feature**: limitations are written into the product (UI banners, model cards, docs), not hidden.

## 4. Project structure

```
creditlens-xai/
├── README.md                  entry point: what it is, screenshots, quick start
├── LICENSE  SECURITY.md       MIT licence; how to report vulnerabilities
├── render.yaml                Render Blueprint (API + PostgreSQL)
├── .python-version            3.12 (the version everything was tested on)
├── .github/
│   ├── workflows/ci.yml       CI: backend tests, Postgres tests, security scans, frontend checks
│   └── dependabot.yml         weekly dependency update PRs
├── sample_data/               FICTIONAL transaction CSVs (4 personas + a deliberately messy file)
├── e2e/browser_flow.py        optional Playwright test of the whole journey
├── docs/                      this guide, architecture, deployment, security, model cards, methodology
├── backend/
│   ├── requirements.txt       exact pinned versions
│   ├── alembic.ini  migrations/   database migrations (0001 = initial schema)
│   ├── check_setup.py         "is my checkout complete?" helper
│   ├── app/
│   │   ├── main.py                 FastAPI app, CORS, security headers, earlier-stage endpoints
│   │   ├── routes_auth.py          register / login / logout / me / consent notice
│   │   ├── routes_applications.py  applicant workflow (draft, upload, correct, preview, submit, delete)
│   │   ├── routes_reviews.py       reviewer queue, detail, request info, decision
│   │   ├── routes_admin.py         users, model versions, monitoring, audit
│   │   ├── deps.py                 session lookup, CSRF + Origin checks, role guards
│   │   ├── security.py             Argon2id hashing, password policy, token helpers
│   │   ├── models.py  db.py        SQLAlchemy tables (13) and engine/session
│   │   ├── app_service.py          business logic: assessments, review routing, submission pipeline
│   │   ├── workflow.py             the state machine (every status change goes through it)
│   │   ├── audit.py                hash-chained, append-only audit events
│   │   ├── registry.py             model versions: copy, SHA-256, activate, integrity-checked load
│   │   ├── policy.py               transparent demonstration rules (separate from the model)
│   │   ├── monitoring.py           admin monitoring summary
│   │   ├── features.py             SHARED feature engineering for the loan model (EMI etc.)
│   │   ├── synthetic.py            synthetic applicant generator (Track B)
│   │   ├── train.py  calibration.py   train + calibrate + select + evaluate the loan model
│   │   ├── public_data.py  public_features.py  public_train.py  public_predict.py   the UCI model (Track A)
│   │   ├── explain.py  reason_codes.py   SHAP explanations and plain-language labels
│   │   ├── scenarios.py            what-if simulator and constrained counterfactual search
│   │   ├── fairness.py  experiments.py   Fairlearn audit; limited-information experiments
│   │   ├── ingestion.py  categorizer.py  cashflow.py   CSV validation, categories, cash-flow analytics
│   │   ├── model_card.py           generates model cards from artifacts (no hand-typed numbers)
│   │   ├── admin.py                CLI: init, bootstrap, create-user, status
│   │   └── config.py  schemas.py  notice.py   environment config, shared schemas, consent text
│   └── tests/                 16 test modules + helpers, 210 tests (pytest)
└── frontend/
    ├── next.config.ts         security headers and the /api proxy (Vercel -> Render)
    └── src/
        ├── app/               pages (App Router): / login register dashboard applications/[id] review admin assess scenarios cashflow models fairness
        ├── components/        24 components (AuthProvider, RequireAuth, ApplicationWorkflow, ReviewDetail, AdminConsole, charts ...)
        ├── lib/               api.ts (fetch client + CSRF), types.ts, fields.ts (validation), format.ts
        └── __tests__/         86 tests (Vitest + Testing Library)
```

## 5. Tech stack and why

| Layer | Choice | Why this | Alternatives and the trade-off |
|---|---|---|---|
| Language (ML + API) | **Python 3.12** | The ML ecosystem lives here; one language for training and serving avoids translation bugs | Java/Go serve faster but would need model export and duplicate the feature code |
| API framework | **FastAPI** | Typed request models (Pydantic) give validation and automatic OpenAPI docs; async-capable; very little boilerplate | Django REST: more batteries (admin, ORM) but heavier; Flask: minimal but you assemble validation yourself |
| Validation | **Pydantic v2** | Declarative constraints (`Field(ge=..., le=...)`) at the edge; errors become clean 422 responses | Hand-written checks: easy to forget a field |
| ML | **scikit-learn** (+ HistGradientBoosting) | Reliable, consistent API (`Pipeline`, `ColumnTransformer`), good baselines; fits "start simple, compare" | XGBoost/LightGBM (optional candidates, not needed to win here); deep learning is overkill for ~14-23 tabular features |
| Explainability | **SHAP** (PermutationExplainer) | Model-agnostic, so it works whichever model wins; additive by construction | LIME: less stable; TreeSHAP: faster but only for supported tree models |
| Fairness | **Fairlearn** | Standard metrics (`MetricFrame`, demographic parity, equalized odds) and a post-processing mitigation | AIF360: broader but heavier; hand-rolled metrics (I cross-check mine against Fairlearn in tests) |
| Data | **pandas, NumPy, SciPy** | Tabular manipulation standard | Polars is faster but less familiar to reviewers |
| Database | **SQLite (local) / PostgreSQL (deploy)** | SQLite needs zero setup for a student machine; Postgres is what real systems use. Same code runs on both (tested on both) | MongoDB: flexible but this data is relational and needs constraints and transactions |
| ORM + migrations | **SQLAlchemy 2 + Alembic** | Parameterised queries (no SQL injection), explicit schema history, portable across databases | Raw SQL: fast but easy to get wrong; Django ORM: tied to Django |
| Passwords | **Argon2id** (argon2-cffi) | Memory-hard, current recommendation for password hashing | bcrypt: fine and widespread; plain SHA-256: **never** (too fast to brute-force) |
| Sessions | **Server-side sessions + HttpOnly cookie + CSRF token** | Revocable instantly (logout, role change, deactivation); the token is not readable by JavaScript | JWT in localStorage: stateless but unrevocable and readable by any XSS |
| Frontend | **Next.js 16 (App Router), React 19, TypeScript** | File-based routing, built-in proxy rewrites and headers, first-class Vercel deployment; TypeScript catches shape mismatches with the API | Plain React + Vite: simpler but you add routing and a server yourself |
| Styling | **Tailwind CSS 4** | Fast, consistent, accessible utility classes; no custom CSS sprawl | Component libraries (MUI): quicker visuals, heavier and harder to make distinctive |
| Charts | **Recharts** | Declarative React charts, adequate for reliability curves and bars | D3: more control, much more code |
| Testing | **pytest** (backend), **Vitest + Testing Library** (frontend), Playwright (optional e2e) | Fast, readable tests; Testing Library tests behaviour users see, not implementation details | Jest: equivalent for the frontend; Cypress: heavier e2e |
| Static analysis | **Bandit, pip-audit, npm audit, ESLint, tsc** | Catch insecure patterns and known-vulnerable packages before release | Snyk/SonarQube: more features, more setup |
| CI | **GitHub Actions** | Free for public repos, lives next to the code | Jenkins/GitLab CI: more control, more upkeep |
| Hosting | **Vercel (site) + Render (API + Postgres)** | Free tiers, GitHub-driven deploys, matches the stack; the Vercel proxy keeps cookies first-party | AWS/GCP: powerful but far more to configure; Kubernetes: unnecessary for this scale |

Why *not* the heavy things: no microservices, Kafka or Kubernetes. One deployable API plus one website is the right size for a six-week student project, and it is easier to explain and test. Say so; it shows judgement.

---

## 6. Concepts: data and machine learning

Each concept: **what it is**, **how this project does it** (with the file), and **the trap it avoids**.

### 6.1 Two data tracks
- **Track A, public labelled data** (`public_data.py`): the UCI *Default of Credit Card Clients* dataset (Yeh, 2009; CC BY 4.0). 30,000 Taiwanese credit-card clients, April-September 2005, 6 months of repayment history, label = default in the next month (22.12% defaulted). It is **credit-card** data, not loan data, so it trains a *separate* model with its own feature schema.
- **Track B, synthetic simulation** (`synthetic.py`): fictional loan applicants whose outcome comes from a hand-written logistic-style rule plus noise. Used to exercise the whole product (EMI features, workflow, reviewers) without pretending anything about real borrowers.
- **Trap avoided:** randomly attaching synthetic UPI features to real labelled borrowers and claiming "predictive improvement". Rule: never feed a model features it was not trained and validated with; never merge unrelated datasets by row order.
- **Honest consequence:** on synthetic data Logistic Regression wins *because the generating rule is logistic*. That is an artefact, not a finding about models.

### 6.2 Feature engineering and train/serve skew
- **EMI formula** (`features.py: calculate_emi`): `EMI = P * r * (1+r)^n / ((1+r)^n - 1)` with `r = annual_rate / 12 / 100`, `P` the principal and `n` the months. Zero interest is the special case `P / n`. Invalid tenure, negative principal or negative rate raise errors; division by zero is impossible because income must be positive.
- **Loan-model features (14):** nine raw inputs, `credit_history_missing`, and four derived values (`new_loan_emi`, `total_emi`, `total_emi_to_income`, `loan_to_annual_income`). **Public model (23):** 20 raw plus `utilization_latest`, `months_delayed`, `payment_ratio_latest`.
- **Skew:** the first prototype computed EMI-to-income as `new_emi / income` in training but `(new_emi + existing_emi) / income` at prediction, so the model was served inputs it never saw. Fix: **one function** is used by training, evaluation, the API and scenarios, plus a test proving batch and single-row paths give identical features.
- **No silent clipping:** out-of-range inputs are rejected with an error, never quietly altered. (The public data has negative bills and an extreme payment ratio of about 11,454; both are kept as recorded and documented.)
- **Unknown is not zero:** an unknown credit-history length stays `NaN` with an explicit `credit_history_missing` flag. A `payment_ratio_latest` is `NaN` (not 0) when the latest bill is not positive. Zero history and unknown history mean different things.

### 6.3 Leakage and splitting
- **Data leakage** = information from outside the training situation sneaking into the model (the label, the future, the test set), giving fake accuracy.
- **Four stratified splits** (`train.py`, `public_train.py`): 55% **train** (fit models), 15% **calibration** (fit calibrators), 15% **validation** (choose model + calibrator), 15% **test** (touched once, at the end). Separate calibration data matters: a calibrator fitted on the same data used to evaluate it would flatter itself.
- **Preprocessing lives inside the sklearn `Pipeline`**, so imputers and scalers are fitted on training rows only.
- **Guards:** training raises an explicit error if the target or a sensitive column is in the features (this used to be an `assert`, which disappears under `python -O`; the security review fixed it).
- **Limits you must state:** the UCI file is one snapshot, so only random stratified splits are possible (no time-based validation); 35 rows are identical apart from ID and are kept (distinct clients).

### 6.4 Models and baselines
- Candidates: **Logistic Regression** (impute + scale), **Random Forest**, **HistGradientBoosting**. Start simple and compare; do not pick the fanciest by default.
- **Baseline:** a constant predictor that always outputs the training default rate (Brier 0.172 on UCI). Any model must beat it.
- **Imbalance (22% positives):** we do **not** use `class_weight`, because re-weighting distorts predicted probabilities and we need real probabilities. Calibration then handles any residual mismatch.
- **Selection rule (documented):** lowest **validation Brier score** across 3 models x 3 calibration options. On UCI, HistGradientBoosting + sigmoid won (0.1313), but Random Forest + sigmoid was 0.1318, a practical tie; do not call it a clear win.

### 6.5 Metrics (and why not accuracy)
| Metric | Meaning | UCI test result | Note |
|---|---|---|---|
| ROC-AUC | Probability a random defaulter is scored above a random non-defaulter (ranking quality) | 0.782 | Unaffected by monotone recalibration |
| Average precision | Area under the precision-recall curve | 0.563 | A random ranker scores the prevalence, 0.221 |
| **Brier score** | Mean squared error of the probabilities (lower is better) | 0.134 vs 0.172 baseline | Rewards calibration *and* ranking; our selection metric |
| Log loss | Penalises confident wrong predictions heavily | 0.427 vs 0.528 baseline | |
| Precision / recall / F1 / confusion matrix | Depend on a **threshold** | at 0.2: 0.42 / 0.66; at 0.3: 0.54 / 0.54; at 0.5: 0.69 / 0.35 | Thresholds are **experimental**, not policy |
- **Accuracy is misleading:** always predicting "no default" is 78% accurate on this data and useless.
- **Threshold trade-off:** flagging more clients raises recall (catch more defaulters) and lowers precision (more false alarms).
- **Other models on UCI test** (for comparison only, not used for selection): Random Forest AUC 0.781, Logistic Regression 0.742 (hurt by extreme `payment_ratio_latest` values and by treating PAY codes as plain numbers).

### 6.6 Probability calibration
- **Calibrated** means "of the clients given 30%, about 30% default". Good ranking (high AUC) does **not** guarantee this.
- **Methods** (`calibration.py`): **sigmoid / Platt scaling** (fit a logistic regression on the model's log-odds; few parameters, works with little data) and **isotonic** (a monotone step function; flexible but needs more data and can create ties). We also keep "none" as a candidate.
- **Evidence:** reliability curve on the test split follows the diagonal (for example predicted 0.704 vs observed 0.702 in the top bin). Calibration error (ECE) is reported in the experiments (0.0066 for the full-history model).
- **What the number is and is not:** the displayed value is the calibrated probability of the *dataset's own default definition*. It is **not** `1 - P(default)` as an approval probability, and not a credit score. The UI and API say so.
- **Caveat:** calibration was measured on a random hold-out from the same 2005 snapshot; it says nothing about other periods.

### 6.7 Explainability with SHAP
- **Idea** (Shapley values from game theory): share the difference between the model's output for this person and the average output among all the features, fairly, by averaging each feature's marginal contribution over many orderings.
- **Implementation** (`explain.py`): `shap.PermutationExplainer` over the **whole fitted pipeline** (so imputers and scalers are included), with 100 stored training rows as the "background". Fixed seed, so repeatable.
- **What is explained:** the model's **uncalibrated raw score**. `baseline + sum(contributions) = raw score`, verified to 1e-6 on every request. If it fails, or the explainer errors, the API returns `status: "unavailable"` and the prediction still works. Nothing is invented.
- **Not percentage points:** the shown probability is a monotone recalibration of the raw score, so contributions are not percentage-point changes to it. The UI says so.
- **Local vs global:** local = why *this* person got this score; global = mean absolute contribution over a sample of validation rows. On the synthetic model `total_emi_to_income` dominates, matching the rule that generated the labels (a sanity check). On UCI the top drivers are `months_delayed`, `PAY_0` and `utilization_latest`.
- **Reason codes** (`reason_codes.py`): top factors in plain language, with values ("Total EMI as a share of monthly income: 140%, raised the model's risk score"). Unknown values read "unknown (not treated as zero)".
- **Known caveat: correlated features.** EMI, total EMI, EMI-to-income and loan-to-income overlap, so credit is shared and a feature that *looks* risky can show a small negative contribution while a related ratio carries the large positive one. Read related features as a group.
- **Not causal:** SHAP describes how the *model* uses inputs, not what would happen in the world if an input changed.
- **Applicant vs reviewer views:** applicants get reason codes and top factors; reviewers also get the full table, chart and method/version.

### 6.8 Cash-flow analytics (`ingestion.py`, `categorizer.py`, `cashflow.py`)
- **Ingestion:** CSV only, 2 MB and 5,000-row limits, header auto-detection (Narration, Withdrawal, Deposit...), separate debit/credit columns, `Cr`/`Dr` suffixes, currency symbols, single date format chosen by majority (day-first). Invalid rows are reported by **row number and reason only** (never raw text); duplicates (same transaction id, or identical content) are excluded and reported.
- **Categories carry provenance:** each transaction has a category, a **source** (supplied, rule, default, or your correction) and a **confidence**. Keyword rules are guesses and labelled so; corrections win over everything.
- **Income tiers, never merged:** *confirmed* (supplied or corrected as income), *likely* (keyword-guessed salary), *unverified* (UPI inflows and uncategorised credits). UPI inflow is **never** "verified income". Internal transfers are excluded from income and spending.
- **Interior months only:** the first and last calendar month of a statement may be partial, so metrics use months strictly between them that contain data. At least 3 usable months are required; gap months are reported as unknown, not zero.
- **Unknown vs zero:** `observed_monthly_debt_payments = 0` means none were *observed*, not "no debt". Debt-to-income is undefined (null) when income is 0. Payment timeliness is computed only when both a due date and a payment date are supplied; it is never inferred from transaction dates.
- **Recurring income:** a credit pattern seen in at least 3 months with amount variation below 25% (coefficient of variation).
- **Not a model input**, because no labelled dataset links transaction behaviour to repayment outcomes. Every response carries `used_for_risk_model: false`.

### 6.9 What-if simulator and counterfactuals (`scenarios.py`, `policy.py`)
- **What-if:** you change allowed values and compare model outputs side by side (base vs up to 5 scenarios).
- **Counterfactual:** the system *searches* for alternative terms that satisfy a demonstration policy. "What is the smallest change that would meet the rules?"
- **Constraints (the ethics):** only loan amount, tenure and interest rate may change; existing EMI only as an explicitly **hypothetical** debt-reduction (opt-in); income, age, employment, number of loans and credit history can **never** change. The API rejects such requests and tests prove immutable fields stay fixed.
- **Always recalculated:** each alternative goes through the shared feature code, so EMI, EMI-to-income and total interest are recomputed, not patched. Longer tenure lowers EMI but raises total interest; the UI shows both.
- **Search:** a bounded grid (amount 25-100% of the request; tenure 6-84 months in steps of 6; optionally 5 debt levels). Ranking cost = `1.0 x share of loan cut + 0.5 x tenure change/78 + 2.0 x share of existing EMI cut`. **The weights are design choices**, not learned.
- **Honest outputs:** `found`, `already_meets_policy`, or `no_feasible_alternative` (with the searched range and the closest attempt, which does not pass). A model-output change is an association, not a proven causal effect, and approval is never guaranteed.
- **Policy (`policy.py`, `demo-policy-1.0`):** simulated default probability at most 20% **and** total EMI-to-income at most 50%; product limits (loan at least 10,000, tenure 6-84 months). These are experimental demonstration thresholds, not a lending policy. The policy is separate from the model, so rules can change without retraining.

### 6.10 Fairness (`fairness.py`)
- **Definitions first** (a common interview trap): *positive prediction* = the model **flags** a client as high risk; the *favourable outcome* for the client = **not flagged**. Fairlearn's "selection rate" is therefore the **flagged rate**. Main harm = **false positives** (flagged but did not default: possible wrongful denial).
- **Metrics per group:** size; flagged rate; false-positive rate (FPR); false-negative rate (FNR); observed default rate; calibration gap (mean predicted minus observed); plus summaries: demographic parity difference/ratio and equalized-odds difference.
- **Uncertainty:** 95% **Wilson** intervals; groups under 100 clients are flagged unreliable and excluded from summaries; an FPR needs at least 30 non-defaulters in the group.
- **Discipline:** the threshold (0.28, maximising F1) is chosen on the **validation** split; all group metrics use the untouched **test** split.
- **Real findings (seed 42):** men were flagged more often than women (about 27% vs 22%) and wrongly flagged more often (FPR about 17% vs 13%), with non-overlapping intervals; calibration gaps by sex were tiny (+/-0.006). Observed default rates also differ between the groups, so this alone is not proof of bias. Age 50+ had the highest wrongly-flagged rate (about 22% vs 13-15%, n=422).
- **Mitigation experiment:** Fairlearn `ThresholdOptimizer` (equalized odds on sex) barely moved the error-rate gap (0.043 to 0.038) and cost about 1 point of accuracy. It is **not deployed**: it needs the protected attribute at decision time (possibly unlawful in lending), randomises some decisions, gives no calibrated probability and does not fix proxy bias.
- **Key ideas to know:** dropping sensitive columns does not remove **proxy bias** (other features can encode them); fairness metrics can **conflict** (when group base rates differ you generally cannot have calibration and equal error rates at the same time); no single number proves fairness; `AGE` is a model input here (and audited), while `SEX`, `EDUCATION`, `MARRIAGE` are excluded from inputs and used only for the audit.

### 6.11 Limited-information experiments (`experiments.py`)
- **Question:** how much does performance drop when the model sees less payment history? (a proxy for thin files)
- **Honesty:** every UCI client has 6 months, so there is **no genuine thin-file subset**. We hide months from people who have them. That is an experiment, not validated thin-file lending.
- **Protocol:** same splits, one fixed recipe per variant, no selection among variants, bootstrap 95% intervals.
- **Results:** 6 months 0.782 (0.766-0.799); last 3 months 0.776; last 2 months 0.769; last month 0.765; **no payment history (limit + age) 0.593** (Brier 0.1693 vs the 0.1722 constant baseline, i.e. almost no skill).
- **Reading it:** most signal sits in the latest repayment status; without payment history the model is nearly useless, which argues against pretending an applicant with no history can be scored.

### 6.12 Reproducibility, versions, model cards
- **Seeds** everywhere (default 42); metrics are identical across reruns (tested).
- **Versioned artifacts:** the model version string encodes model, calibrator, seed and feature-schema version. The artifact stores feature schema, library versions, provenance, limitations and the SHAP background.
- **Registry** (`registry.py`): an admin registers an artifact (a copy named by its SHA-256), activates one version per track, and the loader refuses a file whose checksum no longer matches. Every assessment records which version scored it.
- **Model cards** (`model_card.py`) are *generated* from the artifact and the evaluation report, so they cannot drift from reality.
- **Pickles are code:** `joblib` files can execute code when loaded, so only register files you trained yourself.

### 6.13 Monitoring: drift vs performance
- **Input drift:** are applicants now different from before? Measurable from inputs alone (the admin page shows prediction distribution, missingness shares, counts by status).
- **Performance degradation:** are predictions still right? **Cannot** be measured without observed repayment outcomes, which this demo never collects. The admin page says so. (In production you would join outcomes back after the horizon and track calibration and AUC over time.)

---

## 7. Concepts: backend, security, database

### 7.1 How a request flows through FastAPI
`Browser -> (proxy) -> middleware (security headers, CORS) -> router -> dependencies -> Pydantic validation -> handler -> service -> database -> response`.
- **Dependency injection** (`Depends`): small reusable functions that run before the handler. `get_db` yields a database session; `authenticated_user` finds the session and enforces CSRF; `applicant_user`, `reviewer_user`, `admin_user`, `staff_user` wrap it with a role check. FastAPI shares one `get_db` session per request, so the auth lookup and the handler see the same transaction.
- **Pydantic models** are the contract at the edge: `LoanApplication` constrains each field (income > 0, tenure 3-360...). Bad input never reaches business code; the client gets a clear **422**.
- **Thin routes, fat services:** routes translate HTTP; `app_service.py` holds the rules. That keeps rules testable without HTTP.

### 7.2 Status codes used and why
| Code | Meaning here |
|---|---|
| 401 | Not logged in, or session expired |
| 403 | Logged in but not allowed (wrong role, bad CSRF token, disallowed Origin, reviewing your own case) |
| 404 | Does not exist **or is not yours** (so ids cannot be probed) |
| 409 | Wrong state (editing a locked application, deciding twice, duplicate email) |
| 413 / 415 | Upload too large / not a CSV |
| 422 | Input failed validation (including password policy and override-reason rule) |
| 429 | Account temporarily locked after repeated failed logins |
| 503 | A dependency is not ready (no active model, tampered model file) |

### 7.3 Authentication
- **Registration** creates only `applicant`s, records consent (notice version), and starts a session. Reviewer/admin accounts are created by an admin (API or `python -m app.admin`).
- **Password storage:** **Argon2id**, a deliberately slow, memory-hard hash with a per-password salt (handled by the library). Never store or log the password. Policy follows current guidance: length (10+) over composition rules, plus a small deny-list and "not your email name".
- **Login hardening:** one generic error ("Invalid email or password") for unknown email and wrong password; an unknown email still performs a dummy hash so timing does not leak which accounts exist; after 5 failures the account locks for 15 minutes (trade-off: an attacker can deliberately lock a victim, which is why real systems add rate limiting and alerts).
- **Sessions:** on login a random 256-bit token is generated; the cookie holds the token, the database holds only its **SHA-256**. A database leak therefore does not leak usable sessions. A **new token on every login** prevents session fixation. Sessions expire (8 h), and logout, role change and deactivation delete them immediately.

### 7.4 Cookies, CSRF, CORS and "same site" (the part interviewers love)
- **Cookie flags:** `HttpOnly` (JavaScript cannot read it, so an XSS bug cannot steal it); `SameSite=Lax` (not sent on cross-site subrequests); `Secure` (HTTPS only; enabled by `CREDITLENS_COOKIE_SECURE=true`).
- **CSRF** (cross-site request forgery): a malicious site makes your browser send a request to our API and the browser attaches your cookie automatically. Defences used: (1) **synchronizer token**: each session has a secret CSRF token returned only in a JSON response to the logged-in page; every POST/PATCH/DELETE must echo it in `X-CSRF-Token`; a third-party site cannot read it; (2) an **Origin check** against the allow-list; (3) `SameSite=Lax`. The token is held **in memory** in the browser, never in localStorage.
- **CORS** (cross-origin resource sharing) is a *browser* rule that decides whether JavaScript on origin A may read responses from origin B. We allow exactly one configured origin, with credentials. It is not a server-side access control.
- **Origin vs site:** an *origin* is scheme + host + port; a *site* is scheme + registrable domain (ports ignored). `localhost:3000` and `localhost:8000` are different origins but the **same site**, so Lax cookies flow. `localhost` vs `127.0.0.1` are **different sites**, and `*.vercel.app` vs `*.onrender.com` are different sites too, so the cookie would be dropped.
- **The fix in production:** the Vercel site **proxies `/api/*`** to Render, so the browser only talks to one origin (cookies first-party, no CORS needed). The backend's allow-list still needs the site's origin because of the Origin check.
- **Why not JWT in localStorage:** it is readable by any XSS, cannot be revoked before expiry, and role changes would not apply until it expires. A server-side session fixes all three.

### 7.5 Authorization
- **Roles:** applicant, reviewer, admin. **Server-side on every route.** Front-end guards are convenience only.
- **Least privilege:** admins cannot read application contents; reviewers cannot create applications, cannot see drafts and cannot review their own case; reviewers see a pseudonymous reference (`U12`), never an email.
- **IDOR** (insecure direct object reference): changing an id in the URL to read someone else's data. Defence: every query checks ownership and returns 404 otherwise; random UUIDs for application ids; tests try every route as the wrong user.
- **Safety net:** `tests/test_security.py` enumerates all 44 routes from the OpenAPI spec, calls each anonymously (must be 401) and with the wrong roles (must be 403). A future endpoint added without a guard fails the build.

### 7.6 Workflow, review and audit
- **State machine** (`workflow.py`): the allowed transitions are a table; every status change goes through one function that validates and writes an audit event. Illegal moves raise errors (409 to the client).
- **Why a state machine:** it makes illegal states unrepresentable and makes the process explainable and testable.
- **Submission pipeline** (`app_service.submit_application`): `draft -> submitted -> validation -> assessed -> manual_review` in one database transaction; validation failure returns to `draft` and commits so the failure is recorded. An unanswered reviewer question is checked *before* any state change (a bug found while building: otherwise the applicant could get stuck).
- **Every submission goes to a human** in this demo; the *reasons* (unknown history, missing/insufficient cash-flow data, uncertain categories, policy rules not met) are recorded for the reviewer.
- **Model output vs human decision are different rows** (`assessments` vs `review_decisions`). A decision stores the policy recommendation, whether it was an override, and the override reason (mandatory, at least 10 characters, when the decision differs from the recommendation).
- **Reproducibility of a past assessment:** each assessment stores the input snapshot, feature values, model version (and the checksum-verified registry row), feature-schema version, policy version, explanation, and a cash-flow summary.
- **Audit chain** (`audit.py`): each event stores `sha256(previous_hash + canonical JSON of the event)`. Editing or deleting an old event breaks every later hash, which `verify` detects. It is **tamper-evident, not tamper-proof** (someone with full database access could rewrite the whole chain). Events hold ids and enum values only, never raw financial content; there are deliberately no foreign keys so the record survives deletion of the application.

### 7.7 Database design
- **13 tables**, generic types only (portable to PostgreSQL): users, sessions, consent_records, applications, uploads, transactions, assessments, feature_snapshots, explanations, info_requests, review_decisions, model_versions, audit_events.
- **Choices:** application ids are random UUID strings; timestamps are naive UTC; JSON columns hold snapshots and explanations; a `CHECK` constraint limits `users.role`; unique constraints prevent duplicate model registrations and duplicate transaction keys; SQLite foreign keys are switched on with `PRAGMA foreign_keys=ON` (off by default in SQLite!).
- **Cascades:** deleting an application removes its upload, transactions, assessments, explanations and decisions; the audit row stays.
- **Alembic migrations:** schema changes are versioned scripts (`0001_initial_schema`). A test upgrades a blank database, compares the result with the ORM models (no drift allowed) and checks downgrade works. `render_as_batch` makes SQLite migrations possible.
- **SQLite vs PostgreSQL:** SQLite = a file, no server, one writer, great for local dev/tests; PostgreSQL = a server with concurrency, richer types and managed hosting. The same migration and the same database tests pass on both (PostgreSQL 16.2 verified).
- **Transactions:** handlers commit once at the end, so a failure mid-way rolls everything back. Isolation, locking and the single-writer audit-chain caveat matter at scale (see Future improvements).
- **Retention and deletion:** applicants can delete their own application unless it is in review; there is no automated retention job and no user-deletion endpoint (stated limitations).

### 7.8 Configuration and operations
- **12-factor style:** all configuration comes from environment variables (`config.py`, `.env.example`); no secrets in code. `python -m app.admin bootstrap` is idempotent and prints no passwords (deployment logs are stored), reading the first admin from `CREDITLENS_BOOTSTRAP_ADMIN_*`.
- **Performance facts (measured):** API starts in about 3 s; a full register -> assess -> explain -> submit flow keeps memory around 230-240 MB; one SHAP explanation takes tens of milliseconds; the loaded model is cached per artifact checksum.

---

## 8. Concepts: frontend, testing, delivery

### 8.1 Frontend architecture
- **Next.js App Router:** each folder under `src/app` with a `page.tsx` is a route (`/dashboard`, `/applications/[id]`). Most pages are thin server components that render a **client component** (`"use client"`) because they need state, effects and browser APIs.
- **Auth on the client:** `AuthProvider` (React context) calls `/auth/me` on load, stores the user and CSRF token **in memory**, and exposes `login`, `register`, `logout`. `RequireAuth` shows a login prompt or "Not permitted" for the wrong role. These are UX conveniences; the API is the authority.
- **API client** (`lib/api.ts`): one `fetch` wrapper that sends cookies (`credentials: "include"`), adds `X-CSRF-Token` on non-GET requests, times out with `AbortController`, and turns every failure into an `ApiError` with a human message (network down, timeout, FastAPI validation arrays, structured problem lists).
- **Forms:** validation in `lib/fields.ts` mirrors the backend's limits for quick feedback, but the server stays authoritative (it re-validates everything). Unknown credit history is a checkbox that sends `null`, not `0`.
- **Every page handles** loading, empty, validation error, network failure and success. Example data buttons are labelled "fictional demo inputs"; no result is hard-coded.
- **Accessibility:** labels tied to inputs, `aria-live` regions, `role="alert"` for errors, tables with captions and `scope`, keyboard-reachable tabs, status never conveyed by colour alone ("+0.585" and "raised" accompany red), a skip link, dark-mode aware colours.
- **Security on the front end:** React escapes rendered text (no `dangerouslySetInnerHTML` anywhere), no token in localStorage, security headers in `next.config.ts`.
- **State management:** plain `useState` and context. No Redux: the state is local to workflows, and adding a library would hide the data flow you must be able to explain.

### 8.2 Testing strategy (296 automated tests)
| Level | Examples | Count |
|---|---|---|
| Unit | EMI known value, zero interest, invalid tenure, missing-vs-zero, calibrators, Wilson intervals | many |
| Integration (API + real database) | register -> create -> upload -> preview -> submit -> review -> decide; ownership; CSRF; lockout; admin | 100+ |
| Black-box sweeps | every route anonymous (401), wrong role (403) | 3 |
| Contract / invariants | training = inference features; SHAP additivity; artifact reload identical; migrations match models | many |
| Cross-database | the 50+ database tests also run on PostgreSQL 16.2 | |
| Frontend component | login, workflow, reviewer override rule, admin, charts-free tables | 86 |
| End-to-end | API-level flow in pytest; real-browser Playwright script (`e2e/`) | 2 |
- **What they prove and do not:** they prove behaviour and guard regressions; they do **not** prove model quality on real data, and code **coverage was not measured** (say so if asked).
- **Good test habits used:** hand-computed expectations (the cash-flow test checks an average net cash flow of 7,333.33 worked out on paper first), tests that cross-check against a trusted library (my fairness metrics vs Fairlearn), tests of failure paths (no active model gives 503, tampered model file refused), and tests that fail when a safety property regresses (new route without a guard).
- **Real bugs the tests caught:** a pandas 3 `NaN` truthiness bug that flagged unrelated rows as duplicates; a state-machine trap (unanswered reviewer question); a wrong assumption about edge months in cash flow.

### 8.3 Git, CI/CD and delivery
- **Git hygiene:** `.gitignore` excludes secrets, databases, model files, the dataset and build output; `.gitattributes` normalises line endings; commit small and meaningful (`feat:`, `fix:`, `docs:` prefixes), tag releases (`v1.0.0`).
- **CI (GitHub Actions):** backend tests, the same database tests on a PostgreSQL service, security scans (Bandit, npm audit), frontend typecheck/lint/tests/build. **Dependabot** opens weekly update PRs. (The workflow file has not been run on GitHub by the author; the commands it runs were run locally.)
- **CD (as configured; connect the repos to activate it):** push to `main` -> Render builds the API (installs pinned packages, trains the model, bootstraps on start) and Vercel builds the site. Secrets live in the providers' environment settings, never in the repo.
- **Environments and the free-tier reality:** Render's free service sleeps and has an ephemeral disk, free Postgres expires after 30 days; Vercel Hobby is non-commercial. These limits are in `docs/DEPLOYMENT.md`.

---

## 9. Business view and use cases

### 9.1 Who uses it and what they get
| Persona | Needs | What the product gives them |
|---|---|---|
| **Applicant / thin-file borrower** | A fair hearing, reasons, a way to fix wrong data | Plain-language reason codes, editable transaction categories, scenario comparison, status tracking, deletion |
| **Credit reviewer / underwriter** | Speed, context, defensible decisions | Queue, quality flags, cash-flow summary, model output **and** full explanation, mandatory override reasons |
| **Risk / model-governance lead** | Control over which model scores people | Versioned artifacts with checksums, activation workflow, monitoring, model cards |
| **Compliance / internal audit** | Evidence after the fact | Immutable-style audit trail, stored input snapshots, fairness report |
| **Data scientist** | Reusable, leak-free pipeline | Shared features, four-way splits, calibration and evaluation harness |
| **Educator / student** | A realistic, honest teaching case | Synthetic data, documented concepts, interview guide |

### 9.2 Where this kind of product fits
NBFCs and digital lenders (human-in-the-loop underwriting for thin-file segments), banks (a challenger/explanation layer beside an incumbent scorecard), BNPL and credit-line fintechs (fast cash-flow-based assessment), microfinance institutions, and model-risk or regtech vendors (governance, fairness and audit tooling). The same pattern (calibrated model + explanation + policy + human + audit) applies to insurance underwriting, fraud review and hiring-screen audits.

### 9.3 Why it matters commercially
- **Inclusion:** many creditworthy people have no bureau history; transparent alternative-data assessment can widen the addressable market *if validated*.
- **Risk:** calibrated probabilities enable correct pricing, limits and provisioning; a ranking-only model cannot.
- **Cost of compliance:** explanations, fairness evidence and audit logs are expensive to retrofit; designing them in is cheaper.
- **Trust:** reviewers who can see *why* adopt the system; applicants who get reasons complain less.
- **Operational control:** model registry, monitoring and activation controls reduce model-risk incidents.
- **Startup angle (your stated long-term goal):** a governance-and-explanation layer sold as software to small lenders that cannot build it themselves; KPIs to track would be time-to-decision, override rate, approval and loss rates, appeal rate, and fairness gaps.

### 9.4 What a real company would still need (be explicit)
Real labelled outcome data for the target market and product; temporal and out-of-time validation; a validated policy owned by credit risk; legal review of data use, consent and automated-decision rules; bureau/Account-Aggregator style data integrations under proper licences; MFA, rate limiting, encryption and a security audit; monitoring with outcome feedback; SLAs, backups and incident response.

---

## 10. Future improvements (prioritised)

**Highest value**
1. **Real outcome data and temporal validation** for a chosen market and product (out-of-time test, population drift study).
2. **Outcome-based monitoring:** join repayment outcomes back; track calibration and AUC over time; drift metrics (PSI, KS) on inputs.
3. **Security hardening:** MFA, password reset and email verification, IP rate limiting (Redis), Content-Security-Policy with nonces, encryption at rest or field-level encryption for transaction text, secrets manager.
4. **Persist scenarios and add an appeals/correction flow** for applicants (and notifications).
5. **Champion/challenger models:** serve a shadow model, compare on live traffic, promote with approval.

**ML depth**
6. Monotonic constraints (e.g. higher EMI burden can never lower risk), conformal prediction for honest uncertainty intervals, reject inference, intersectional fairness, DiCE-style counterfactuals compared with the transparent search.
7. Bounded **LLM assistance** with a template fallback for plain-language and Hindi/English explanations (never changing scores, validating against structured facts; deferred in the original spec).
8. **Statement parsing:** PDF/OCR and bank-aggregator formats (where legally permitted).

**Engineering**
9. Docker image and infrastructure-as-code, background workers for training and large uploads (Celery/RQ), caching, structured logging and tracing (OpenTelemetry) with alerting, managed backups.
10. Concurrency-safe audit chain (per-partition chains or external anchoring), retention jobs, data-subject request endpoints.
11. Playwright end-to-end in CI, coverage reporting, generated API client types from OpenAPI, load tests.

## 11. Glossary
**AUC (ROC-AUC):** ranking quality, 0.5 = random, 1 = perfect. **Average precision:** area under the precision-recall curve. **Background data (SHAP):** reference rows defining "average" behaviour. **Brier score:** mean squared probability error. **Calibration:** predicted probabilities matching observed frequencies. **CORS:** browser rule for cross-origin reads. **Counterfactual:** a changed scenario that would meet a condition. **CSRF:** forged cross-site requests using your cookie. **Data leakage:** information that would not be available at prediction time influencing training. **Demographic parity:** equal flagged rates across groups. **Equalized odds:** equal error rates across groups. **ECE:** expected calibration error. **EMI:** equated monthly instalment. **False positive rate:** non-defaulters wrongly flagged. **HttpOnly:** cookie not readable by JavaScript. **IDOR:** reading others' objects by changing an id. **Isotonic regression:** monotone step-function calibration. **Migration:** a versioned schema change. **Model card:** a standard description of a model's use, data, results and limits. **Origin:** scheme + host + port. **Platt scaling:** sigmoid calibration. **PD:** probability of default. **Proxy variable:** a feature that encodes a protected attribute. **Reliability curve:** observed vs predicted probability plot. **SameSite:** cookie rule limiting cross-site sending. **SHAP:** additive feature attributions based on Shapley values. **Site:** scheme + registrable domain. **State machine:** a fixed set of states and allowed moves. **Thin file:** an applicant with little credit history. **Train/serve skew:** features computed differently in training and production. **Wilson interval:** confidence interval for a proportion that behaves well for small samples.
