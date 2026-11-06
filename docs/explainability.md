# Explainability (Stage 3)

**Method:** SHAP `PermutationExplainer` over the whole fitted pipeline (model-agnostic), with an independent
background sample of 100 training rows stored inside the model artifact. A fixed seed makes explanations repeatable.

**What is explained:** the model's *uncalibrated* risk score (probability scale). `baseline + sum(contributions) = score`.
This is verified for every explanation; if the check fails, or the explainer errors, the API returns
`explanation.status = "unavailable"` and the UI says so. Nothing is invented.

**What it is not**
- Not percentage-point changes to the displayed (calibrated) probability.
- Not causal. Changing an input in real life need not change the outcome the way the model score changes.
- Not the same as global importance: a feature that matters on average may not matter for one person.

**Views.** `detail=summary` (applicant): top factors + plain-language reason codes. `detail=full` (reviewer):
all contributions, scale, method/version, global importance. Role gating arrives with authentication (Stage 5);
until then the UI shows the technical section in a collapsible block and the API must not be public.

## Known limitation: correlated inputs
Several loan features overlap (new EMI, total EMI, EMI-to-income, loan-to-income). SHAP splits credit among
correlated features, so a feature that *looks* risky (e.g. a large total EMI) can show a small negative
contribution while a related ratio carries the large positive one. Read the group together. Reason codes show the
largest contributors only; they should not be read as independent causes.

## Global importance
Computed at training time on a sample of the validation split (`CREDITLENS_GLOBAL_SHAP_ROWS`, default 200) and stored in
the artifact and evaluation report. Sanity check: on the synthetic model, `total_emi_to_income` dominates, matching
the rule used to generate the labels.
