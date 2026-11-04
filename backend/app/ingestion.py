"""CSV ingestion: validation, column mapping, parsing, duplicate + invalid-row reporting.

Nothing here infers meaning from descriptions (that is categorizer.py). Invalid rows are
reported by data-row number and reason only, so error reports never echo raw descriptions.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pandas as pd

from . import config

CANONICAL_FIELDS = ["date", "description", "amount", "direction", "category", "transaction_id",
                    "account_id", "balance", "due_date", "payment_date", "debit", "credit"]

SYNONYMS = {
    "date": ["date", "txn_date", "transaction_date", "value_date", "posting_date"],
    "description": ["description", "narration", "particulars", "details", "remarks",
                    "transaction_remarks"],
    "amount": ["amount", "txn_amount", "transaction_amount"],
    "direction": ["direction", "type", "dr_cr", "cr_dr", "transaction_type"],
    "category": ["category"],
    "transaction_id": ["transaction_id", "txn_id", "reference", "ref_no", "utr"],
    "account_id": ["account_id", "account", "account_no"],
    "balance": ["balance", "closing_balance", "running_balance"],
    "due_date": ["due_date"],
    "payment_date": ["payment_date", "paid_date"],
    "debit": ["debit", "withdrawal", "withdrawal_amt", "debit_amount"],
    "credit": ["credit", "deposit", "deposit_amt", "credit_amount"],
}

DATE_FORMATS = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d-%b-%Y", "%d/%m/%y"]
CREDIT_WORDS = {"credit", "cr", "c", "deposit", "in"}
DEBIT_WORDS = {"debit", "dr", "d", "withdrawal", "out"}
MAX_ISSUES_RETURNED = 100


class UploadError(Exception):
    """A problem with the whole file (not a single row)."""

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.message, self.status_code = message, status_code


@dataclass
class ParseResult:
    transactions: pd.DataFrame
    issues: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    mapping: dict = field(default_factory=dict)
    date_format: str | None = None


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(h).strip().lower()).strip("_")


def detect_mapping(columns: list[str], user_mapping: dict | None = None) -> dict:
    """Return {canonical_field: actual_column_name}. User mapping wins over auto-detection."""
    user_mapping = user_mapping or {}
    bad = [k for k in user_mapping if k not in CANONICAL_FIELDS]
    if bad:
        raise UploadError(f"Unknown mapping fields: {bad}")
    for target, col in user_mapping.items():
        if col not in columns:
            raise UploadError(f"Mapped column '{col}' for '{target}' is not in the file")
    by_norm = {_norm_header(c): c for c in columns}
    mapping = dict(user_mapping)
    for target, names in SYNONYMS.items():
        if target in mapping:
            continue
        for n in names:
            if n in by_norm:
                mapping[target] = by_norm[n]
                break
    missing = [f for f in ("date", "description") if f not in mapping]
    if "amount" not in mapping and "debit" not in mapping and "credit" not in mapping:
        missing.append("amount (or debit/credit columns)")
    if missing:
        raise UploadError(f"Missing required columns: {missing}. Use the mapping option to point "
                          f"to the right columns. Found columns: {list(columns)}")
    return mapping


def decode_upload(data: bytes, filename: str | None) -> str:
    if not filename or not filename.lower().endswith(".csv"):
        raise UploadError("Only .csv files are accepted", 415)
    if len(data) > config.max_upload_bytes():
        raise UploadError(f"File too large (limit {config.max_upload_bytes()} bytes)", 413)
    if b"\x00" in data:
        raise UploadError("File does not look like a text CSV", 422)
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UploadError("File must be UTF-8 encoded text", 422) from exc


def parse_amount(value) -> tuple[float | None, str | None]:
    """'₹1,234.50', '(500)', '-200', '1,000.00 Cr' -> (signed value, 'credit'/'debit'/None)."""
    s = str(value).strip()
    if not s:
        return None, None
    hint = None
    m = re.search(r"(?i)\b(cr|dr)\.?\s*$", s)
    if m:
        hint = "credit" if m.group(1).lower() == "cr" else "debit"
        s = s[:m.start()].strip()
    negative = (s.startswith("(") and s.endswith(")")) or s.startswith("-")
    s = re.sub(r"(?i)(rs\.?|inr|₹)", "", s)
    cleaned = re.sub(r"[^\d.]", "", s)
    if cleaned in ("", ".") or cleaned.count(".") > 1:
        return None, None
    v = float(cleaned)
    return (-v if negative else v), hint


def parse_dates(series: pd.Series) -> tuple[pd.Series, str | None]:
    """Pick the single format that parses the most rows (dd/mm preferred over mm/dd by design)."""
    best, best_fmt, best_n = None, None, 0
    for fmt in DATE_FORMATS:
        parsed = pd.to_datetime(series.str.strip(), format=fmt, errors="coerce")
        n = int(parsed.notna().sum())
        if n > best_n:
            best, best_fmt, best_n = parsed, fmt, n
    if best is None:
        return pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]"), None
    return best, best_fmt


def _clean_optional(series: pd.Series, lower: bool = False) -> pd.Series:
    """Empty/blank strings -> None (never NaN, which is truthy and breaks equality checks)."""
    def f(v):
        v = str(v).strip()
        v = v.lower() if lower else v
        return v if v else None
    return pd.Series([f(v) for v in series], index=series.index, dtype=object)


def _direction_from_text(v: str) -> str | None:
    t = str(v).strip().lower()
    return "credit" if t in CREDIT_WORDS else "debit" if t in DEBIT_WORDS else None


def parse_csv(data: bytes, filename: str | None, user_mapping: dict | None = None) -> ParseResult:
    text = decode_upload(data, filename)
    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, skipinitialspace=True)
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise UploadError("Could not read the file as CSV", 422) from exc
    if len(df) == 0:
        raise UploadError("The CSV has no data rows", 422)
    if len(df) > config.max_upload_rows():
        raise UploadError(f"Too many rows (limit {config.max_upload_rows()})", 422)

    mapping = detect_mapping(list(df.columns), user_mapping)
    col = lambda f: df[mapping[f]] if f in mapping else pd.Series([""] * len(df), index=df.index)

    issues: list[dict] = []

    def issue(i, fld, problem, severity="error"):
        issues.append({"row": int(i) + 1, "field": fld, "problem": problem, "severity": severity})

    dates, fmt = parse_dates(col("date"))
    amounts, direction = [], []
    for i in df.index:
        direction_val = _direction_from_text(col("direction").iloc[i]) if "direction" in mapping else None
        amt, hint = (None, None)
        if "amount" in mapping:
            amt, hint = parse_amount(col("amount").iloc[i])
        if direction_val is None and "direction" not in mapping:
            direction_val = hint
        if "amount" not in mapping:  # separate debit/credit columns
            d_amt, _ = parse_amount(col("debit").iloc[i]) if "debit" in mapping else (None, None)
            c_amt, _ = parse_amount(col("credit").iloc[i]) if "credit" in mapping else (None, None)
            if d_amt and c_amt:
                amt, direction_val = None, None
            elif c_amt:
                amt, direction_val = c_amt, "credit"
            elif d_amt:
                amt, direction_val = d_amt, "debit"
        elif direction_val is None and amt is not None and "direction" not in mapping and hint is None:
            direction_val = "debit" if amt < 0 else "credit"  # signed-amount statements
        amounts.append(abs(amt) if amt is not None else None)
        direction.append(direction_val)

    out = pd.DataFrame({
        "row": df.index + 1,
        "date": dates,
        "description": col("description").str.strip(),
        "amount": amounts,
        "direction": direction,
        "category_supplied": _clean_optional(col("category"), lower=True),
        "transaction_id": _clean_optional(col("transaction_id")),
        "account_id": _clean_optional(col("account_id")),
    })
    out["balance"] = [parse_amount(v)[0] if str(v).strip() else None for v in col("balance")]
    out["due_date"] = parse_dates(col("due_date"))[0] if "due_date" in mapping else pd.NaT
    out["payment_date"] = parse_dates(col("payment_date"))[0] if "payment_date" in mapping else pd.NaT

    valid = pd.Series(True, index=out.index)
    for i in out.index:
        if pd.isna(out.at[i, "date"]):
            issue(i, "date", "unparseable or inconsistent date format"); valid[i] = False
        if not out.at[i, "description"]:
            issue(i, "description", "missing description"); valid[i] = False
        a = out.at[i, "amount"]
        if a is None or pd.isna(a) or a == 0:
            issue(i, "amount", "missing, non-numeric or zero amount"); valid[i] = False
        if out.at[i, "direction"] is None:
            issue(i, "direction", "could not determine credit/debit"); valid[i] = False

    good = out[valid].copy()
    # Duplicate detection: by transaction_id when present, otherwise by content.
    dup_mask = pd.Series(False, index=good.index)
    seen_ids, seen_content = set(), set()
    for i, r in good.iterrows():
        key = ("id", r["transaction_id"]) if r["transaction_id"] else \
              ("c", r["date"], r["description"].lower(), r["amount"], r["direction"], r["account_id"])
        seen = seen_ids if key[0] == "id" else seen_content
        if key in seen:
            dup_mask[i] = True
            issue(i, "row", "possible duplicate of an earlier row (excluded)", "warning")
        seen.add(key)
    good = good[~dup_mask].copy()
    good["key"] = [t if t else f"row-{r}" for t, r in zip(good["transaction_id"], good["row"])]
    good = good.reset_index(drop=True)

    errors = sum(1 for x in issues if x["severity"] == "error")
    stats = {
        "rows_total": int(len(df)), "rows_valid": int(len(good)),
        "rows_with_errors": int(len({x["row"] for x in issues if x["severity"] == "error"})),
        "duplicates_excluded": int(dup_mask.sum()), "issues_total": len(issues),
        "errors_total": errors,
    }
    return ParseResult(good, sorted(issues, key=lambda x: x["row"])[:MAX_ISSUES_RETURNED],
                       stats, mapping, fmt)
