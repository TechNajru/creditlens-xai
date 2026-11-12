"""End-to-end application flow (API level, real cookies/CSRF/roles):

Register -> create application -> upload sample CSV -> review transactions -> assess supported inputs ->
view explanation -> submit for review -> reviewer records decision -> applicant sees the outcome.
"""
import pytest

from tests.api_helpers import LOAN, SAMPLES, Api, seed

pytestmark = pytest.mark.real_auth


def test_register_to_reviewer_decision(db_env):
    seed()

    # 1. applicant registers (consent recorded) and is logged in
    applicant = Api()
    notice = applicant.client.get("/api/v1/consent/notice").json()
    reg = applicant.register("najrudeen.demo@example.com", notice=notice["version"])
    assert reg.status_code == 201 and reg.json()["user"]["role"] == "applicant"

    # 2. create a draft application
    app = applicant.post("/api/v1/applications", json={**LOAN, "credit_history_months": None}).json()
    app_id = app["id"]
    assert app["status"] == "draft" and app["editable"] is True

    # 3. upload the sample CSV; 4. review the extracted transactions and correct a guessed category
    up = applicant.upload(app_id, SAMPLES / "SYNTHETIC_salaried_stable.csv").json()
    assert up["upload"]["rows_with_errors"] == 0 and up["upload"]["rows_valid"] > 20
    txs = applicant.get(f"/api/v1/applications/{app_id}/transactions").json()
    guessed = [t for t in txs["transactions"] if t["confidence"] == "low"]
    assert guessed, "the sample has at least one low-confidence (guessed) category to review"
    fixed = applicant.patch(f"/api/v1/applications/{app_id}/transactions/{guessed[0]['id']}",
                            json={"category": "groceries" if guessed[0]["direction"] == "debit" else "income_other"})
    assert fixed.json()["category_source"] == "user_correction"
    cashflow = applicant.get(f"/api/v1/applications/{app_id}/cashflow").json()
    assert cashflow["coverage"]["sufficient_for_analysis"] and cashflow["used_for_risk_model"] is False

    # 5. assess supported inputs (preview) and 6. view the explanation
    preview = applicant.post(f"/api/v1/applications/{app_id}/assessments/preview").json()
    explanation = preview["result"]["explanation"]
    assert preview["is_preview"] and explanation["status"] == "available" and explanation["reason_codes"]
    assert preview["result"]["data_provenance"].startswith("SYNTHETIC")

    # 7. submit for human review (server runs submitted -> validation -> assessed -> manual_review)
    submitted = applicant.post(f"/api/v1/applications/{app_id}/submit").json()
    assert submitted["status"] == "manual_review" and submitted["final_decision"] is None

    # 8. reviewer inspects quality, cash flow, model output and full explanation, then records a decision
    reviewer = Api()
    reviewer.login("reviewer@demo.local")
    queue = reviewer.get("/api/v1/reviews/queue").json()["applications"]
    assert [q["id"] for q in queue] == [app_id]
    detail = reviewer.get(f"/api/v1/reviews/{app_id}").json()
    assert detail["input_quality"]["credit_history"] == "unknown" and detail["cashflow"]["metrics"]
    assert any(t["category_source"] == "user_correction" for t in detail["transactions"])
    assert len(detail["assessment"]["result"]["explanation"]["contributions"]) == 14
    assert detail["assessment"]["policy_version"] == "demo-policy-1.0"
    rec = detail["policy_recommendation"]
    decision = reviewer.post(f"/api/v1/reviews/{app_id}/decision",
                             json={"decision": rec, "reason": "Follows the demonstration policy recommendation."})
    assert decision.status_code == 200 and decision.json()["status"] == "final_demo_decision"

    # 9. applicant sees the outcome; the model output and the human decision are separate records
    final = applicant.get(f"/api/v1/applications/{app_id}").json()
    assert final["status"] == "final_demo_decision" and final["final_decision"]["decision"] == rec
    assert final["assessment"]["is_preview"] is False

    # 10. admin: the audit trail is complete, ordered and tamper-evident
    admin = Api()
    admin.login("admin@demo.local")
    events = admin.get(f"/api/v1/admin/audit?application_id={app_id}&limit=200").json()["events"][::-1]
    flow = [e["details"]["status_to"] for e in events if e["action"] == "application.status_changed"]
    assert flow == ["submitted", "validation", "assessed", "manual_review", "final_demo_decision"]
    actions = [e["action"] for e in events]
    for needed in ("application.created", "upload.created", "transaction.category_corrected", "assessment.created",
                   "review.viewed", "review.decision_recorded"):
        assert needed in actions
    assert admin.get("/api/v1/admin/audit/verify").json()["ok"] is True
