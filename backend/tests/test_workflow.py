from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app import registry
from app.db import get_session_factory
from app.models import Application, AuditEvent, ModelVersion, Transaction, Upload, Assessment
from app.train import train
from app.workflow import STATES, TRANSITIONS
from tests.api_helpers import HEAVY, LOAN, SAMPLES, Api, logged_in, seed

pytestmark = pytest.mark.real_auth
APPS = "/api/v1/applications"
STABLE = SAMPLES / "SYNTHETIC_salaried_stable.csv"


@pytest.fixture
def world(db_env):
    seed()
    w = SimpleNamespace(alice=logged_in("alice@example.com"), bob=logged_in("bob@example.com"), reviewer=Api(), admin=Api())
    w.reviewer.login("reviewer@demo.local")
    w.admin.login("admin@demo.local")
    return w


def new_app(api, inputs=LOAN):
    r = api.post(APPS, json=inputs)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def submitted_app(api, inputs=LOAN, csv=None):
    app_id = new_app(api, inputs)
    if csv:
        assert api.upload(app_id, csv).status_code == 201
    r = api.post(f"{APPS}/{app_id}/submit")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "manual_review"
    return app_id


def statuses(admin, app_id):
    ev = admin.get(f"/api/v1/admin/audit?application_id={app_id}&limit=200").json()["events"][::-1]
    return [e["details"]["status_to"] for e in ev if e["action"] == "application.status_changed"]


def db():
    return get_session_factory()()


# ---------------- state machine ----------------
def test_state_machine_table_is_consistent():
    assert set(TRANSITIONS) == set(STATES)
    assert TRANSITIONS["final_demo_decision"] == set()
    assert TRANSITIONS["draft"] == {"submitted"} and TRANSITIONS["manual_review"] == {"info_requested", "final_demo_decision"}
    for targets in TRANSITIONS.values():
        assert targets <= set(STATES)


def test_sanity_of_the_two_policy_cases(world):
    ok = submitted_app(world.alice, LOAN)
    bad = submitted_app(world.alice, HEAVY)
    assert world.reviewer.get(f"/api/v1/reviews/{ok}").json()["policy_recommendation"] == "demo_approved"
    assert world.reviewer.get(f"/api/v1/reviews/{bad}").json()["policy_recommendation"] == "demo_declined"


# ---------------- drafts, history, ownership ----------------
def test_create_edit_list_and_history(world):
    app_id = new_app(world.alice)
    assert world.alice.get(APPS).json()["applications"][0]["id"] == app_id
    r = world.alice.patch(f"{APPS}/{app_id}", json={**LOAN, "loan_amount": 250000})
    assert r.status_code == 200 and r.json()["loan_inputs"]["loan_amount"] == 250000
    assert world.alice.patch(f"{APPS}/{app_id}", json={**LOAN, "tenure_months": 0}).status_code == 422
    assert world.alice.post(APPS, json={k: v for k, v in LOAN.items() if k != "age"}).status_code == 422
    assert world.bob.get(APPS).json()["applications"] == []                       # history is private


def test_other_users_cannot_touch_my_application(world):
    app_id = new_app(world.alice)
    tx_url = f"{APPS}/{app_id}"
    assert world.alice.upload(app_id, STABLE).status_code == 201
    probes = [("get", tx_url, {}), ("patch", tx_url, {"json": LOAN}), ("delete", tx_url, {}),
              ("get", f"{tx_url}/transactions", {}), ("get", f"{tx_url}/cashflow", {}),
              ("post", f"{tx_url}/assessments/preview", {}), ("post", f"{tx_url}/submit", {})]
    for method, url, kw in probes:
        assert getattr(world.bob, method)(url, **kw).status_code == 404, url
    assert world.bob.upload(app_id, STABLE).status_code == 404
    tx = world.alice.get(f"{tx_url}/transactions").json()["transactions"][0]
    assert world.bob.patch(f"{tx_url}/transactions/{tx['id']}", json={"category": "rent"}).status_code == 404
    assert world.reviewer.get(f"/api/v1/reviews/{app_id}").status_code == 404     # drafts are invisible to reviewers
    assert world.admin.get(f"{APPS}/{app_id}").status_code == 403                 # admins do not read applications


def test_a_users_transaction_id_cannot_be_used_from_another_application(world):
    a1, a2 = new_app(world.alice), new_app(world.alice)
    world.alice.upload(a1, STABLE)
    tx = world.alice.get(f"{APPS}/{a1}/transactions").json()["transactions"][0]
    assert world.alice.patch(f"{APPS}/{a2}/transactions/{tx['id']}", json={"category": "rent"}).status_code == 404


# ---------------- uploads, corrections, cash flow ----------------
def test_upload_validation_and_limits(world, monkeypatch):
    app_id = new_app(world.alice)
    r = world.alice.upload(app_id, STABLE)
    assert r.status_code == 201 and r.json()["upload"]["rows_with_errors"] == 0 and r.json()["transactions"]
    assert world.alice.upload(app_id, b"a,b\n1,2\n", name="x.xlsx").status_code == 415
    assert world.alice.upload(app_id, b"foo,bar\n1,2\n").status_code == 422
    messy = world.alice.upload(app_id, SAMPLES / "SYNTHETIC_messy_for_validation_demo.csv").json()
    assert messy["upload"]["rows_with_errors"] == 3 and messy["upload"]["duplicates_excluded"] == 1
    assert "IMPOSSIBLE" not in str(messy["upload"]["issues"])                      # reports carry no raw text
    monkeypatch.setenv("CREDITLENS_MAX_UPLOAD_BYTES", "50")
    assert world.alice.upload(app_id, STABLE).status_code == 413
    with db() as s:
        assert s.scalar(select(func.count()).select_from(Upload)) == 1             # a re-upload replaces, never duplicates


def test_category_correction_rules_and_cashflow(world):
    app_id = new_app(world.alice)
    assert world.alice.get(f"{APPS}/{app_id}/cashflow").status_code == 404
    world.alice.upload(app_id, SAMPLES / "SYNTHETIC_gig_variable.csv")
    cf = world.alice.get(f"{APPS}/{app_id}/cashflow").json()
    assert cf["used_for_risk_model"] is False and cf["metrics"]["avg_monthly_income_confirmed_or_likely"] == 0
    txs = world.alice.get(f"{APPS}/{app_id}/transactions").json()["transactions"]
    credit = next(t for t in txs if t["direction"] == "credit" and "2026-02" <= t["date"][:7] <= "2026-05")   # interior month
    assert world.alice.patch(f"{APPS}/{app_id}/transactions/{credit['id']}", json={"category": "rent"}).status_code == 422   # wrong direction
    ok = world.alice.patch(f"{APPS}/{app_id}/transactions/{credit['id']}", json={"category": "income_other"})
    assert ok.status_code == 200 and ok.json()["category_source"] == "user_correction" and ok.json()["confidence"] == "high"
    cf2 = world.alice.get(f"{APPS}/{app_id}/cashflow").json()
    assert cf2["metrics"]["avg_monthly_income_confirmed_only"] > 0


# ---------------- assessments ----------------
def test_preview_assessment_stores_versions_and_hides_reviewer_detail(world):
    app_id = new_app(world.alice)
    r = world.alice.post(f"{APPS}/{app_id}/assessments/preview")
    assert r.status_code == 201
    body = r.json()
    ex = body["result"]["explanation"]
    assert body["is_preview"] is True and body["model_version"].startswith("sim-") and body["policy_version"] == "demo-policy-1.0"
    assert 0 <= body["result"]["default_probability_simulated"] <= 1
    assert ex["status"] == "available" and ex["reason_codes"] and "contributions" not in ex and "global_importance" not in ex
    assert world.alice.get(f"{APPS}/{app_id}").json()["assessment"]["is_preview"] is True
    world.alice.patch(f"{APPS}/{app_id}", json={**LOAN, "loan_amount": 100000})
    assert world.alice.get(f"{APPS}/{app_id}").json()["assessment"] is None       # stale previews are discarded


def test_no_active_model_gives_503_and_leaves_the_draft_alone(db_env):
    seed(activate=False)
    api = logged_in("alice@example.com")
    app_id = new_app(api)
    assert api.post(f"{APPS}/{app_id}/assessments/preview").status_code == 503
    r = api.post(f"{APPS}/{app_id}/submit")
    assert r.status_code == 503 and "active" in r.json()["detail"].lower()
    assert api.get(f"{APPS}/{app_id}").json()["status"] == "draft"


def test_tampered_model_file_is_refused(db_env):
    seed()
    with db() as s:
        path = s.scalar(select(ModelVersion.artifact_path))
    with open(path, "ab") as f:
        f.write(b"tamper")
    api = logged_in("alice@example.com")
    r = api.post(f"{APPS}/{new_app(api)}/assessments/preview")
    assert r.status_code == 503 and "checksum" in r.json()["detail"]


# ---------------- submission ----------------
def test_submission_pipeline_states_records_and_reasons(world):
    app_id = submitted_app(world.alice, HEAVY)
    assert statuses(world.admin, app_id) == ["submitted", "validation", "assessed", "manual_review"]
    view = world.reviewer.get(f"/api/v1/reviews/{app_id}").json()
    codes = [r["code"] for r in view["review_reasons"]]
    assert {"demo_policy_all_cases_reviewed", "credit_history_unknown", "cashflow_not_provided", "policy_rules_not_met"} <= set(codes)
    a = view["assessment"]
    assert a["is_preview"] is False and a["model_version"].startswith("sim-") and a["feature_schema_version"] == "1.0.0"
    with db() as s:
        asm = s.scalar(select(Assessment).where(Assessment.application_id == app_id, Assessment.is_preview.is_(False)))
        assert asm.feature_snapshot.features["total_emi_to_income"] > 1 and asm.feature_snapshot.input_snapshot["loan_amount"] == HEAVY["loan_amount"]
        assert asm.explanation.status == "available" and asm.model_version_id is not None


def test_failed_validation_returns_to_draft(world):
    app_id = new_app(world.alice)
    with db() as s:
        app = s.get(Application, app_id)
        app.loan_inputs = {**app.loan_inputs, "loan_amount": -5}
        s.commit()
    r = world.alice.post(f"{APPS}/{app_id}/submit")
    assert r.status_code == 422 and r.json()["detail"]["problems"]
    assert world.alice.get(f"{APPS}/{app_id}").json()["status"] == "draft"
    assert statuses(world.admin, app_id) == ["submitted", "validation", "draft"]


def test_submitted_application_is_locked_for_the_applicant(world):
    app_id = submitted_app(world.alice)
    assert world.alice.patch(f"{APPS}/{app_id}", json=LOAN).status_code == 409
    assert world.alice.upload(app_id, STABLE).status_code == 409
    assert world.alice.post(f"{APPS}/{app_id}/submit").status_code == 409
    assert world.alice.post(f"{APPS}/{app_id}/assessments/preview").status_code == 409
    assert world.alice.delete(f"{APPS}/{app_id}").status_code == 409              # not while a reviewer may be working on it


def test_with_cashflow_file_the_coverage_reason_disappears(world):
    app_id = submitted_app(world.alice, csv=STABLE)
    view = world.reviewer.get(f"/api/v1/reviews/{app_id}").json()
    assert view["input_quality"]["cashflow_provided"] is True and view["input_quality"]["cashflow_sufficient"] is True
    assert "cashflow_not_provided" not in [r["code"] for r in view["review_reasons"]]
    assert view["cashflow"]["used_for_risk_model"] is False and view["transactions"]


# ---------------- reviewer view and privacy ----------------
def test_reviewer_sees_full_detail_and_a_pseudonym_applicant_sees_less(world):
    app_id = submitted_app(world.alice)
    q = world.reviewer.get("/api/v1/reviews/queue").json()["applications"]
    assert [a["id"] for a in q] == [app_id] and q[0]["applicant_ref"].startswith("U") and "email" not in str(q)
    rv = world.reviewer.get(f"/api/v1/reviews/{app_id}").json()
    assert "alice@example.com" not in str(rv)
    full = rv["assessment"]["result"]["explanation"]
    assert len(full["contributions"]) == 14 and full["global_importance"]["values"]
    mine = world.alice.get(f"{APPS}/{app_id}").json()
    assert "contributions" not in mine["assessment"]["result"]["explanation"]
    assert world.alice.get("/api/v1/reviews/queue").status_code == 403


def test_applicant_timeline_is_filtered(world):
    app_id = submitted_app(world.alice)
    tl = world.alice.get(f"{APPS}/{app_id}").json()["timeline"]
    assert [e["details"].get("status_to") for e in tl if e["action"] == "application.status_changed"][-1] == "manual_review"
    assert all(set(e["details"]) <= {"status_from", "status_to", "decision"} for e in tl)
    assert "assessment.created" not in [e["action"] for e in tl]


# ---------------- information requests ----------------
def test_information_request_round_trip(world):
    app_id = submitted_app(world.alice)
    r = world.reviewer.post(f"/api/v1/reviews/{app_id}/request-info", json={"message": "Please confirm your employment length."})
    assert r.status_code == 200 and r.json()["status"] == "info_requested"
    mine = world.alice.get(f"{APPS}/{app_id}").json()
    rid = mine["info_requests"][0]["id"]
    assert mine["editable"] is True
    blocked = world.alice.post(f"{APPS}/{app_id}/submit")                         # must answer first, and stays answerable
    assert blocked.status_code == 422 and world.alice.get(f"{APPS}/{app_id}").json()["status"] == "info_requested"
    assert world.alice.post(f"{APPS}/{app_id}/info-requests/{rid + 99}/respond", json={"message": "x"}).status_code == 404
    assert world.alice.post(f"{APPS}/{app_id}/info-requests/{rid}/respond", json={"message": "Five years, same employer."}).status_code == 200
    assert world.alice.post(f"{APPS}/{app_id}/info-requests/{rid}/respond", json={"message": "again"}).status_code == 409
    world.alice.patch(f"{APPS}/{app_id}", json={**LOAN, "employment_years": 6})
    again = world.alice.post(f"{APPS}/{app_id}/submit")
    assert again.status_code == 200 and again.json()["status"] == "manual_review"
    with db() as s:
        assert s.scalar(select(func.count()).select_from(Assessment).where(Assessment.application_id == app_id, Assessment.is_preview.is_(False))) == 2
    assert world.reviewer.get(f"/api/v1/reviews/{app_id}").json()["assessment"]["result"]["derived_values"]
    assert world.reviewer.post(f"/api/v1/reviews/{app_id}/request-info", json={"message": "short"}).status_code == 422


# ---------------- decisions ----------------
def test_override_requires_a_reason_and_is_recorded(world):
    app_id = submitted_app(world.alice, HEAVY)                    # policy recommends decline
    url = f"/api/v1/reviews/{app_id}/decision"
    assert world.reviewer.post(url, json={"decision": "demo_approved", "reason": "Looks fine to me overall."}).status_code == 422
    assert world.reviewer.post(url, json={"decision": "demo_approved", "reason": "Looks fine to me overall.", "override_reason": "short"}).status_code == 422
    assert world.reviewer.post(url, json={"decision": "maybe", "reason": "Looks fine to me overall."}).status_code == 422
    assert world.reviewer.post(url, json={"decision": "demo_declined", "reason": "short"}).status_code == 422
    ok = world.reviewer.post(url, json={"decision": "demo_approved", "reason": "Strong verified savings noted.",
                                        "override_reason": "Applicant provided savings evidence offline."})
    assert ok.status_code == 200
    d = ok.json()["decisions"][0]
    assert d["is_override"] is True and d["policy_recommendation"] == "demo_declined" and d["override_reason"]
    assert ok.json()["status"] == "final_demo_decision"
    assert world.reviewer.post(url, json={"decision": "demo_declined", "reason": "Second attempt here."}).status_code == 409
    assert world.reviewer.post(f"/api/v1/reviews/{app_id}/request-info", json={"message": "Anything else please?"}).status_code == 409


def test_following_the_recommendation_needs_no_override(world):
    app_id = submitted_app(world.alice, LOAN)                      # policy recommends approve
    r = world.reviewer.post(f"/api/v1/reviews/{app_id}/decision", json={"decision": "demo_approved", "reason": "Meets all demo rules."})
    assert r.status_code == 200 and r.json()["decisions"][0]["is_override"] is False
    mine = world.alice.get(f"{APPS}/{app_id}").json()
    assert mine["status"] == "final_demo_decision" and mine["final_decision"]["decision"] == "demo_approved"
    assert "override_reason" not in mine["final_decision"] and "policy_recommendation" not in mine["final_decision"]
    assert world.alice.patch(f"{APPS}/{app_id}", json=LOAN).status_code == 409


def test_decline_against_an_approve_recommendation_is_also_an_override(world):
    app_id = submitted_app(world.alice, LOAN)
    url = f"/api/v1/reviews/{app_id}/decision"
    assert world.reviewer.post(url, json={"decision": "demo_declined", "reason": "Concerned about stability."}).status_code == 422
    assert world.reviewer.post(url, json={"decision": "demo_declined", "reason": "Concerned about stability.",
                                          "override_reason": "Unstable income pattern in notes."}).json()["decisions"][0]["is_override"] is True


def test_reviewer_cannot_review_their_own_application(world):
    app_id = submitted_app(world.alice)
    alice_id = world.alice.user["id"]
    assert world.admin.patch(f"/api/v1/admin/users/{alice_id}", json={"role": "reviewer"}).status_code == 200
    assert world.alice.get("/api/v1/auth/me").status_code == 401                  # role change forces a fresh login
    world.alice.login("alice@example.com")
    assert world.alice.get("/api/v1/reviews/queue").json()["applications"] == []
    r = world.alice.post(f"/api/v1/reviews/{app_id}/decision", json={"decision": "demo_approved", "reason": "I approve myself."})
    assert r.status_code == 403 and "own application" in r.json()["detail"]


# ---------------- deletion and retention ----------------
def test_deleting_removes_content_but_keeps_a_minimal_audit_record(world):
    app_id = new_app(world.alice)
    world.alice.upload(app_id, STABLE)
    world.alice.post(f"{APPS}/{app_id}/assessments/preview")
    assert world.alice.delete(f"{APPS}/{app_id}").status_code == 200
    with db() as s:
        for model in (Application, Upload, Transaction, Assessment):
            assert s.scalar(select(func.count()).select_from(model)) == 0, model
        deleted = s.scalars(select(AuditEvent).where(AuditEvent.action == "application.deleted")).all()
        assert len(deleted) == 1 and deleted[0].application_id == app_id and "description" not in str(deleted[0].details)
    assert world.alice.get(f"{APPS}/{app_id}").status_code == 404


def test_finished_applications_can_be_deleted(world):
    app_id = submitted_app(world.alice)
    world.reviewer.post(f"/api/v1/reviews/{app_id}/decision", json={"decision": "demo_approved", "reason": "Meets all demo rules."})
    assert world.alice.delete(f"{APPS}/{app_id}").status_code == 200
    assert world.reviewer.get(f"/api/v1/reviews/{app_id}").status_code == 404


# ---------------- admin ----------------
def test_admin_user_management(world):
    a = world.admin
    r = a.post("/api/v1/admin/users", json={"email": "rev2@example.com", "password": "another-strong-pass-2", "role": "reviewer"})
    assert r.status_code == 201 and r.json()["role"] == "reviewer"
    assert a.post("/api/v1/admin/users", json={"email": "rev2@example.com", "password": "another-strong-pass-2", "role": "reviewer"}).status_code == 409
    assert a.post("/api/v1/admin/users", json={"email": "x@example.com", "password": "short", "role": "reviewer"}).status_code == 422
    assert a.post("/api/v1/admin/users", json={"email": "x@example.com", "password": "another-strong-pass-2", "role": "root"}).status_code == 422
    users = {u["email"]: u for u in a.get("/api/v1/admin/users").json()["users"]}
    assert {"alice@example.com", "reviewer@demo.local", "admin@demo.local", "rev2@example.com"} <= set(users)
    assert a.patch(f"/api/v1/admin/users/{users['admin@demo.local']['id']}", json={"is_active": False}).status_code == 400   # not yourself
    assert a.patch("/api/v1/admin/users/9999", json={"is_active": False}).status_code == 404
    assert world.alice.get("/api/v1/admin/users").status_code == 403


def test_model_registry_register_activate_and_switch(world, tmp_path):
    a = world.admin
    models = a.get("/api/v1/admin/models").json()["models"]
    assert len(models) == 1 and models[0]["is_active"] and models[0]["track"] == "simulation"
    again = a.post("/api/v1/admin/models/register", json={"track": "simulation"}).json()
    assert again["newly_registered"] is False and len(a.get("/api/v1/admin/models").json()["models"]) == 1
    train(models_dir=tmp_path / "m2", reports_dir=tmp_path / "r2", n_samples=1500, seed=3)
    with db() as s:
        mv2, created = registry.register_artifact(s, "simulation", source=tmp_path / "m2" / "creditlens_model.joblib")
        s.commit()
        mv2_id, mv2_version = mv2.id, mv2.version
    assert created
    assert a.post(f"/api/v1/admin/models/{mv2_id}/activate").json()["is_active"] is True
    listed = a.get("/api/v1/admin/models").json()["models"]
    assert sum(m["is_active"] for m in listed) == 1 and next(m for m in listed if m["is_active"])["id"] == mv2_id
    app_id = submitted_app(world.alice)
    assert world.reviewer.get(f"/api/v1/reviews/{app_id}").json()["assessment"]["model_version"] == mv2_version
    assert a.post(f"/api/v1/admin/models/9999/activate").status_code == 404
    assert world.alice.post("/api/v1/admin/models/register", json={"track": "simulation"}).status_code == 403


def test_monitoring_summary_and_honest_notes(world):
    ok, bad = submitted_app(world.alice, LOAN), submitted_app(world.alice, HEAVY)
    world.reviewer.post(f"/api/v1/reviews/{ok}/decision", json={"decision": "demo_approved", "reason": "Meets all demo rules."})
    m = world.admin.get("/api/v1/admin/monitoring").json()
    assert m["applications_by_status"] == {"final_demo_decision": 1, "manual_review": 1}
    assert m["assessments"]["official"] == 2 and m["prediction_distribution"]["n"] == 2
    assert sum(m["prediction_distribution"]["histogram_10_bins"]) == 2
    assert m["input_missingness"]["credit_history_unknown_share"] == 0.5 and m["input_missingness"]["no_cashflow_file_share"] == 1.0
    assert m["review"]["decisions"] == 1 and m["review"]["override_share"] == 0.0
    assert any("cannot be measured without repayment outcomes" in n for n in m["notes"])


def test_audit_trail_is_chained_and_tampering_is_detected(world):
    submitted_app(world.alice)
    ok = world.admin.get("/api/v1/admin/audit/verify").json()
    assert ok["ok"] is True and ok["checked"] > 10
    with db() as s:
        ev = s.scalars(select(AuditEvent).where(AuditEvent.action == "application.created")).first()
        ev.details = {"status_to": "tampered"}
        s.commit()
        bad_id = ev.id
    bad = world.admin.get("/api/v1/admin/audit/verify").json()
    assert bad["ok"] is False and bad["first_bad_event_id"] == bad_id


def test_audit_listing_filters_by_application(world):
    app_id = submitted_app(world.alice)
    other = new_app(world.bob)
    mine = world.admin.get(f"/api/v1/admin/audit?application_id={app_id}").json()["events"]
    assert mine and all(e["application_id"] == app_id for e in mine)
    assert not any(e["application_id"] == other for e in mine)
    assert world.admin.get("/api/v1/admin/audit?limit=0").status_code == 422
