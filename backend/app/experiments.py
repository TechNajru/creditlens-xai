"""LIMITED-INFORMATION experiments on the UCI data (NOT validated thin-file lending).

Question: how much does performance fall when the model sees less payment history?
Every client in this dataset has 6 months of history, so no genuine thin-file subset exists. We therefore
hide months from clients who DO have them. Real thin-file applicants differ in unobserved ways, so these
results are only an indication of how much the model relies on history length.

Protocol: same splits as the main public model; one fixed recipe per variant (HistGradientBoosting +
sigmoid calibration fitted on the calibration split); NO selection among variants; test metrics with
bootstrap 95% intervals. Run from backend/:  python -m app.experiments
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from . import config
from .calibration import SigmoidCalibrator
from .public_data import load_public_dataset
from .public_features import BILL_COLS, PAY_COLS, PAYAMT_COLS, validate_public_raw
from .public_train import split_indices

VARIANTS = [(6, "Full history (6 months)"), (3, "Last 3 months only"), (2, "Last 2 months only"),
            (1, "Last month only"), (0, "No payment history (limit + age only)")]
N_BOOT = 200
LABEL = ("LIMITED-INFORMATION EXPERIMENT. Months are hidden from clients who actually have 6 months of history. "
         "This is not a validated thin-file evaluation.")


def limited_features(raw: pd.DataFrame, k: int) -> pd.DataFrame:
    """Features using only the most recent k months (month 1 = most recent). k=0 keeps limit and age only."""
    validate_public_raw(raw)
    x = raw[["LIMIT_BAL", "AGE"]].astype(float).copy()
    if k == 0:
        return x.reset_index(drop=True)
    pay, bill, amt = PAY_COLS[:k], BILL_COLS[:k], PAYAMT_COLS[:k]
    x = pd.concat([x, raw[pay + bill + amt].astype(float)], axis=1)
    x["utilization_latest"] = x["BILL_AMT1"] / x["LIMIT_BAL"]
    x["months_delayed"] = (x[pay] >= 1).sum(axis=1).astype(float)          # only the visible months
    ratio = np.full(len(x), np.nan)
    pos = x["BILL_AMT1"].to_numpy() > 0
    ratio[pos] = x["PAY_AMT1"].to_numpy()[pos] / x["BILL_AMT1"].to_numpy()[pos]
    x["payment_ratio_latest"] = ratio
    return x.reset_index(drop=True)


def ece(y, p, bins: int = 10) -> float:
    """Expected calibration error with equal-count bins (lower is better)."""
    order = np.argsort(p)
    total = 0.0
    for chunk in np.array_split(order, bins):
        if len(chunk):
            total += len(chunk) / len(p) * abs(p[chunk].mean() - y[chunk].mean())
    return float(total)


def bootstrap_auc(y, p, seed: int, n: int = N_BOOT) -> list[float]:
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        idx = rng.integers(0, len(y), len(y))
        if y[idx].min() == y[idx].max():
            continue
        vals.append(roc_auc_score(y[idx], p[idx]))
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def run_experiments(reports_dir: Path | None = None, data=None, data_path=None, seed: int | None = None) -> dict:
    seed = config.default_seed() if seed is None else seed
    reports_dir = Path(reports_dir or config.reports_dir())
    reports_dir.mkdir(parents=True, exist_ok=True)
    raw, y_s, _, meta = data if data is not None else load_public_dataset(data_path)
    y = y_s.to_numpy()
    sp = split_indices(y, seed)
    base_rate = float(np.mean(y[sp["train"]]))
    out, full_auc = [], None
    for k, label in VARIANTS:
        X = limited_features(raw, k)
        tr, ca, te = X.iloc[sp["train"]], X.iloc[sp["calibration"]], X.iloc[sp["test"]]
        model = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
                                               random_state=seed).fit(tr, y[sp["train"]])
        cal = SigmoidCalibrator().fit(model.predict_proba(ca)[:, 1], y[sp["calibration"]])
        p = np.clip(cal.transform(model.predict_proba(te)[:, 1]), 1e-6, 1 - 1e-6)
        yt = y[sp["test"]]
        auc = float(roc_auc_score(yt, p))
        full_auc = auc if full_auc is None else full_auc
        out.append({"months_visible": k, "label": label, "n_features": int(X.shape[1]), "features": list(X.columns),
                    "roc_auc": auc, "roc_auc_ci95": bootstrap_auc(yt, p, seed),
                    "brier": float(brier_score_loss(yt, p)), "log_loss": float(log_loss(yt, p)),
                    "ece": ece(yt, p), "roc_auc_change_vs_full": auc - full_auc})
    report = {
        "label": LABEL, "data_provenance": f"PUBLIC data: UCI {meta.get('name', 'Default of Credit Card Clients')}",
        "evaluated_on": "untouched test split", "n_test": int(len(sp["test"])), "seed": seed,
        "recipe": "HistGradientBoosting (fixed) + sigmoid calibration; no selection among variants",
        "baseline_constant_brier": float(brier_score_loss(y[sp["test"]], np.full(len(sp["test"]), base_rate))),
        "variants": out,
        "caveats": [
            "Clients with 6 months of history were artificially limited; real thin-file applicants differ in unobserved ways.",
            "Intervals are bootstrap 95% over the test split only; they ignore training-split randomness.",
            "A drop in ROC-AUC shows reliance on history, not how a thin-file product would perform.",
            "Not used to approve, deny or price anything.",
        ],
    }
    (reports_dir / "experiments_public.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    r = run_experiments()
    print(r["label"])
    for v in r["variants"]:
        lo, hi = v["roc_auc_ci95"]
        print(f"{v['label']:<42} AUC {v['roc_auc']:.3f} [{lo:.3f}-{hi:.3f}]  Brier {v['brier']:.4f}  ECE {v['ece']:.4f}")
    print("Constant base-rate Brier:", round(r["baseline_constant_brier"], 4))
