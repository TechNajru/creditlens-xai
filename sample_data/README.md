# Sample CSVs — ALL SYNTHETIC

Fictional transactions (account `SYNTHETIC-001`), Jan–Jun 2026. Regenerate: `python -m app.sample_data` (from `backend/`).

| File | Purpose |
|---|---|
| SYNTHETIC_salaried_stable.csv | steady salary, rent, EMI, internal transfers |
| SYNTHETIC_gig_variable.csv | variable UPI inflows, no salary (shows "unverified" inflow) |
| SYNTHETIC_stressed.csv | expenses exceed income (negative months) |
| SYNTHETIC_messy_for_validation_demo.csv | bad date, bad amount, missing description, duplicate, unknown category |

Columns: date, description, amount (positive), direction (credit/debit), category (optional), transaction_id, account_id, balance.
