"""Loader for the UCI "Default of Credit Card Clients" file (Yeh, 2009; CC BY 4.0).

Accepts the official .xls (extra 'X1..X23' row above the real header) or a CSV export.
Looks in backend/data/ (or CREDITLENS_DATA_DIR) unless a path is given.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config
from .public_features import AUDIT_COLUMNS, PUBLIC_TARGET, RAW_PUBLIC

SOURCE = {
    "name": "Default of Credit Card Clients",
    "creator": "I-Cheng Yeh (2009)",
    "url": "https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients",
    "doi": "https://doi.org/10.24432/C55S3H",
    "licence": "CC BY 4.0 (attribution required)",
    "population": "Credit-card clients in Taiwan, April-September 2005; amounts in NT dollars",
    "label": "default payment next month (1 = yes, 0 = no); one-month horizon",
}
TARGET_NAMES = ["default payment next month", "default.payment.next.month", "default_payment_next_month"]


class DatasetNotFoundError(FileNotFoundError):
    pass


def find_dataset(path: str | Path | None = None) -> Path:
    if path:
        p = Path(path)
        if not p.exists():
            raise DatasetNotFoundError(f"Dataset file not found: {p}")
        return p
    d = config.data_dir()
    for pattern in ("default*credit*card*.xls*", "default*credit*card*.csv", "UCI_Credit_Card.csv"):
        hits = sorted(d.glob(pattern))
        if hits:
            return hits[0]
    raise DatasetNotFoundError(
        f"No UCI credit-card dataset found in {d}. Download it from {SOURCE['url']} and put the "
        f".xls (or a CSV export) in that folder.")


def _read(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in (".xls", ".xlsx"):
        engine = "xlrd" if path.suffix.lower() == ".xls" else None
        probe = pd.read_excel(path, header=None, nrows=3, engine=engine)
        header = 1 if "ID" not in set(probe.iloc[0].astype(str)) else 0
        return pd.read_excel(path, header=header, engine=engine)
    probe = pd.read_csv(path, header=None, nrows=3, dtype=str)
    header = 1 if "ID" not in set(probe.iloc[0].astype(str)) else 0
    return pd.read_csv(path, header=header)


def load_public_dataset(path: str | Path | None = None):
    """Returns (raw_features, y, audit, meta). Raises a clear error if columns are missing."""
    path = find_dataset(path)
    df = _read(path)
    df.columns = [str(c).strip() for c in df.columns]
    target = next((c for c in TARGET_NAMES if c in df.columns), None)
    if target is None:
        raise ValueError(f"Target column not found. Expected one of {TARGET_NAMES}. Found: {list(df.columns)}")
    missing = [c for c in RAW_PUBLIC + AUDIT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Dataset is missing expected columns: {missing}")
    y = df[target].astype(int).rename(PUBLIC_TARGET)
    if set(y.unique()) - {0, 1}:
        raise ValueError("Target must contain only 0/1")
    meta = {**SOURCE, "file": path.name, "rows": int(len(df)),
            "positive_rate": float(y.mean()),
            "duplicate_rows_excluding_id": int(df.drop(columns=[c for c in ("ID",) if c in df]).duplicated().sum())}
    return (df[RAW_PUBLIC].reset_index(drop=True), y.reset_index(drop=True),
            df[AUDIT_COLUMNS].reset_index(drop=True), meta)
