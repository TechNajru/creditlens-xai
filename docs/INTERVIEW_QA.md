# Interview question bank for CreditLens XAI

How to use it: read a question, answer **out loud** in your own words in 30-60 seconds, then compare. Answers are deliberately short; the reasoning lives in `PROJECT_GUIDE.md`. Numbers come from this project's actual runs (seed 42). Say "in my project" and give a real example; interviewers reward specifics.

**Golden rules:** (1) never claim more than you built (synthetic data, demonstration policy, no real validation); (2) when you do not know, say how you would find out; (3) for every design choice be ready to name the alternative and the trade-off.

Sections: A Overview and behavioural · B Credit risk and ML fundamentals · C Metrics and evaluation · D Calibration · E Explainability · F Fairness · G Leakage, splits, pipelines · H Backend and API · I Security · J Database · K Frontend · L Testing, CI, Git · M Deployment and system design · N Business and ethics · O Tricky questions · P Pitches and reference sheet

---

## A. Overview and behavioural

**A1. Describe the project in 30 seconds.**
It is an educational credit-risk decision-support platform: a calibrated model scores a loan application, SHAP explains the score, a fairness audit checks group outcomes, a human reviewer records the final demonstration decision, and a hash-chained audit trail records everything. FastAPI and PostgreSQL on the back, Next.js on the front, 296 automated tests, and a documented, tested deployment path to Render and Vercel. [Once you have actually deployed it, say "deployed on Render and Vercel" and add your live URL; until then do not claim it is live.] It uses synthetic data for the loan model and is explicit that it is not a real lender.

**A2. Why did you build it instead of a standard "loan prediction" notebook?**
Notebook projects stop at accuracy. Real lending needs trustworthy probabilities, reasons, fairness evidence, human accountability and auditability. I wanted to show I can build the whole chain, including the parts that make ML usable in a regulated setting.

**A3. What was the hardest part?**
Getting the *honesty* right while keeping it useful: separating real public data from synthetic data, refusing to claim results I cannot support, and making every number traceable (versions, snapshots, audit). Technically, the trickiest areas were cookie/CSRF behaviour across origins and making explanations provably consistent (SHAP additivity check).

**A4. Tell me about a bug you found and how.**
Two good ones. (1) The original prototype computed EMI-to-income differently in training and prediction (train/serve skew); I fixed it with one shared feature function and a parity test. (2) A pandas 3 behaviour: empty optional CSV fields became `NaN`, which is truthy and equal to itself, so two rows with no transaction id were flagged as duplicates. A test with missing ids caught it; I normalised empties to `None`.

**A5. What would you do differently?**
Start with the audit and workflow model earlier, add rate limiting and MFA, and get real outcome data for out-of-time validation. I would also measure test coverage and add Playwright to CI.

**A6. How did you decide what *not* to build?**
I cut Kubernetes, microservices, Kafka, graph models and live bank integrations: they add risk without helping the learning goal at this scale. I deferred the LLM feature because the core had to be correct and usable without a paid API.

**A7. Did you build this alone? Did you use AI tools?**
Be honest. A good answer: "I built it with an AI assistant under my direction, working stage by stage. I ran and verified each stage, I can explain every module, and I am happy to change something live." Then *prove* it: be ready to walk through `features.py`, the state machine and the cookie flow without notes. Never claim sole authorship of work you cannot explain. (Check the policy of the company or course you are applying to.)

**A8. How did you know the system works?**
296 automated tests, a black-box sweep of every route, database tests on both SQLite and PostgreSQL, a real-browser run of the full journey, static analysis (Bandit), and dependency audits. I also measured memory (about 236 MB) and start-up time (about 3 s).

**A9. What are you proudest of?**
The explanation guard: SHAP contributions must add up to the model score or the explanation is withheld. It shows I treat explanations as claims that can be checked, not decoration.

**A10. What is the biggest limitation?**
The loan model learns a rule I wrote (synthetic data), and the UCI model reflects 2005 Taiwan credit-card clients with no time-based validation. So none of it proves real-world lending performance. The value is the engineering and the responsible-AI practice.

---

## B. Credit risk and ML fundamentals

**B1. What is probability of default?**
The estimated probability a borrower fails to repay within a defined horizon under a defined default definition. Without the horizon and definition the number means nothing. In UCI it is "default next month".

**B2. What is a thin-file applicant and why is it hard?**
Someone with little or no credit history, so bureau scores cannot rate them. Alternative data such as cash-flow can help, but only if validated on labelled outcomes. My experiment shows that with *no* payment history the model has almost no skill (AUC 0.593).

**B3. Why not just use accuracy?**
Defaults are about 22% of UCI clients, so predicting "no default" for everyone is 78% accurate and useless. I use ranking metrics (ROC-AUC, average precision), probability metrics (Brier, log loss) and threshold trade-offs.

**B4. Which models did you compare and why?**
Logistic Regression (simple, interpretable baseline), Random Forest (non-linear, robust) and HistGradientBoosting (strong on tabular data, handles missing values). I did not assume the fanciest wins; I chose by validation Brier score. On UCI boosting won narrowly over Random Forest (0.1313 vs 0.1318), which I report as a practical tie.

**B5. Why did Logistic Regression win on your synthetic data?**
Because I generated the labels with a logistic-style rule, so a logistic model recovers it perfectly. It is an artefact of the simulation, not evidence about model families.

**B6. How do you handle class imbalance?**
I did not use class weights or oversampling, because both distort probabilities and I need real probabilities. I use probability-aware metrics, calibrate, and treat thresholds as a separate, experimental decision. If I used SMOTE I would apply it only inside training folds.

**B7. Explain overfitting and how you controlled it.**
A model that memorises training noise performs worse on new data. Controls: separate validation data for selection, an untouched test split, regularisation-like settings (`min_samples_leaf`, shallow leaves), and calibration on its own split.

**B8. Logistic Regression vs tree ensembles?**
Linear models are simple and have directly interpretable coefficients but assume linear log-odds; ensembles capture interactions and non-linearity but are harder to explain (hence SHAP). On UCI the ensembles beat Logistic Regression (AUC about 0.78 vs 0.74), partly because of extreme values and coded features.

**B9. What is a Pipeline and why use it?**
It chains preprocessing and the model so preprocessing is fitted only on training data and applied identically at prediction. It prevents leakage and train/serve skew.

**B10. How do you treat missing values?**
Unknown is not zero. Credit-history length stays `NaN` with an explicit missing indicator; undefined ratios stay `NaN`. Logistic Regression and Random Forest use median imputation (with indicators for the public model); HistGradientBoosting handles `NaN` natively.

**B11. Explain the EMI formula.**
`EMI = P r (1+r)^n / ((1+r)^n - 1)`, with `r` the monthly rate (annual/12/100) and `n` the months. It makes the present value of `n` equal payments equal the principal. At 0% interest it reduces to `P/n`. Example: 100,000 at 12% for 12 months is 8,884.88.

**B12. Why is total EMI-to-income a good feature?**
It measures affordability: how much of monthly income is committed to debt service including the new loan. It was also the top SHAP driver on the synthetic model, matching the generating rule (a good sanity check).

**B13. What is train/serve skew?**
When the model sees differently-computed features in production than in training. The original prototype had it. I now compute features in one function used everywhere and test that batch and single-row results are identical.

**B14. Why did you build a second, separate model for the UCI data?**
It is credit-card data (limits, bills, repayment status), not loan applications (amount, tenure, EMI). Different feature schema and population, so it must be a different model, reported separately. Mixing them would be unsound.

**B15. What does "no silent clipping" mean?**
Out-of-range inputs are rejected with an error rather than quietly altered, so we never score a different input from the one supplied. Unusual real values (negative bills, a payment ratio around 11,454) are kept and documented.

---

## C. Metrics and evaluation

**C1. Explain ROC-AUC intuitively.**
It is the probability that a randomly chosen defaulter gets a higher score than a randomly chosen non-defaulter. 0.5 is random; my UCI model scored 0.782 on the untouched test split.

**C2. Why is ROC-AUC alone not enough?**
It only measures ranking. A model can rank well and still output badly miscalibrated probabilities. Pricing and limits need the probabilities, hence Brier score and calibration checks.

**C3. What is the Brier score?**
The mean squared difference between predicted probability and the 0/1 outcome. It is a proper scoring rule: it rewards both discrimination and calibration. UCI: 0.134 for the model vs 0.172 for a constant base-rate predictor.

**C4. Precision, recall, F1: what trade-off?**
Precision = flagged clients who truly default; recall = defaulters we catch. Raising the threshold raises precision and lowers recall. At 0.2 I got precision 0.42 and recall 0.66; at 0.5, 0.69 and 0.35. The right threshold is a business and policy decision, so I label mine experimental.

**C5. What is average precision and what is its baseline?**
Area under the precision-recall curve, more informative with imbalance. The random baseline equals prevalence, 0.221; my model had 0.563.

**C6. How did you choose a threshold for the fairness audit?**
On the validation split by maximising F1 (0.28), then I measured group metrics on the untouched test split. Choosing it on the test data would leak.

**C7. What is a confusion matrix?**
Counts of true/false positives and negatives at a threshold; all threshold metrics derive from it.

**C8. How do you compare models fairly?**
Same splits, same preprocessing inside pipelines, a documented selection criterion on validation data, test set touched once. I also report non-selected models on the test set for information only, clearly labelled.

**C9. Why a majority/constant baseline?**
It sets the floor. If a model barely beats "predict the average", the extra complexity is not earning its keep. In the no-history experiment my model (Brier 0.1693) barely beat the baseline (0.1722).

**C10. What are confidence intervals on metrics for?**
Test sets are samples. I report bootstrap 95% intervals for AUC in the experiments and Wilson intervals for rates in the fairness audit, so differences smaller than the noise are not over-interpreted.

**C11. Can you trust the test metrics for the future?**
Only partly. UCI is a single snapshot with random splits; there is no out-of-time validation. Metrics describe that dataset, not the world next year.

**C12. What is log loss and when does it matter?**
The negative average log-likelihood; it heavily penalises confident wrong predictions, which matters when probabilities drive decisions.

---

## D. Calibration

**D1. What is calibration?**
Predicted probabilities match observed frequencies: among clients scored 30%, about 30% default.

**D2. Why can a high-AUC model be badly calibrated?**
AUC depends only on the order of scores. Multiplying all scores by 0.5 keeps AUC identical but halves every probability.

**D3. Platt (sigmoid) vs isotonic?**
Sigmoid fits a two-parameter logistic curve on the model's log-odds: stable with little data but assumes that shape. Isotonic fits a monotone step function: flexible but needs more data and can produce ties. I compare both plus "none" on validation.

**D4. Why a separate calibration split?**
Fitting the calibrator on data used to evaluate it would flatter the result. Training fits the model, calibration fits the calibrator, validation chooses, test evaluates once.

**D5. How did you evaluate calibration?**
Reliability curve on the test split (predicted 0.704 vs observed 0.702 in the top bin), Brier score, and expected calibration error (0.0066 for the full-history model).

**D6. Does class weighting affect calibration?**
Yes: re-weighting changes the base rate the model learns, shifting probabilities. That is why I avoided it and calibrate instead.

**D7. Is 1 - P(default) the probability of approval?**
No. Approval depends on policy, capacity, fraud checks and more. The UI states this. The display is "simulated probability of default under the dataset's definition".

**D8. If calibration drifts in production, how would you know?**
By comparing predicted and observed rates after outcomes arrive. This demo cannot, because it never observes outcomes, and the admin page says so.

---

## E. Explainability

**E1. How does SHAP work?**
Based on Shapley values: a feature's contribution is its average marginal effect on the prediction across many orderings of the features. Contributions plus a baseline (the average prediction over a background sample) add up to the model's output for that person.

**E2. Why PermutationExplainer?**
It is model-agnostic, so it works with any selected model and with my whole pipeline (imputers and scalers included), and it satisfies additivity. TreeSHAP is faster but only for supported tree models.

**E3. What exactly do the contributions add up to?**
The model's uncalibrated raw score, not the displayed calibrated probability. I verify `baseline + sum(contributions) = raw score` (tolerance 1e-6) on every request.

**E4. Are SHAP values percentage-point changes in probability?**
No, because of the calibration step, and the UI says so. They describe the raw score scale.

**E5. Does SHAP show causation?**
No. It shows how the *model* uses its inputs. Changing a real-world input might not change the outcome as the model suggests.

**E6. Feature importance vs SHAP?**
Global feature importance (mean |SHAP| or impurity importance) describes the model overall. SHAP also gives a per-person decomposition. A feature important on average may be irrelevant for one individual.

**E7. What if the explainer fails?**
The API returns `unavailable` with a reason, the prediction still works, and nothing is fabricated. A failed additivity check also withholds the explanation.

**E8. What problem do correlated features cause?**
Credit is shared among them, so a feature that looks risky (large total EMI) can show a small negative contribution while a related ratio carries the big positive one. I document this and tell users to read related features together.

**E9. What are reason codes?**
Plain-language statements of the top factors, such as "Total EMI as a share of monthly income: 140%, raised the model's risk score". They make explanations usable for applicants.

**E10. Why different explanation detail for applicants and reviewers?**
Applicants need understandable reasons; reviewers need the full table, chart, method and versions to challenge the model. The server returns the reduced view to applicants, not just the UI.

---

## F. Fairness

**F1. How did you define "positive prediction" and why does it matter?**
Positive = the model flags a client as high risk; the favourable outcome for the client is *not* being flagged. Without stating this, "selection rate" is ambiguous (selected to be denied or approved?). Fairlearn's selection rate is therefore my flagged rate.

**F2. Which harm did you focus on?**
False positives (flagged but did not default), because they could wrongly deny someone. I still report false negatives.

**F3. Demographic parity vs equalized odds?**
Demographic parity: equal flagged rates across groups. Equalized odds: equal false-positive and true-positive rates across groups. They answer different questions and can conflict.

**F4. Why can't we satisfy every fairness metric at once?**
Results by Kleinberg et al. and Chouldechova show that when groups have different base rates you generally cannot have calibration and equal error rates simultaneously. So fairness needs a stated choice, not a single score.

**F5. Does removing sex from the features make the model fair?**
No: other features can act as proxies. That is why the audit measures outcomes by group. In my model `SEX`, `EDUCATION`, `MARRIAGE` are excluded from inputs but used for auditing, and `AGE` is an input and also audited.

**F6. What did you find?**
Men were flagged more (about 27% vs 22%) and wrongly flagged more (FPR about 17% vs 13%) with non-overlapping intervals; calibration gaps by sex were tiny. Age 50+ had the highest wrongly-flagged rate (about 22%). Observed default rates differ between groups, so this is evidence to investigate, not proof of bias.

**F7. How did you handle small groups?**
Groups under 100 clients are flagged unreliable and excluded from disparity summaries; a rate needs at least 30 relevant cases; every rate has a 95% Wilson interval.

**F8. What mitigation did you try and why didn't you deploy it?**
Fairlearn `ThresholdOptimizer` (equalized odds on sex). It barely moved the gap (0.043 to 0.038) and cost about 1 point of accuracy. It also needs the protected attribute at decision time (possibly unlawful), randomises some decisions, gives no calibrated probability and does not fix proxies. So I analysed it and left it undeployed.

**F9. Is it legal to use group-specific thresholds?**
Often not in lending, and it depends on jurisdiction. That is a legal and policy decision, not a technical one, which is exactly why I do not apply it automatically.

**F10. How would you improve the fairness work?**
Intersectional groups, out-of-time data, in-processing methods that do not need the attribute at prediction, and stakeholder review of which harms matter.

---

## G. Leakage, splits, pipelines

**G1. What is data leakage? Give examples.**
Information unavailable at prediction time influencing training: the label in the features, preprocessing fitted on all data, tuning on the test set, post-outcome fields. My guards: target and sensitive columns checked out of features (explicit error), preprocessing inside pipelines, four-way split, test touched once.

**G2. Why four splits?**
Train (fit), calibration (fit calibrator), validation (choose model and calibrator), test (final, once). Reusing one set for two jobs produces optimistic results.

**G3. Why stratified?**
To keep the default rate similar in every split (22.1%), so metrics are comparable.

**G4. Why no time-based split?**
UCI is a single snapshot with no usable time ordering for this purpose. Out-of-time validation is on my future-work list; I state this limitation.

**G5. How do you make results reproducible?**
Fixed seeds, pinned library versions, versioned artifacts that record versions and provenance, and tests that retrain twice and compare metrics.

**G6. What about duplicate rows?**
UCI has 35 rows identical apart from ID. They are distinct clients so I kept them and documented it; with group-aware data (repeated applicants) I would split by group.

---

## H. Backend and API design

**H1. Why FastAPI?**
Typed validation with Pydantic, automatic OpenAPI docs, dependency injection and good performance, with little boilerplate. Django would add an admin and ORM I do not need; Flask would make me assemble validation myself.

**H2. What is dependency injection in FastAPI?**
Functions declared with `Depends` run before the handler and their results are injected. I use it for the database session, the current user and role checks, so security is declared at the route, not remembered inside it.

**H3. Why are most endpoints `def`, not `async def`?**
They do blocking database calls and CPU-bound ML. FastAPI runs sync endpoints in a thread pool, which keeps the event loop free. `async def` would not make CPU work faster. The upload endpoint is async only because reading the upload is awaited.

**H4. How do you validate input?**
At the edge with Pydantic constraints (income > 0, tenure 3-360, ...), then again in the feature code, because the ML layer should not trust callers. Bad input returns 422 with field messages.

**H5. How is the API versioned and organised?**
Under `/api/v1/...`, grouped by resource: auth, applications, reviews, admin, scenarios, assessments, models, fairness. Versioning lets me change contracts later without breaking clients.

**H6. Which HTTP status codes do you use for what?**
401 not logged in; 403 forbidden (role, CSRF, origin, own case); 404 missing or not yours; 409 wrong state; 413/415 upload problems; 422 validation; 429 lockout; 503 model not available.

**H7. Why 404 instead of 403 for someone else's application?**
403 confirms the resource exists. 404 reveals nothing, which blocks id probing (IDOR enumeration).

**H8. How do you keep routes thin?**
Routes handle HTTP and call services (`app_service.py`), which hold the rules. ML code never touches HTTP or the database. That makes logic unit-testable.

**H9. Pagination?**
List endpoints cap results (200) but do not paginate. That is a known limitation; with many applications I would add cursor pagination.

**H10. How do you handle configuration?**
Environment variables (12-factor): database URL, CORS origin, cookie secure flag, session length, lockout settings, bootstrap admin. No secrets in code or the repository.

---

## I. Security

**I1. How do you store passwords?**
Argon2id via argon2-cffi: a slow, memory-hard hash with per-password salt. Never plain text, never fast hashes like SHA-256 alone. I also enforce length 10+, a deny-list, and no email-name.

**I2. Sessions vs JWT: why sessions?**
Server-side sessions can be revoked instantly (logout, role change, deactivation) and the token is not readable by JavaScript when in an HttpOnly cookie. JWTs are stateless but hard to revoke, and in localStorage are exposed to XSS.

**I3. What is stored for a session?**
Only the SHA-256 of a random 256-bit token plus a CSRF token and expiry. If the database leaks, attackers cannot reuse the sessions.

**I4. What is CSRF and how do you prevent it?**
A malicious site triggers a request your browser authenticates with your cookie. I require an `X-CSRF-Token` header (a per-session secret only the real page can read) on every POST/PATCH/DELETE, check the `Origin` header against an allow-list, and use `SameSite=Lax` cookies.

**I5. What is CORS and is it a security control for the server?**
A browser mechanism that controls whether JavaScript from one origin can read responses from another. It protects users' browsers, not the API: non-browser clients ignore it. Real access control is the session, roles and CSRF checks.

**I6. Explain "site" vs "origin".**
Origin = scheme + host + port. Site = scheme + registrable domain. `localhost:3000` and `localhost:8000` are different origins but one site; `localhost` vs `127.0.0.1` are different sites; `*.vercel.app` vs `*.onrender.com` are different sites.

**I7. Why did you proxy `/api` through Vercel?**
`SameSite=Lax` cookies are not set/sent across sites. With the site and API on different domains, login would appear to work and then be lost. The Vercel rewrite makes browser traffic same-origin, keeping the cookie first-party. I tested it in a real browser.

**I8. What do HttpOnly, Secure and SameSite do?**
HttpOnly hides the cookie from JavaScript (limits XSS damage); Secure sends it only over HTTPS; SameSite limits sending on cross-site requests (CSRF defence).

**I9. How do you prevent brute force and user enumeration?**
Generic login error, a dummy hash for unknown emails to equalise timing, and a 5-failure lockout for 15 minutes. Limits: no IP rate limiting, and lockout can be abused to lock a victim; registration reveals existing emails (409).

**I10. What is IDOR and how do you prevent it?**
Accessing others' objects by changing an id. Every query checks ownership; other people's resources return 404; ids are random UUIDs; a test sweeps routes as the wrong user.

**I11. SQL injection and XSS: are you protected?**
SQL: all access via SQLAlchemy with bound parameters, no string-built SQL (checked by code search). XSS: React escapes rendered text, no `dangerouslySetInnerHTML`; HttpOnly cookies and an in-memory CSRF token limit damage if one ever slipped in. No Content-Security-Policy yet: stated limitation.

**I12. How do you protect file uploads?**
CSV only, extension and content checks (no binary), 2 MB and 5,000-row limits, UTF-8 requirement, parsed as data never executed, filenames reduced to a basename, errors reported by row number only. No CSV export exists, so formula injection is not exposed.

**I13. What did your security review find?**
Bandit found three `assert`s, two guarding against data leakage which disappear under `python -O`; I replaced them with explicit errors. pip-audit: no project dependency flagged. A route sweep proves all 44 routes enforce login and roles. I also removed a per-request model-pickle load from an endpoint.

**I14. Why are pickles risky?**
Loading a pickle can execute arbitrary code. So the registry only loads files that were registered locally, and it verifies their SHA-256 before loading. Never load model files from untrusted sources.

**I15. What is missing for production?**
MFA, password reset and email verification, IP rate limiting, Content-Security-Policy, encryption at rest, managed secrets, alerting, independent security testing.

**I16. How would you respond if a secret was committed to Git?**
Treat it as compromised: rotate it immediately, then remove it from history (`git filter-repo`), force-push, and tell collaborators to re-clone. Removing it only from the latest commit is not enough.

---

## J. Database

**J1. Why SQLAlchemy and Alembic?**
SQLAlchemy gives parameterised queries and portability between SQLite and PostgreSQL; Alembic gives versioned, reviewable schema changes. A test checks migrations match the models (no drift) and that downgrade works.

**J2. SQLite vs PostgreSQL?**
SQLite is a file: zero setup, single writer, ideal for local dev and tests. PostgreSQL is a server: concurrency, richer types, managed backups. My database tests run on both (PostgreSQL 16.2 verified).

**J3. Why JSON columns?**
For snapshots whose shape can change (inputs, explanations, cash-flow summaries) and are read as a whole. Relational columns are used for anything queried, filtered or constrained.

**J4. Why UUID primary keys for applications?**
Not guessable, so ids do not leak counts or allow enumeration. Integer ids are fine for internal tables.

**J5. How do you protect integrity in the database?**
Foreign keys (switched on explicitly in SQLite), unique constraints (model registrations, transaction keys, emails), a CHECK constraint on roles, and cascades for deleting an application's data.

**J6. Why does the audit table have no foreign keys?**
The record must survive deleting an application or user; an FK with cascade would delete the history.

**J7. Explain ACID and transactions in your app.**
Atomicity, consistency, isolation, durability. A handler commits once at the end, so a failure rolls back everything. The submission pipeline (several state changes, an assessment, an explanation) is one transaction; a validation failure commits only the "back to draft" record and then raises.

**J8. What are indexes and which did you add?**
Structures that speed lookups. I index foreign keys used in filters (`user_id`, `application_id`), status, and unique session token hashes and emails.

**J9. Where would performance problems appear?**
List views touch relationships per row (an N+1 query pattern); SHAP per request is CPU work; the single-writer audit chain would bottleneck at high write rates. Fixes: eager loading, caching/queues, partitioned or externally anchored audit chains.

**J10. How do you handle time zones?**
All timestamps are stored as naive UTC and serialised with a `Z` suffix. It is simple but you must never mix naive and aware datetimes.

**J11. How would you back up and restore?**
Managed PostgreSQL backups, tested restores, and migrations in version control. Free tiers often have no backups, which I flag in the deployment guide.

**J12. What is database normalisation and where did you denormalise?**
Normalisation avoids duplicated facts. I deliberately snapshot data (inputs, features, versions) in assessments so a past decision remains reproducible even if later records change.

---

## K. Frontend

**K1. Why Next.js?**
File-based routing, security headers and proxy rewrites in config, easy Vercel deployment, TypeScript support. A plain Vite SPA would need a separate server for rewrites and headers.

**K2. Server vs client components?**
Server components render on the server and cannot use state or effects; client components (`"use client"`) run in the browser. My pages are thin server wrappers around client components because the workflows need state, effects and cookies.

**K3. How does authentication work on the client?**
`AuthProvider` calls `/auth/me` on load, keeps the user and CSRF token in memory, and exposes login/register/logout. `RequireAuth` only improves UX; the API enforces everything again.

**K4. Why not store the token in localStorage?**
Any XSS bug could read it. The session is an HttpOnly cookie; the CSRF token lives in memory and is re-fetched on reload.

**K5. How does your API client handle errors?**
One wrapper: sends cookies, adds the CSRF header on non-GET, times out via `AbortController`, and converts network failures, timeouts and FastAPI validation arrays or structured problems into readable messages.

**K6. Explain `useEffect` cleanup in your code.**
Data-loading effects set a `cancelled` flag in their cleanup so a late response cannot update state after unmount or after the input changed (avoids race conditions and warnings).

**K7. Why not Redux?**
State is local to each workflow plus one auth context. A global store would add indirection without benefit; I can trace every state change by reading the component.

**K8. How do you keep client validation and server validation consistent?**
The client mirrors the limits for fast feedback, but the server is authoritative and re-validates. If they disagree the server's message is shown.

**K9. How did you make the UI accessible?**
Labels bound to inputs, `aria-live` for results, `role="alert"` for errors, table captions and scopes, keyboard-operable tabs, a skip link, and no information conveyed by colour alone.

**K10. What is hydration?**
React attaching behaviour to server-rendered HTML in the browser. Mismatches between server and client output cause warnings; that is another reason browser-only APIs live in effects and client components.

**K11. What are `NEXT_PUBLIC_` variables?**
Environment variables inlined into the browser bundle **at build time**, so they must be set before building and need a redeploy to change. Secrets must never use that prefix; my `BACKEND_URL` is server-side only.

**K12. How do the rewrites work?**
`next.config.ts` forwards `/api/:path*` to `BACKEND_URL` when it is set, so the browser sees one origin. Only `/api/*` is forwarded; `/health` via the site returns 404 by design.

**K13. How do you test React components?**
Vitest and Testing Library, asserting what a user sees and does (labels, roles, text) with a method-aware `fetch` mock. Example: the reviewer form must show an override field only when the decision differs from the recommendation and refuse to send without it.

**K14. What would you add to the frontend?**
Error boundaries, optimistic updates, pagination, internationalisation (including Hindi), end-to-end tests in CI, and a Content-Security-Policy with nonces.

---

## L. Testing, CI, Git

**L1. Describe your testing strategy.**
Unit tests for pure logic (EMI, calibrators, intervals), integration tests through the real API and database (full journey, ownership, CSRF, lockout), invariants (training and inference features identical, SHAP additivity, artifact reload), black-box sweeps of every route, component tests on the frontend, and a real-browser end-to-end run. 210 backend and 86 frontend tests.

**L2. What does a black-box route sweep give you?**
It reads all 44 routes from the OpenAPI spec and calls each anonymously (must be 401) and with the wrong role (must be 403). A future endpoint added without a guard fails the build, so the safety property cannot silently regress.

**L3. How do you test migrations?**
Upgrade a blank database, compare the resulting schema with the ORM metadata (no drift allowed), downgrade to base and upgrade again. The same tests run on PostgreSQL.

**L4. How do you know your fairness numbers are right?**
I cross-check my group metrics against Fairlearn's functions in tests, and compare the disparity summary with Fairlearn on the filtered groups. Hand-checked toy cases cover the Wilson interval and threshold choice.

**L5. How do you test failure paths?**
No active model gives 503 and leaves the draft untouched; a tampered model file is refused by checksum; an explainer crash still returns the prediction with `unavailable`; a forced additivity failure withholds the explanation.

**L6. Mocking vs real dependencies?**
Backend integration tests use a real database and real model files in temp folders, not mocks, so they catch real bugs. Frontend tests mock `fetch` because the browser UI is the unit under test; the real API contract is covered by the backend tests and the Playwright run.

**L7. What is your CI pipeline?**
GitHub Actions: backend tests, the database tests on a PostgreSQL service, security scans (Bandit, npm audit), and frontend typecheck, lint, tests and build. Dependabot proposes weekly updates. (I ran the same commands locally; the workflow file itself has not run on GitHub yet.)

**L8. Branching and commit practice?**
Short-lived feature branches merged by pull request into `main`, small commits with prefixes (`feat:`, `fix:`, `docs:`, `test:`), release tags like `v1.0.0`. Rebase for a clean local history, merge commits (or squash) when merging PRs.

**L9. What belongs in `.gitignore`?**
Secrets (`.env`), databases, model artifacts, datasets with their own licences, virtual environments, `node_modules`, build output, local reports. Generated and secret files must be reproducible, not committed.

**L10. Did you measure code coverage?**
No, and I say so. I used behaviour-focused tests and invariants instead; adding coverage reporting and mutation testing is on my list.

---

## M. Deployment and system design

**M1. How is it deployed?**
(Answer for the design; say "deployed" only once you have done it.) The plan is the website on Vercel and the API and PostgreSQL on Render. Render's build installs pinned packages and trains the model from source (about 10 seconds); each start runs an idempotent bootstrap (migrations, register and activate the model, create the first admin from environment variables) before Uvicorn starts. Vercel proxies `/api/*` to Render.

**M2. Why PostgreSQL on Render rather than SQLite?**
Render's free web service has an ephemeral filesystem, so a SQLite file would be erased on every restart or redeploy.

**M3. What are the free-tier limits to know?**
Render free web services sleep after about 15 minutes idle (cold start of up to a minute); free PostgreSQL expires after 30 days and has no backups; Vercel Hobby is non-commercial. Always re-check current terms.

**M4. What is a 12-factor app?**
A set of practices for portable services: configuration in environment variables, stateless processes, backing services as attached resources, logs to stdout, parity between environments. My config, bootstrap and sessions-in-database follow it.

**M5. Can the API scale horizontally?**
Mostly yes: it is stateless because sessions live in the database and models load from a registry. Caveats: each process loads the model into memory; the hash-chained audit table assumes a single writer; SHAP is CPU-bound. I would add a queue or worker for heavy work and partition or externally anchor the audit chain.

**M6. How would you handle 1 million applications a day?**
Separate scoring service with the model loaded once per worker, a message queue for assessments, read replicas for dashboards, caching of static reports, partitioned audit storage, autoscaling, and proper observability. Training and registry would be a separate offline pipeline.

**M7. How would you do zero-downtime deploys and rollbacks?**
Blue/green or rolling releases behind a health check; backwards-compatible migrations (expand then contract); keep the previous model version registered so activation can roll back instantly.

**M8. How do you roll back a bad model?**
Activate the previous registered version in the admin page. Old assessments keep the version they were scored with, so history stays truthful.

**M9. What would you monitor in production?**
Latency and error rates, queue depth, input and prediction distribution drift, missingness, override and decline rates by group, and (once outcomes arrive) calibration and AUC over time.

**M10. Why not Kubernetes or microservices?**
One API plus one website is the right size here; extra moving parts would add risk and explanation burden without benefit. I would revisit with real scale, team size or regulatory isolation needs.

---

## N. Business and ethics

**N1. Who is the customer?**
Small and mid-size lenders (NBFCs, fintechs, microfinance) that need explainable, auditable, human-in-the-loop assessment, and compliance or model-risk teams that need governance evidence.

**N2. What value does it create?**
Faster, more consistent reviews, defensible decisions with reasons, evidence for fairness and audit, controlled model changes, and a path to serve thin-file applicants if validated.

**N3. How would you measure business success?**
Time to decision, approval rate at a fixed loss rate (or loss rate at fixed approval), override rate and reasons, appeal rate, fairness gaps, model calibration over time, and reviewer productivity.

**N4. Isn't automating credit decisions dangerous?**
Yes, which is why this system supports a human, separates model from policy from decision, requires override reasons, explains scores and audits everything. Many of its choices exist to prevent over-reliance on the model.

**N5. How do you protect applicants?**
Consent notice, data minimisation (pseudonymous reviewer view), the right to correct and delete, no raw financial data in logs, clear statements of what the score is not.

**N6. What regulations apply to this domain?**
They vary by country: expect rules on explaining adverse decisions, anti-discrimination, data protection and automated decision-making, and digital-lending conduct. I would involve legal counsel; this project demonstrates building blocks, not compliance.

**N7. How would this become a startup product?**
Sell a governance-and-explanation layer to lenders who cannot build one: model registry, explanations, fairness reports, reviewer workflow, audit. Validate with a design partner on their data first.

**N8. What is your stance on alternative data like UPI?**
Promising for inclusion but risky: the data is noisy, consent and privacy matter, and unverified inflows must not be treated as income. In my engine UPI inflows are never counted as verified income, and cash-flow analytics are kept out of the risk model until a labelled dataset supports them.

---

## O. Tricky questions and how to answer honestly

**O1. "Your AUC of 0.78 is just the public dataset benchmark. What did *you* add?"**
Not a new modelling record: the contribution is the system around the model: leak-free pipeline, calibration comparison, verified explanations, fairness audit with uncertainty, constrained counterfactuals, workflow, audit and deployment. Say so plainly.

**O2. "Why should I trust a model trained on synthetic data?"**
You should not, and the product says so. The synthetic track exists to exercise the workflow and engineering. The public-data model is the only one with real labels, and it is scoped to 2005 Taiwan credit-card clients.

**O3. "What if the model is wrong for a group?"**
That is what the audit surfaces: group-level false-positive rates with intervals and small-group warnings. The response would be investigation, not an automatic fix: data checks, feature review, policy decisions, possibly retraining.

**O4. "Why is the reviewer allowed to override the policy?"**
Policies encode averages; humans see context. But overrides require a written reason, are flagged in the record and audit trail, and feed the override-rate metric so patterns can be reviewed.

**O5. "Isn't storing transaction descriptions a privacy risk?"**
Yes. They are stored in plain text in the database, shown only to the owner and the assigned reviewer, deleted with the application, and never logged. I list the lack of encryption at rest and retention automation as limitations.

**O6. "Your policy thresholds look arbitrary."**
They are, by design: experimental demonstration values (20% probability, 50% EMI-to-income) that are configurable per request and explicitly not a validated lending policy. A real policy needs credit-risk ownership and outcome data.

**O7. "The counterfactual weights look arbitrary too."**
Yes: 1.0 / 0.5 / 2.0 are design choices to prefer small loan cuts and penalise hypothetical debt reduction. They are documented and the search is bounded; I would calibrate them with user research.

**O8. "How do you know the explanation isn't misleading?"**
It is verified to add up to the model score, labelled as an association not a cause, and shown with the correlated-feature caveat. It can still mislead if read as causal, which is why the wording matters.

**O9. "What happens if two reviewers open the same case?"**
Only one decision can be recorded: the state moves to `final_demo_decision` and the second attempt gets 409. There is no explicit lock or assignment; a real system would add assignment and optimistic locking.

**O10. "Is it production ready?"**
No, and I can list exactly why: synthetic loan data, no real validation, no MFA/rate limiting/CSP/encryption at rest, free-tier hosting, no independent security review. It is a portfolio-grade, honestly scoped prototype.

**O11. "Walk me through what happens when I click Submit."**
Browser sends POST with the HttpOnly cookie and the CSRF header (through the Vercel proxy). FastAPI resolves the session by token hash, checks role, CSRF and Origin, loads the active model (checksum verified), moves the state `draft -> submitted -> validation`, scores and explains, stores assessment + snapshot + explanation, moves to `assessed -> manual_review`, writes audit events and commits once.

**O12. "Show me a design decision you would defend and one you would change."**
Defend: separating model output, policy and human decision into different records. Change: put pagination and eager loading in the list endpoints, and add rate limiting before anything else.

---

## P. Pitches and reference sheet

### P1. Three pitches
- **10 seconds:** "An explainable, calibrated, fairness-audited credit-risk platform with human review and a tamper-evident audit trail, built end to end."
- **60 seconds:** use A1, then add "the part I am proudest of is that explanations are verified to add up to the model score, and that the project states its limits instead of overclaiming."
- **3 minutes:** the demo script (`DEMO_SCRIPT.md`), then limits and next steps.

### P2. Questions to ask the interviewer
How do you validate and monitor models once outcomes arrive? Who owns policy thresholds: risk or engineering? How do reviewers and models interact today? What is your deployment and rollback process for models? How do you test for fairness regressions?

### P3. Numbers you should know cold
| Item | Value |
|---|---|
| UCI dataset | 30,000 clients, 23 features, 22.12% default, 2005 Taiwan, CC BY 4.0 |
| Splits | 55% train / 15% calibration / 15% validation / 15% test |
| UCI test result (selected: boosting + sigmoid) | ROC-AUC 0.782, average precision 0.563, Brier 0.134, log loss 0.427 |
| Baseline | constant predictor Brier 0.172, log loss 0.528 |
| Other models | Random Forest AUC 0.781; Logistic Regression 0.742 |
| Calibration | predicted 0.704 vs observed 0.702 (top bin); ECE 0.0066 |
| No-history experiment | AUC 0.593, Brier 0.1693 vs 0.1722 baseline; last month only 0.765 |
| Fairness (sex) | flagged about 27% vs 22%; FPR about 17% vs 13%; mitigation 0.043 to 0.038 |
| Threshold used for audit | 0.28 (max F1 on validation); min group 100, min class 30 |
| Policy | probability at most 20% and total EMI-to-income at most 50% |
| Auth | Argon2id; 8 h sessions; 5 failures -> 15 min lock; password 10+ characters |
| API | 44 routes, 13 tables, 6 states plus info_requested |
| Tests | 210 backend + 86 frontend = 296 |
| Performance | start about 3 s; about 236 MB peak in a full flow |
| Stack versions | Python 3.12; FastAPI 0.162; scikit-learn 1.9; SHAP 0.54; Fairlearn 0.15; SQLAlchemy 2.1; Next.js 16; React 19 |

### P4. Seven-day study plan
Day 1: pitch, structure, tech-stack table. Day 2: credit-risk and metrics (B, C). Day 3: calibration and SHAP (D, E). Day 4: fairness and leakage (F, G). Day 5: auth, cookies, CSRF, CORS (I) while tracing the code in `deps.py` and `routes_auth.py`. Day 6: database, workflow, audit (J) plus frontend (K). Day 7: deployment, tricky questions (M, O); record yourself doing the 3-minute demo.

### P5. If you only have one hour
Read the pitch and "what makes it distinctive" (guide sections 1 and 3), the limitations (guide section 9.4 and `docs/security_and_workflow.md`), sections I4-I7 here, and the numbers table above.
