# CreditLens XAI — frontend

Next.js (App Router) + TypeScript + Tailwind + Recharts. Talks to the FastAPI backend in `../backend`.

## Run (Windows PowerShell), from this folder
```powershell
copy .env.example .env.local      # API address; default http://localhost:8000
npm install
npm run dev                        # http://localhost:3000
```
Start the backend first (see the root README). **Open the app at `http://localhost:3000` and keep the API on `localhost` too**:
the session cookie is `SameSite=Lax`, so `127.0.0.1` and `localhost` count as different sites and login would not stick.

## Checks
```powershell
npm run typecheck
npm run lint
npm test          # 86 component/unit tests (Vitest + Testing Library)
npm run build
```

## Pages
Public: `/` `/login` `/register`. Applicant: `/dashboard` `/applications/new` `/applications/[id]` plus the tools (`/assess`, `/assess-public`, `/scenarios`, `/cashflow`, `/models`).
Reviewer: `/review` `/review/[id]` (and `/models`, `/fairness`). Admin: `/admin`.
Route guards in the UI are a convenience; the API enforces every permission. The CSRF token is held in memory only.
