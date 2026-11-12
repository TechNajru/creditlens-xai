# Demo script and recording plan (about 7 minutes)

**Goal:** show an interviewer, in one pass, that you can build a complete, honest ML product: data -> calibrated model -> explanation -> human review -> audit.

## Before you record
- Fresh database: `python -m app.admin init` (copy the printed reviewer/admin passwords), then start backend and frontend.
- Two browser windows (or one normal + one private): **applicant** and **reviewer**. Zoom 110%, close other tabs, hide bookmarks.
- Have `sample_data/SYNTHETIC_salaried_stable.csv` and `SYNTHETIC_messy_for_validation_demo.csv` ready on the desktop.
- Record 1080p with OBS or the Windows Game Bar (Win+G); test the microphone; speak slowly. Export MP4, upload as *unlisted* and link it in the README.

## Script
| Time | Screen | Say / do |
|---|---|---|
| 0:00 | Landing page | "CreditLens XAI is an educational credit-risk decision-support platform. Note the banner: it is not a lender, not a credit score, and the loan model uses synthetic data." |
| 0:30 | Register | Show the data-use notice and consent checkbox. "Public sign-up only creates applicants; reviewers are created by an admin." |
| 1:00 | New application | Click the *moderate burden* example, create the draft. "Everything here is a fictional demo input." |
| 1:30 | Upload the messy CSV, then the good CSV | "Invalid rows are reported by row number, never echoing raw text. Duplicates are excluded." Correct one guessed category in the table. "Rule-based categories are guesses and are labelled with their confidence." |
| 2:30 | Cash-flow summary | "UPI inflows are never counted as verified income. Only interior months are used because the first and last month may be partial. This summary is **not** a model input." |
| 3:00 | Preview assessment | Read the probability and the reason codes. "The probability is calibrated; this is not an approval probability." Open nothing technical yet. |
| 3:30 | Submit | Tick the confirmation, submit. "The server runs submitted -> validation -> assessed -> manual review. Every step is audited." |
| 4:00 | Switch to reviewer window | Queue -> open. "The reviewer sees a pseudonymous reference, not the email." Show review reasons, input quality, cash flow. |
| 4:45 | Technical details | Expand the SHAP chart. "These contributions add up exactly to the raw model score; that is checked on every request. They describe the model, not causes." |
| 5:15 | Decision | Choose the decision that **differs** from the recommendation to show the mandatory override reason; then record one that follows it. "Model output and human decision are separate records." |
| 5:45 | Applicant window | Dashboard shows the outcome; open it: the applicant sees the decision but not internal override details. |
| 6:15 | What-if page (optional) | Show a counterfactual: "Only amount and tenure can change; income, age and history never can; debt reduction is labelled hypothetical; if nothing qualifies it says so." |
| 6:30 | Fairness page | "Wrongly-flagged rates by group with confidence intervals and small-group warnings. The mitigation is analysed but deliberately not deployed." |
| 7:00 | Admin -> Audit -> Verify | "Hash-chained audit trail. Tamper with one event and verification fails." Close with the limitations slide: no MFA, synthetic data, unvalidated thresholds. |

## If something goes wrong
Keep the sample CSVs and a pre-submitted application ready as a backup; narrate the failure honestly ("this is a cold start") and refresh. Never improvise numbers: read them from the screen.

## Screenshots for the README
Landing, application page with a preview, reviewer detail, model evaluation, fairness, admin audit. Store them in `docs/screenshots/`.
