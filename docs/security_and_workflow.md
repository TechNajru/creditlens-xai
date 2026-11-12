# Accounts, roles, workflow and security (Stage 5)

## Roles
| Role | Can | Cannot |
|---|---|---|
| applicant (public registration) | create/edit drafts, upload CSV, correct categories, preview, submit, view own history and outcome, delete own application (unless in review) | see anyone else's data, use reviewer/admin features |
| reviewer (created by an admin) | see submitted applications (pseudonymous applicant reference, no email), inspect quality/cash flow/model output/full explanation, request information, record a demonstration decision (override needs a written reason), see audit history | create applications, review their own application, change data |
| admin | manage users, register/activate model versions, view monitoring and the audit trail | read application contents (by design) |

Reviewer and admin accounts can only be created by an administrator (`python -m app.admin init` creates two demo accounts; the passwords are printed once).

## Application states
`draft -> submitted -> validation -> assessed -> manual_review -> final_demo_decision`; validation failure returns to `draft`;
a reviewer can move `manual_review -> info_requested`, after which the applicant answers, edits and resubmits.
Every transition goes through one function and is written to the audit trail. In this demonstration **every** submission goes to a human
(the reasons it was flagged - unknown credit history, no/insufficient cash-flow data, policy rules not met - are recorded for the reviewer).

Model output and human decisions are separate tables (`assessments` vs `review_decisions`). A decision records the policy recommendation,
whether it was an override, and the override reason. Each assessment stores the input snapshot, the feature values, the model version (with a
checksum-verified artifact), feature-schema version, policy version, the explanation, and a descriptive cash-flow summary (never a model input).

## Security controls that exist
- Passwords: Argon2id; length-based policy with a deny-list; generic login errors; per-account lockout after repeated failures.
- Sessions: random 256-bit token in an **HttpOnly, SameSite=Lax** cookie (`Secure` when `CREDITLENS_COOKIE_SECURE=true`); only its SHA-256 is stored; new session on every login; expiry; logout and role/activation changes revoke sessions.
- CSRF: per-session token sent in an `X-CSRF-Token` header on every POST/PATCH/DELETE, plus an `Origin` check. The token is kept in memory in the browser, never in localStorage.
- CORS: only the configured origin, with credentials. Security headers on API responses (`nosniff`, `no-store`, `no-referrer`) and on the website (frame denial, nosniff, referrer and permissions policy).
- Authorization is enforced on the server for every endpoint (the UI guards are only convenience). Other people's applications return 404, not 403.
- Earlier-stage endpoints (predictions, scenarios, uploads, evaluation) now require login; the fairness report is reviewer/admin only.
- Privacy: consent notice recorded at registration; reviewers see pseudonymous references; the audit trail stores ids and enum values only (never transaction text, emails or passwords); deleting an application removes its uploaded transactions, assessments and decisions.
- Integrity: hash-chained audit events (tamper-evident), model artifact checksums, foreign keys enforced on SQLite, database check constraint on roles.

## What does NOT exist (be honest in interviews)
- No password reset, email verification, MFA, or "change password" screen.
- Lockout is per account only; there is no IP rate limiting or CAPTCHA, and the 409 on duplicate registration reveals that an email exists.
- No Content-Security-Policy yet (needs nonce setup for Next.js inline scripts).
- The cookie model needs the website and API on the **same site** (here: both on `localhost`). A real deployment needs HTTPS, `Secure` cookies and a shared registrable domain or a reverse proxy.
- Uploaded transaction text is stored unencrypted in the database. There is no encryption at rest, no automated retention job, and no user-deletion endpoint.
- The audit chain is tamper-EVIDENT, not tamper-proof (someone with full database access could rewrite it), and concurrent writers could fork it; it is designed for a single-writer SQLite demo.
- Scenarios (what-if) are not persisted. Model files are pickles: register only files you trained yourself.
- No external security review has been done. This is not a "compliant" system.
