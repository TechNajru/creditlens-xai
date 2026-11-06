"""Generate model cards from the trained artifact + evaluation report (no hand-typed numbers).

Run from backend/:  python -m app.model_card      ->  ../docs/model_cards/MODEL_CARD_<track>.md
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib

from . import config

TRACKS = {
    "simulation": {"title": "Loan-application simulation model", "report": "evaluation.json",
                   "artifact": config.ARTIFACT_NAME,
                   "use": "Demonstrating the pipeline (features, calibration, evaluation, explanations) on SYNTHETIC "
                          "loan applications.",
                   "out_of_scope": ["Any real lending, pricing or approval decision.",
                                    "Estimating real borrower behaviour: the labels come from a hand-written rule."]},
    "public": {"title": "Public-data credit-card default model (UCI)", "report": "evaluation_public.json",
               "artifact": config.PUBLIC_ARTIFACT_NAME,
               "use": "Educational exploration of calibrated, explainable default-risk modelling on a public "
                      "credit-card dataset.",
               "out_of_scope": ["Real lending, collections or approval decisions.",
                                "Populations, years, currencies or products other than 2005 Taiwan credit-card clients.",
                                "Use as a credit-bureau score."]},
}


def _f(x, n=3):
    return f"{x:.{n}f}"


def render_model_card(track: str, models_dir: Path | None = None, reports_dir: Path | None = None) -> str:
    t = TRACKS[track]
    models_dir, reports_dir = Path(models_dir or config.models_dir()), Path(reports_dir or config.reports_dir())
    rep = json.loads((reports_dir / t["report"]).read_text())
    meta = joblib.load(models_dir / t["artifact"])["metadata"]
    sel = rep["selected"]
    test = rep.get("test_metrics") or rep["test_metrics_selected"]
    base = rep["majority_baseline"]
    lv = meta["library_versions"]
    L = [f"# Model card — {t['title']}", "",
         "> Educational prototype. Not a lender, not a credit score, not a loan approval.", "",
         "## Model details",
         f"- Version: `{meta['model_version']}`",
         f"- Algorithm: {sel['model']}; probability calibration: {sel['calibration']} (calibration evaluated: "
         f"{'yes' if meta['calibration_evaluated'] else 'no'})",
         f"- Feature schema: {meta['feature_schema']['version']} ({len(meta['feature_schema']['columns'])} features)",
         f"- Trained (UTC): {meta['trained_at_utc']}; seed {meta['seed']}",
         f"- Libraries: Python {lv['python']}, scikit-learn {lv['scikit-learn']}, pandas {lv['pandas']}, numpy {lv['numpy']}", "",
         "## Intended use", t["use"], "", "## Out of scope"] + [f"- {x}" for x in t["out_of_scope"]]
    L += ["", "## Data", f"- Provenance: {meta['data_provenance']}", f"- Target: {meta['target_definition']}"]
    ds = meta.get("dataset")
    if ds:
        L += [f"- Source: {ds['creator']}, {ds['url']} ({ds['licence']})", f"- Population: {ds['population']}",
              f"- Rows: {ds['rows']:,}; positive rate {_f(ds['positive_rate'], 4)}; "
              f"rows identical except ID: {ds['duplicate_rows_excluding_id']}"]
    L += [f"- Split sizes: " + ", ".join(f"{k} {v:,}" for k, v in rep["split_sizes"].items()),
          "- Excluded from model inputs: " + (", ".join(meta["excluded_from_model_inputs"]) if "excluded_from_model_inputs" in meta else "target column"),
          "", "## Training and selection protocol",
          "Stratified random splits (train / calibration / validation / test). Preprocessing is fitted inside each "
          "pipeline on the training split. Calibrators are fitted on the calibration split. The model and calibrator "
          f"were chosen by {meta['selection_criterion']}. The test split was used once, after selection.", "",
          "## Results", "### Validation (used for selection)", "| Model | Calibration | Brier | ROC-AUC | Log loss |", "|---|---|---|---|---|"]
    for r in rep["validation_candidates"]:
        mark = " **(selected)**" if (r["model"], r["calibration"]) == (sel["model"], sel["calibration"]) else ""
        L.append(f"| {r['model']}{mark} | {r['calibration']} | {_f(r['brier'], 4)} | {_f(r['roc_auc'])} | {_f(r['log_loss'], 4)} |")
    L += ["", "### Test (untouched split, selected model)",
          f"- ROC-AUC {_f(test['roc_auc'])}; average precision {_f(test['average_precision'])}; "
          f"Brier {_f(test['brier'], 4)}; log loss {_f(test['log_loss'], 4)}",
          f"- Constant base-rate baseline: Brier {_f(base['brier_constant_base_rate'], 4)}; "
          f"log loss {_f(base['log_loss_constant_base_rate'], 4)}; accuracy of always predicting 'no default' "
          f"{_f(base['accuracy_always_negative'])}", "",
          "### Threshold trade-offs (experimental)", "| Threshold | Precision | Recall | F1 |", "|---|---|---|---|"]
    for t_ in rep["test_threshold_tradeoffs"]:
        L.append(f"| {t_['threshold']} | {_f(t_['precision'])} | {_f(t_['recall'])} | {_f(t_['f1'])} |")
    gi = rep.get("global_importance")
    L += ["", "## Explainability"]
    if gi:
        L += [f"- Method: {gi['method']} (version {gi['version']}); scale: {gi['scale']}.",
              "- Top global drivers (mean absolute contribution): " +
              ", ".join(f"{v['feature']} ({_f(v['mean_abs_shap'])})" for v in gi["values"][:5]) + ".",
              "- Explanations describe how the model uses its inputs; they do not show causes."]
    else:
        L.append("- Not available for this artifact (retrain).")
    L += ["", "## Fairness"]
    fair_path = reports_dir / "fairness_public.json"
    if track == "public" and fair_path.exists():
        f = json.loads(fair_path.read_text())
        L += [f"- A Fairlearn audit exists (`python -m app.fairness`). Positive prediction = flagged as high risk at threshold "
              f"{f['threshold']['value']} (chosen on validation, experimental); all group metrics use the untouched test split "
              f"({f['n_test']:,} clients).",
              "- Group gaps (reliable groups only; see the report for intervals and small-group warnings):"]
        for name, a in f["attributes"].items():
            sm = a["summary"]
            if sm["computed"]:
                L.append(f"  - {name}: demographic parity difference {_f(sm['demographic_parity_difference'])}, "
                         f"equalized odds difference {_f(sm['equalized_odds_difference'])}")
        mt = f["mitigation"]
        L += [f"- One mitigation was evaluated ({mt['method']}); it is NOT deployed and needs the protected attribute at decision time.",
              "- This does not show the model is fair. No single metric can, and proxy bias can remain."]
    else:
        L += ["- No fairness assessment has been performed for this model. Do not infer that it is fair."]
    L += ["", "## Limitations and ethical considerations"]
    L += [f"- {x}" for x in meta["limitations"]]
    L += ["- Metrics describe one random hold-out; they carry sampling uncertainty (no confidence intervals reported here)."]
    if ds:
        L += ["", "## Citation", f"{ds['creator']}. {ds['name']} [Dataset]. UCI Machine Learning Repository. {ds['doi']}"]
    return "\n".join(L) + "\n"


def write_cards(out_dir: Path | None = None) -> list[Path]:
    out_dir = Path(out_dir or config.BASE_DIR.parent / "docs" / "model_cards")
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for track in TRACKS:
        try:
            text = render_model_card(track)
        except FileNotFoundError:
            print(f"skipped {track}: not trained yet")
            continue
        p = out_dir / f"MODEL_CARD_{track}.md"
        p.write_text(text)
        written.append(p)
        print("wrote", p)
    return written


if __name__ == "__main__":
    write_cards()
