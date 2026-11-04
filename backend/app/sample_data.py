"""Fictional transaction CSVs (Track B). Run from backend/:  python -m app.sample_data

Every row is invented; account_id is always SYNTHETIC-001. They exist to test upload, validation,
categorization and cash-flow analytics, and say nothing about real borrowers.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import config

MONTHS = [(2026, m) for m in range(1, 7)]  # Jan-Jun 2026


def _persona_rows(persona: str, rng: np.random.Generator) -> list[tuple]:
    rows = []  # (date, description, amount, direction)
    for y, m in MONTHS:
        d = lambda day: date(y, m, day)
        if persona == "salaried_stable":
            rows += [(d(1), "SALARY CREDIT ACME PVT LTD", 60000, "credit"),
                     (d(5), "RENT PAYMENT TO LANDLORD", 15000, "debit"),
                     (d(7), "HOME LOAN EMI", 6000, "debit"),
                     (d(9), "ELECTRICITY BILL BSES", int(rng.integers(1500, 2200)), "debit"),
                     (d(10), "AIRTEL BROADBAND BILL", 999, "debit"),
                     (d(12), "TRANSFER TO OWN SAVINGS ACCOUNT", 5000, "debit"),
                     (d(13), "TRANSFER FROM OWN SAVINGS ACCOUNT", 5000, "credit"),
                     (d(20), "UPI-FRIEND SHARED DINNER REFUND", 600, "credit")]
            rows += [(d(int(x)), "UPI-BIGBASKET GROCERY", int(rng.integers(700, 1600)), "debit")
                     for x in (3, 11, 18, 26)]
            rows += [(d(int(x)), "UPI-ZOMATO FOOD", int(rng.integers(250, 700)), "debit") for x in (6, 15, 24)]
            rows += [(d(22), "UPI-MERCHANT 4521", int(rng.integers(300, 900)), "debit")]
        elif persona == "gig_variable":
            rows += [(d(9), "RENT PAYMENT", 9000, "debit"), (d(8), "BAJAJ FINANCE EMI", 3000, "debit"),
                     (d(14), "ELECTRICITY BILL", 1100, "debit")]
            rows += [(d(int(x)), "UPI-CUSTOMER PAYMENT", int(rng.integers(2500, 6500)), "credit")
                     for x in rng.choice(np.arange(1, 28), size=int(rng.integers(4, 9)), replace=False)]
            rows += [(d(int(x)), "FUEL PETROL PUMP", int(rng.integers(400, 900)), "debit") for x in (4, 12, 20)]
            rows += [(d(int(x)), "UPI-GROCERY STORE", int(rng.integers(500, 1200)), "debit") for x in (7, 19)]
        elif persona == "stressed":
            rows += [(d(1), "SALARY CREDIT NOVA SERVICES", 35000, "credit"),
                     (d(4), "RENT PAYMENT", 12000, "debit"), (d(6), "PERSONAL LOAN EMI", 14000, "debit"),
                     (d(8), "CREDIT CARD BILL PAYMENT", 6000, "debit"),
                     (d(10), "ELECTRICITY BILL", 1400, "debit")]
            rows += [(d(int(x)), "UPI-SWIGGY FOOD", int(rng.integers(400, 1100)), "debit") for x in (2, 9, 14, 21, 27)]
            rows += [(d(int(x)), "UPI-SHOPPING AMAZON", int(rng.integers(800, 3500)), "debit") for x in (11, 23)]
            rows += [(d(17), "UPI-GROCERY", int(rng.integers(900, 1800)), "debit")]
    return rows


def generate_persona(persona: str, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = sorted(_persona_rows(persona, rng), key=lambda r: r[0])
    bal, out = 20000.0, []
    for i, (dt, desc, amt, direction) in enumerate(rows, 1):
        bal += amt if direction == "credit" else -amt
        out.append({"date": dt.isoformat(), "description": desc, "amount": amt, "direction": direction,
                    "category": "", "transaction_id": f"SYN-{persona[:3].upper()}-{i:04d}",
                    "account_id": "SYNTHETIC-001", "balance": round(bal, 2)})
    return pd.DataFrame(out)


MESSY_CSV = """date,description,amount,direction,category,transaction_id,account_id
2026-01-01,SALARY CREDIT ACME PVT LTD,60000,credit,,M-1,SYNTHETIC-001
2026-01-05,RENT PAYMENT,15000,debit,,M-2,SYNTHETIC-001
2026-01-05,RENT PAYMENT,15000,debit,,M-2,SYNTHETIC-001
31/02/2026,IMPOSSIBLE DATE ROW,500,debit,,M-4,SYNTHETIC-001
2026-01-09,BAD AMOUNT ROW,abc,debit,,M-5,SYNTHETIC-001
2026-01-10,,750,debit,,M-6,SYNTHETIC-001
2026-01-12,UNKNOWN CATEGORY ROW,900,debit,foo,M-7,SYNTHETIC-001
2026-01-15,UPI-SOMEONE,2000,credit,,M-8,SYNTHETIC-001
2026-01-20,SIDE GIG PAYOUT,5000,credit,income_other,M-9,SYNTHETIC-001
"""


def write_samples() -> None:
    out = config.BASE_DIR.parent / "sample_data"
    out.mkdir(exist_ok=True)
    for p in ("salaried_stable", "gig_variable", "stressed"):
        generate_persona(p).to_csv(out / f"SYNTHETIC_{p}.csv", index=False)
    (out / "SYNTHETIC_messy_for_validation_demo.csv").write_text(MESSY_CSV)
    print("Wrote sample CSVs to", out)


if __name__ == "__main__":
    write_samples()
