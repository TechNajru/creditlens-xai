# Security review (Stage 6)

Scope: the code in this repository at v1.0.0. Method: automated tools, black-box tests, targeted code searches, and a manual walk through the OWASP Top 10 (2021 edition categories). This is a **self-review by the author**, not an independent audit, and it does not make the system "compliant" with anything.

## Tools run and results
| Check | Result |
|---|---|
| Bandit (static analysis of `backend/app`) | First run: 0 high, 0 medium, 3 low. All three were `assert` statements; two guarded against **data leakage** (target / sensitive columns in the features) and would silently disappear under `python -O`. **Fixed**: now explicit `ValueError`s. Re-run: 0 issues. |
| pip-audit (86 installed Python packages) | No project dependency has a known vulnerability. Only `pip` itself (the installer, in the test sandbox) was flagged. |
| npm audit (production dependencies) | 0 vulnerabilities. |
| Black-box sweep of **every route** (`tests/test_security.py`) | All 44 API routes refuse anonymous callers (except health, consent notice, register, login). Every `/admin`, `/reviews`, `/applications` route returns 403 to the wrong roles. Now a permanent regression test: a new endpoint added without a guard fails the build. |
| Code search: XSS sinks (`dangerouslySetInnerHTML`, `innerHTML`, `eval`) | None in the frontend source. React escapes all rendered text (including transaction descriptions). |
| Code search: raw SQL / shell / eval | None. All database access is through SQLAlchemy (parameterised). |
| Code search: hard-coded secrets, committed `.env`/`.db`/`.joblib`/dataset | None found; `.gitignore` excludes them. |
| Real database | The database suites (migrations, auth, workflow, reviews, admin, audit, end-to-end) pass on **PostgreSQL 16.2** as well as SQLite. |

## Findings and fixes during the review
1. **Safety checks used `assert`** (see above): fixed.
2. **Evaluation endpoint deserialised a model pickle on every request** just to read a list of limitations: wasteful and extra attack surface. Fixed: limitations are stored in the report JSON at training time; the endpoint no longer loads the model (regression test added).
3. **Cross-site cookie trap in deployment** (site and API on different domains): fixed with the same-origin `/api` proxy, and the localhost default now uses `localhost` for both ends. Tested in a real browser.
4. **Production bootstrap** no longer prints passwords: `python -m app.admin bootstrap` reads the first admin from environment variables.

## OWASP Top 10 (2021 categories) walk-through
| Category | What exists | Residual risk |
|---|---|---|
| A01 Broken access control | Server-side role guards on every route; ownership checks return 404; reviewers cannot see drafts or review their own cases; admins cannot read applications; black-box sweeps | Roles are coarse (three) |
| A02 Cryptographic failures | Argon2id; session tokens stored as SHA-256; `Secure` cookies when HTTPS flag set | No encryption at rest; transaction text stored in plain text in the database |
| A03 Injection | ORM only; Pydantic validation; React escaping | CSV formula injection is possible only if someone later adds a CSV *export* and opens it in a spreadsheet |
| A04 Insecure design | Model / policy / human separation; state machine; consent; deletion; pseudonymous reviewer view | Demonstration thresholds are unvalidated by design |
| A05 Security misconfiguration | Explicit CORS allow-list, security headers on API and site, no debug mode, secrets via environment | No Content-Security-Policy |
| A06 Vulnerable components | Exact version pins, audits, Dependabot, CI security job | Very new major versions of several libraries (less battle-tested) |
| A07 Authentication failures | Lockout, generic errors, timing-equalised unknown-user path, session rotation, expiry, revocation | No MFA, no password reset, per-account lockout allows a deliberate lock-out of a victim, no IP rate limiting |
| A08 Integrity failures | Model artifact SHA-256 checked before loading; tamper-evident audit chain; CI | Model files are pickles: register only files you trained |
| A09 Logging and monitoring | Audit trail (ids and enums only), monitoring summary | No alerting or log shipping |
| A10 SSRF | The server never fetches user-supplied URLs | Not applicable |

## How to repeat the review
```powershell
cd backend
pip install bandit pip-audit
bandit -r app
pip-audit
python -m pytest tests/test_security.py -q
cd ..\frontend ; npm audit --omit=dev
```
