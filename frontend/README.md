# CreditLens XAI — frontend

Next.js (App Router) + TypeScript + Tailwind + Recharts. Talks to the FastAPI backend in `../backend`.

## Run (Windows PowerShell), from this folder
```powershell
copy .env.example .env.local      # API address; default http://127.0.0.1:8000
npm install
npm run dev                        # http://localhost:3000
```
Start the backend first (see the root README). **Open the app at `http://localhost:3000`** — the backend only
allows that origin by default. If you use another address, set `CREDITLENS_CORS_ORIGINS` for the backend.

## Checks
```powershell
npm run typecheck
npm run lint
npm test          # 24 component/unit tests (Vitest + Testing Library)
npm run build
```

## Pages
`/` landing · `/assess` loan simulation · `/assess-public` UCI model · `/cashflow` upload + corrections + summary · `/models` evaluation dashboard.
No hard-coded predictions: results come from the API. Example buttons are labelled fictional demo inputs.
Login, history, scenarios and reviewer screens arrive in later stages.
