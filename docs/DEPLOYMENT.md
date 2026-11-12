# Deployment guide: GitHub -> Render (API) + Vercel (website)

Verified facts (checked against the providers' current documentation when this was written; re-check pricing and limits, they change):
- **Render free web services** spin down after about 15 minutes without traffic and have an **ephemeral filesystem**: files written at runtime (including a SQLite database) are lost on restart or redeploy. So **use PostgreSQL**, not SQLite, on Render.
- **Render free PostgreSQL** expires 30 days after creation (14-day grace to upgrade), is 1 GB and has no backups. Fine for a demo; for anything lasting, upgrade or point `CREDITLENS_DATABASE_URL` at another Postgres provider.
- **Vercel Hobby** is for personal, **non-commercial** use. In a monorepo you must set the project's **Root Directory**. `NEXT_PUBLIC_*` variables are baked in at build time, so changing them needs a redeploy.

Measured on this project (Linux, Python 3.12): API start-up about 3 s; memory about 230-240 MB after a full register -> assess -> explain -> submit flow, so it fits a 512 MB instance.

## Why the website proxies `/api/*`
Session cookies are `SameSite=Lax`. Browsers treat `creditlens.vercel.app` and `creditlens-api.onrender.com` as **different sites**, so a cookie set by the API would be dropped and login would "succeed" but never stick. The fix: the Vercel site rewrites `/api/*` to the Render API (`frontend/next.config.ts`), so the browser only ever talks to one origin. This was tested end to end in a real browser (cookie, CSRF and Origin checks all pass through the proxy).

## Step 0 - Put the project on GitHub
From the repo root (PowerShell):
```powershell
git init
git add .
git status                      # check: no .env, .db, .joblib, .xls, venv or node_modules appear
git commit -m "CreditLens XAI v1.0.0"
git branch -M main
git remote add origin https://github.com/TechNajru/creditlens-xai.git     # create the EMPTY repo on github.com first
git push -u origin main
git tag v1.0.0 ; git push origin v1.0.0
```
If you already have a repo with history, skip `git init`, `git remote add`; just `git add . ; git commit ; git push`.

## Step 1 - API on Render
**Option A (recommended): Blueprint.** Render dashboard -> New -> Blueprint -> connect the GitHub repo. Render reads `render.yaml` and creates the web service and PostgreSQL database. It will ask for the three `sync: false` values:

| Variable | Value |
|---|---|
| `CREDITLENS_BOOTSTRAP_ADMIN_EMAIL` | your admin email (can be fictional, e.g. `admin@creditlens.example`) |
| `CREDITLENS_BOOTSTRAP_ADMIN_PASSWORD` | a long passphrase (10+ chars; never reused). It is read once to create the first admin; it is never printed |
| `CREDITLENS_CORS_ORIGINS` | leave a placeholder now; set to your Vercel URL in Step 3 |

**Option B: manual.** New -> PostgreSQL (note the *Internal Database URL*). New -> Web Service -> repo, Runtime Python, Region same as DB, then:
- Build command: `pip install -r backend/requirements.txt && cd backend && python -m app.train`
- Start command: `cd backend && python -m app.admin bootstrap && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/health`
- Environment: `PYTHON_VERSION=3.12.8`, `CREDITLENS_DATABASE_URL=<internal database URL>`, `CREDITLENS_COOKIE_SECURE=true`, plus the three variables above.

What happens: the build installs the pinned packages and trains the simulation model from source (about 10 s). Each start runs `bootstrap`, which is idempotent: it applies migrations, registers and activates the model version, and creates the first admin only if none exists. Logs should end with `bootstrap complete`.

Check: open `https://<your-api>.onrender.com/health` -> `{"status":"ok"}`. (The first request after a sleep can take a minute.)

Not deployed by design: the UCI **public-data** model, fairness report and experiments need the dataset, which is not in the repository. Those pages show a "not generated yet" message. To enable them you would train locally and host the artifacts yourself (see Future work); for a portfolio demo the simulation workflow is the complete product.

## Step 2 - Website on Vercel
Vercel -> Add New -> Project -> import the repo, then:
- **Root Directory:** `frontend`
- Framework preset: Next.js (auto-detected)
- **Environment variables** (set before the first build):

| Variable | Value | Why |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `/` | calls become same-origin (`/api/...`) |
| `BACKEND_URL` | `https://<your-api>.onrender.com` (no trailing slash) | where `/api/*` is proxied |

Deploy. Note the URL, for example `https://creditlens-xai.vercel.app`.

## Step 3 - Tell the API which origin to trust
Render -> your web service -> Environment -> set `CREDITLENS_CORS_ORIGINS` to the **exact** Vercel origin (`https://creditlens-xai.vercel.app`, https, no trailing slash, no path). Save; Render redeploys. For two origins (a custom domain too) separate them with a comma. Wildcards are not supported on purpose: the origin check is a CSRF defence.

## Step 4 - Verify (do this in a private window)
1. `https://<site>/api/v1/consent/notice` returns JSON (proves the proxy works).
2. Register, create an application, upload `sample_data/SYNTHETIC_salaried_stable.csv`, preview, submit.
3. Log in as the admin you bootstrapped -> Admin -> Users -> create a reviewer account -> log in as reviewer -> decide.
4. Admin -> Audit -> "Verify audit chain".

## Troubleshooting
| Symptom | Likely cause | Fix |
|---|---|---|
| Login "works" but you are logged out on the next page | Site and API on different origins (no proxy), or `NEXT_PUBLIC_API_URL` not `/` at build time | Set it to `/`, **redeploy** (it is build-time) |
| `403 Origin not allowed` on every POST | `CREDITLENS_CORS_ORIGINS` does not exactly match the site origin | Fix it (https, no trailing slash); preview URLs differ per deployment |
| `403 Missing or invalid CSRF token` | Stale page after the session was replaced | Reload; log in again |
| `404` on `/api/...` at the Vercel URL | `BACKEND_URL` missing when the site was built | Set it and redeploy |
| `502`/`504` or very slow first request | Render free instance was asleep (cold start) | Wait about a minute, refresh |
| `503 No active 'simulation' model version` | Build did not train, or bootstrap failed | Check Render build/start logs for `python -m app.train` and `bootstrap complete` |
| Data vanished | SQLite on Render's ephemeral disk, or the free database expired | Use PostgreSQL; upgrade or migrate before day 30 |
| Build fails installing numba/llvmlite/scikit-learn | Python version not pinned | Keep `PYTHON_VERSION=3.12.8` (and `.python-version`) |
| Cannot log in as admin | `CREDITLENS_BOOTSTRAP_ADMIN_*` unset, or password too weak | Set them (10+ char passphrase) and restart; log shows the reason |

## Alternative: both on Render
You can run the Next.js app as a second Render web service (`npm ci && npm run build`, start `npm start`, root `frontend`) with the same two variables. Keep the `/api` proxy so cookies stay first-party. (Not tested by the author; Vercel is the tested path.)

## Production hardening before real use (not done)
Custom domain with HTTPS, MFA and password reset, IP rate limiting, Content-Security-Policy, encryption at rest, managed backups, log shipping and alerting, a security review by someone else. See `docs/security_and_workflow.md`.
