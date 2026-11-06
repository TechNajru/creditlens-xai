# Fairness audit and limited-information experiments (Stage 4)

Both apply to the **public-data model** (UCI credit-card default, Taiwan 2005). Generate the reports (from `backend/`):
```powershell
python -m app.fairness       # -> reports/fairness_public.json
python -m app.experiments    # -> reports/experiments_public.json
```

## Fairness audit — definitions
- **Positive prediction** = flagged as high default risk (probability ≥ threshold). **Favourable outcome** = not flagged.
- Fairlearn's "selection rate" is therefore the **flagged rate**. This avoids confusing predicting default with approving someone.
- Main harm: **false positives** (flagged but did not default → possible wrongful denial). False negatives are reported too.
- Threshold chosen on the **validation** split (max F1, experimental); all group metrics use the **untouched test split** (4,500 clients).
- Per group: size, flagged/favourable rate, false-positive/negative rates (95% Wilson intervals), observed default rate,
  calibration gap (mean predicted − observed), reliability flags. Groups under 100 clients are excluded from disparity summaries;
  rates need ≥30 relevant cases.
- Attributes: SEX, EDUCATION, MARRIAGE (audit only, **not** model inputs) and AGE group (**age is a model input** and is audited).

## Example findings (one run, seed 42; your numbers may differ slightly)
- Men were flagged more often than women (≈27% vs 22%) and wrongly flagged more often (FPR ≈17% vs 13%); intervals do not overlap.
  Calibration gaps by sex were tiny (±0.006). Observed default rates also differ between the groups, so this is not by itself proof of bias.
- Age 50+ had the highest wrongly-flagged rate (≈22% vs ≈13–15%) with n=422.
- EDUCATION "others" (n=20) and the undocumented codes are too small to interpret.
- Mitigation (Fairlearn ThresholdOptimizer, equalized odds on SEX): the equalized-odds gap barely moved (0.043 → 0.038) while
  accuracy fell about 1 point. It is **not deployed**: it needs the protected attribute at decision time (possibly unlawful in lending),
  randomizes some decisions, produces no calibrated probability, and does not fix proxy bias.

## What this audit cannot show
No metric proves fairness; differences within the intervals may be noise; group differences can reflect real differences,
data-collection effects or historical bias; results do not transfer beyond this 2005 dataset.

## Limited-information experiments
Hides payment months from clients who *do* have 6 months (so it is **not** a thin-file evaluation: no genuine thin-file subset exists).
Fixed recipe (HistGradientBoosting + sigmoid calibration), same splits, no selection among variants, bootstrap 95% intervals.

| Visible history | ROC-AUC (95% CI) | Brier | Calibration error |
|---|---|---|---|
| 6 months | 0.782 (0.766–0.799) | 0.1340 | 0.0066 |
| last 3 months | 0.776 (0.762–0.792) | 0.1354 | 0.0084 |
| last 2 months | 0.769 (0.752–0.784) | 0.1359 | 0.0086 |
| last month | 0.765 (0.750–0.782) | 0.1372 | 0.0107 |
| none (limit + age only) | 0.593 (0.575–0.615) | 0.1693 | 0.0292 |

Constant base-rate Brier = 0.1722. Reading: most signal sits in the most recent months' repayment status; with no payment history the
model has almost no skill (Brier barely beats the constant baseline). That is an argument against pretending an applicant with no history can be scored.
