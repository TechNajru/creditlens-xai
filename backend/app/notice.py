"""Data-use notice shown at registration. Bump NOTICE_VERSION when the text changes."""
NOTICE_VERSION = "2026-11-v1"
NOTICE_TEXT = """CreditLens XAI is an educational prototype. It is not a bank, does not issue loans, is not a credit-bureau score and does not guarantee approval.

What you enter: loan details and, optionally, a transaction CSV. Use only fictional or properly de-identified data. Do not upload real bank statements.

What happens to it: it is stored in this application's database, scored by models trained on synthetic or public 2005 data, and shown to you and to a human reviewer (who sees a pseudonymous applicant reference, not your email). Model outputs and reviewer decisions are separate records. Reviewers record a demonstration decision only; no real lending decision is made.

Your controls: you may edit a draft, correct transaction categories, and delete an application at any time unless it is currently under review. Deleting removes the application, its uploaded transactions and its assessments. A minimal audit record (event type, time, ids; no financial content) is kept.

No external services receive your data."""
