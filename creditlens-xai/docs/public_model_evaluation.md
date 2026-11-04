# Public-data model evaluation (UCI, seed 42)

Numbers below are from one run on the real file (30,000 clients). Regenerate with `python -m app.public_train`;
the authoritative output is `backend/reports/evaluation_public.json`. Split: 55% train / 15% calibration /
15% validation / 15% test, stratified random (single snapshot, so no temporal split).

**Selection rule:** lowest validation Brier across model × calibrator. Winner: HistGradientBoosting + sigmoid
(validation Brier 0.1313). Random Forest + sigmoid was 0.1318 — a practical tie, not evidence that boosting is better.

| Model (own best calibrator) | Test ROC-AUC | Test Avg. precision | Test Brier | Test log loss |
|---|---|---|---|---|
| HistGradientBoosting + sigmoid (selected) | 0.782 | 0.563 | 0.134 | 0.427 |
| Random Forest + sigmoid | 0.781 | 0.564 | 0.134 | 0.428 |
| Logistic Regression + isotonic | 0.742 | 0.493 | 0.142 | 0.452 |
| Constant base-rate baseline | – | – | 0.172 | 0.528 |

(Test metrics for the non-selected models are for comparison only; nothing was chosen on the test split.)
Average precision of a random ranker equals the positive rate, 0.221.

Calibration: on the test split the reliability curve follows the diagonal closely (e.g. predicted 0.704 vs observed 0.702
in the top bin). This is calibration on a random hold-out of the same 2005 snapshot, not evidence for other periods.

Threshold trade-offs (experimental, test split): at 0.2 → precision 0.42 / recall 0.66; at 0.3 → 0.54 / 0.54; at 0.5 → 0.69 / 0.35.

Caveats: Logistic Regression is hurt by extreme `payment_ratio_latest` outliers and by using PAY codes as plain numbers;
a better-engineered linear model is possible. Not a credit score; not validated beyond this dataset.
