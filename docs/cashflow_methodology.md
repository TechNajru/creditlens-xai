# Cash-flow methodology (Stage 2)

Cash-flow outputs are **descriptive analytics only**. They are not inputs to the risk model: no labelled
dataset links transaction behaviour to repayment outcomes, so using them for risk would be unvalidated.
Every API response carries `"used_for_risk_model": false`.

## Ingestion rules
- CSV only (.csv, UTF-8). Limits: 2 MB and 5,000 rows (env: `CREDITLENS_MAX_UPLOAD_BYTES`, `CREDITLENS_MAX_UPLOAD_ROWS`).
- Required: date, description, and either `amount` (+ direction, or signed) or separate `debit`/`credit` columns.
- Common bank headers are auto-detected (Narration, Withdrawal, Deposit, ...). Override with a `mapping` JSON.
- Dates: the single format that parses most rows is used (day-first preferred: `dd/mm/yyyy`, never guessed as `mm/dd`).
- Amounts accept `₹`, `Rs.`, commas, `(500)`, `-500`, and `Cr`/`Dr` suffixes. Zero or non-numeric amounts are invalid.
- Invalid rows are excluded and reported by data-row number + field + reason (never the raw text).
- Duplicates: same `transaction_id`, or identical date/description/amount/direction/account. They are excluded and
  reported as warnings. (Genuine identical purchases can be flagged; review the warning list.)

## Categories
Order of precedence: user correction > supplied category > keyword rule > default. Each transaction carries
`category_source` and `confidence` (high / medium / low). Keyword rules are guesses, and the UI must show that.

## Income tiers (never merged)
| Tier | Meaning |
|---|---|
| confirmed | income category supplied in the CSV or set by the user |
| likely | keyword-guessed salary (e.g. "salary", "payroll") |
| unverified | UPI inflows and uncategorized credits — never counted as income |

Internal transfers ("own account", "self transfer", ...) are excluded from income and spending.
Refunds are tracked separately (they count as inflow, not income).

## Months, coverage, unknown vs zero
- Metrics use **interior months only** (strictly between the first and last calendar month), since edge months may be partial.
  So at least 5 calendar months of statement are needed for 3 usable months.
- Interior months with no transactions are "gap months": unknown, excluded, and reported.
- Fewer than 3 usable months => `sufficient_for_analysis: false` and review should be requested.
- Unknown is `null`, never 0. `observed_monthly_debt_payments = 0` means none were *observed*, not "no debt".
- `observed_debt_to_income` is `null` when income is 0 (undefined).

## Essential spending (assumption)
rent, utilities, groceries, healthcare. Transport, dining/shopping and entertainment are discretionary.

## Payment timeliness
Computed only if both `due_date` and `payment_date` are supplied. Never inferred from transaction dates.

## Known limitations
Keyword rules are English/Indian-bank oriented and will miss many merchants. Recurring-income detection needs
>=3 months with a stable amount (CV < 0.25). No statement-period input yet (partial-month handling is conservative).
Upload ownership checks arrive with authentication (Stage 5): the endpoints are stateless and must not be public.
