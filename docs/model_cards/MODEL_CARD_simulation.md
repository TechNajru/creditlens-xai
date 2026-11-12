# Model card — Loan-application simulation model

> Educational prototype. Not a lender, not a credit score, not a loan approval.

## Model details
- Version: `sim-logistic_regression-sigmoid-seed42-fs1.0.0`
- Algorithm: logistic_regression; probability calibration: sigmoid (calibration evaluated: yes)
- Feature schema: 1.0.0 (14 features)
- Trained (UTC): 2026-11-04T19:56:04+00:00; seed 42
- Libraries: Python 3.12.3, scikit-learn 1.9.1, pandas 3.1.0, numpy 2.5.4

## Intended use
Demonstrating the pipeline (features, calibration, evaluation, explanations) on SYNTHETIC loan applications.

## Out of scope
- Any real lending, pricing or approval decision.
- Estimating real borrower behaviour: the labels come from a hand-written rule.

## Data
- Provenance: SYNTHETIC simulation data (fictional; not real borrowers)
- Target: Simulated default within 12 months, generated from a hand-written rule plus noise.
- Split sizes: train 11,000, calibration 3,000, validation 3,000, test 3,000
- Excluded from model inputs: target column

## Training and selection protocol
Stratified random splits (train / calibration / validation / test). Preprocessing is fitted inside each pipeline on the training split. Calibrators are fitted on the calibration split. The model and calibrator were chosen by lowest validation Brier score across model x calibrator combinations. The test split was used once, after selection.

## Results
### Validation (used for selection)
| Model | Calibration | Brier | ROC-AUC | Log loss |
|---|---|---|---|---|
| logistic_regression **(selected)** | sigmoid | 0.1113 | 0.855 | 0.3604 |
| logistic_regression | none | 0.1114 | 0.855 | 0.3609 |
| logistic_regression | isotonic | 0.1117 | 0.854 | 0.3646 |
| hist_gradient_boosting | sigmoid | 0.1128 | 0.851 | 0.3650 |
| hist_gradient_boosting | none | 0.1129 | 0.851 | 0.3655 |
| hist_gradient_boosting | isotonic | 0.1129 | 0.848 | 0.3748 |
| random_forest | sigmoid | 0.1131 | 0.848 | 0.3670 |
| random_forest | none | 0.1133 | 0.848 | 0.3679 |
| random_forest | isotonic | 0.1136 | 0.846 | 0.3730 |

### Test (untouched split, selected model)
- ROC-AUC 0.848; average precision 0.702; Brier 0.1111; log loss 0.3635
- Constant base-rate baseline: Brier 0.1727; log loss 0.5294; accuracy of always predicting 'no default' 0.778

### Threshold trade-offs (experimental)
| Threshold | Precision | Recall | F1 |
|---|---|---|---|
| 0.05 | 0.275 | 0.962 | 0.428 |
| 0.1 | 0.354 | 0.892 | 0.507 |
| 0.15 | 0.429 | 0.823 | 0.564 |
| 0.2 | 0.489 | 0.758 | 0.594 |
| 0.3 | 0.604 | 0.658 | 0.630 |
| 0.5 | 0.776 | 0.453 | 0.573 |

## Explainability
- Method: SHAP PermutationExplainer (model-agnostic, independent background samples) (version shap-permutation-v1); scale: uncalibrated model risk score (probability scale, before calibration).
- Top global drivers (mean absolute contribution): total_emi_to_income (0.156), credit_history_missing (0.025), credit_history_months (0.018), loan_amount (0.018), num_existing_loans (0.015).
- Explanations describe how the model uses its inputs; they do not show causes.

## Fairness
- No fairness assessment has been performed for this model. Do not infer that it is fair.

## Limitations and ethical considerations
- Trained on synthetic data: performance says nothing about real borrowers.
- Not a credit-bureau score and not a loan-approval probability.
- Probability is the simulated 12-month default probability, not (1 - approval).
- Thresholds shown in reports are experimental.
- Metrics describe one random hold-out; they carry sampling uncertainty (no confidence intervals reported here).
