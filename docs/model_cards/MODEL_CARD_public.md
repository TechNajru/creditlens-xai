# Model card — Public-data credit-card default model (UCI)

> Educational prototype. Not a lender, not a credit score, not a loan approval.

## Model details
- Version: `uci-hist_gradient_boosting-sigmoid-seed42-public-1.0.0`
- Algorithm: hist_gradient_boosting; probability calibration: sigmoid (calibration evaluated: yes)
- Feature schema: public-1.0.0 (23 features)
- Trained (UTC): 2026-11-04T19:56:21+00:00; seed 42
- Libraries: Python 3.12.3, scikit-learn 1.9.1, pandas 3.1.0, numpy 2.5.4

## Intended use
Educational exploration of calibrated, explainable default-risk modelling on a public credit-card dataset.

## Out of scope
- Real lending, collections or approval decisions.
- Populations, years, currencies or products other than 2005 Taiwan credit-card clients.
- Use as a credit-bureau score.

## Data
- Provenance: PUBLIC data: UCI Default of Credit Card Clients (I-Cheng Yeh (2009)), CC BY 4.0 (attribution required)
- Target: Default payment in the month after the 6-month observation window (1 = yes).
- Source: I-Cheng Yeh (2009), https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients (CC BY 4.0 (attribution required))
- Population: Credit-card clients in Taiwan, April-September 2005; amounts in NT dollars
- Rows: 30,000; positive rate 0.2212; rows identical except ID: 35
- Split sizes: train 16,500, calibration 4,500, validation 4,500, test 4,500
- Excluded from model inputs: SEX, EDUCATION, MARRIAGE, ID

## Training and selection protocol
Stratified random splits (train / calibration / validation / test). Preprocessing is fitted inside each pipeline on the training split. Calibrators are fitted on the calibration split. The model and calibrator were chosen by lowest validation Brier score across model x calibrator combinations. The test split was used once, after selection.

## Results
### Validation (used for selection)
| Model | Calibration | Brier | ROC-AUC | Log loss |
|---|---|---|---|---|
| hist_gradient_boosting **(selected)** | sigmoid | 0.1313 | 0.786 | 0.4215 |
| hist_gradient_boosting | none | 0.1316 | 0.786 | 0.4219 |
| random_forest | sigmoid | 0.1318 | 0.788 | 0.4221 |
| hist_gradient_boosting | isotonic | 0.1320 | 0.784 | 0.4280 |
| random_forest | none | 0.1321 | 0.788 | 0.4226 |
| random_forest | isotonic | 0.1322 | 0.785 | 0.4389 |
| logistic_regression | isotonic | 0.1378 | 0.761 | 0.4439 |
| logistic_regression | sigmoid | 0.1381 | 0.762 | 0.4418 |
| logistic_regression | none | 0.1381 | 0.762 | 0.4418 |

### Test (untouched split, selected model)
- ROC-AUC 0.782; average precision 0.563; Brier 0.1340; log loss 0.4272
- Constant base-rate baseline: Brier 0.1722; log loss 0.5283; accuracy of always predicting 'no default' 0.779

### Threshold trade-offs (experimental)
| Threshold | Precision | Recall | F1 |
|---|---|---|---|
| 0.05 | 0.232 | 0.990 | 0.376 |
| 0.1 | 0.281 | 0.925 | 0.431 |
| 0.15 | 0.348 | 0.797 | 0.484 |
| 0.2 | 0.424 | 0.663 | 0.517 |
| 0.3 | 0.542 | 0.537 | 0.539 |
| 0.5 | 0.688 | 0.354 | 0.467 |

## Explainability
- Method: SHAP PermutationExplainer (model-agnostic, independent background samples) (version shap-permutation-v1); scale: uncalibrated model risk score (probability scale, before calibration).
- Top global drivers (mean absolute contribution): months_delayed (0.066), PAY_0 (0.037), utilization_latest (0.018), BILL_AMT1 (0.014), PAY_AMT1 (0.012).
- Explanations describe how the model uses its inputs; they do not show causes.

## Fairness
- A Fairlearn audit exists (`python -m app.fairness`). Positive prediction = flagged as high risk at threshold 0.28 (chosen on validation, experimental); all group metrics use the untouched test split (4,500 clients).
- Group gaps (reliable groups only; see the report for intervals and small-group warnings):
  - SEX: demographic parity difference 0.054, equalized odds difference 0.043
  - EDUCATION: demographic parity difference 0.101, equalized odds difference 0.085
  - MARRIAGE: demographic parity difference 0.025, equalized odds difference 0.012
  - AGE_GROUP: demographic parity difference 0.114, equalized odds difference 0.123
- One mitigation was evaluated (Fairlearn ThresholdOptimizer: post-processing to equalized odds with randomized group-specific thresholds); it is NOT deployed and needs the protected attribute at decision time.
- This does not show the model is fair. No single metric can, and proxy bias can remain.

## Limitations and ethical considerations
- Trained on 2005 Taiwan credit-card clients (NT dollars); not validated for other populations, years, currencies or loan products.
- Predicts a credit-card payment default in the next month, not a loan default or approval.
- Random stratified split of a single snapshot: no temporal validation was possible.
- Not a credit-bureau score. Thresholds in reports are experimental.
- SEX, EDUCATION and MARRIAGE are excluded from inputs, but proxy bias can remain.
- Metrics describe one random hold-out; they carry sampling uncertainty (no confidence intervals reported here).

## Citation
I-Cheng Yeh (2009). Default of Credit Card Clients [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C55S3H
