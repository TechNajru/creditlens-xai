# What-if simulator and counterfactual alternatives (Stage 4)

Applies to the **loan simulation model only** (synthetic data). Endpoints: `POST /api/v1/scenarios/what-if`,
`POST /api/v1/scenarios/counterfactuals`.

## What may change
| Input | Rule |
|---|---|
| loan amount, tenure, interest rate | directly controllable application terms: allowed |
| existing monthly EMI | allowed only as an explicitly **hypothetical** debt-reduction scenario (opt-in for the search) |
| income, age, employment years, number of loans, credit history | never changed (facts or personal characteristics); the API returns 422 |

Never suggested: changing protected traits, changing history, or falsifying income.

## Every scenario or alternative
Re-scored through the shared feature code, so EMI, total EMI ÷ income and total interest are **recalculated**, not patched.
The response lists changed vs unchanged inputs, product-feasibility issues, the demonstration-policy result, and the change
in the model's output. It always carries the notes: the change is an association from a synthetic-data model, not a proven
causal effect, and real-world approval is not guaranteed.

## Policy (separate from the model: `app/policy.py`, version `demo-policy-1.0`)
Experimental thresholds, adjustable per request: simulated default probability ≤ 20%, total EMI ÷ income ≤ 50%; product
limits: loan ≥ 10,000, tenure 6–84 months. These are demonstration values, **not a validated lending policy**.

## Search
Grid over loan amount (25%–100% of the request), tenure (6–84 months, steps of 6) and, if allowed, existing EMI
(100/75/50/25/0%). Alternatives are ranked by a transparent cost: `1.0 × share of loan cut + 0.5 × tenure change/78 +
2.0 × share of existing EMI cut`. **The weights are design choices**, not learned or validated. If nothing passes, the response
says `no_feasible_alternative`, states the searched range, and shows the closest attempt (lowest probability), which does not pass.
Longer tenure lowers the EMI but raises total interest; the UI shows both.

## Limits
Only a bounded grid is searched ("no alternative found" does not prove none exists outside it). Results depend on a model
trained on synthetic data and mean nothing about real lenders.
