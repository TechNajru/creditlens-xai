import pytest
from fastapi.testclient import TestClient

from app.features import calculate_emi
from app.main import app
from app.policy import DemoPolicy
from app.predict import load_bundle
from app.scenarios import HYPOTHETICAL, IMMUTABLE, MUTABLE, ScenarioError, apply_changes, counterfactuals, what_if
from tests.conftest import VALID_APPLICATION

client = TestClient(app)
HEAVY = {**VALID_APPLICATION, "monthly_income": 40000, "loan_amount": 1_200_000, "annual_interest_rate": 14,
         "existing_emi": 15000, "credit_history_months": None, "age": 27, "employment_years": 2,
         "num_existing_loans": 2}
MODERATE = {**VALID_APPLICATION, "loan_amount": 900_000, "existing_emi": 8000, "monthly_income": 50000}


@pytest.fixture(scope="module")
def bundle(trained_dir):
    return load_bundle(trained_dir / "models")


def test_field_groups_are_disjoint_and_complete():
    assert set(MUTABLE).isdisjoint(IMMUTABLE)
    assert {"monthly_income", "age", "employment_years", "num_existing_loans", "credit_history_months"} == set(IMMUTABLE)
    assert HYPOTHETICAL == {"existing_emi"}


@pytest.mark.parametrize("field", ["monthly_income", "age", "employment_years", "num_existing_loans", "credit_history_months"])
def test_immutable_fields_cannot_be_changed(field):
    with pytest.raises(ScenarioError) as e:
        apply_changes(VALID_APPLICATION, {field: 1})
    assert "cannot be changed" in str(e.value)


def test_unknown_field_rejected():
    with pytest.raises(ScenarioError):
        apply_changes(VALID_APPLICATION, {"gender": 1})


def test_what_if_recalculates_derived_values(bundle):
    res = what_if(bundle, VALID_APPLICATION, [{"name": "Smaller loan", "changes": {"loan_amount": 150000, "tenure_months": 24}}], DemoPolicy())
    s = res["scenarios"][0]
    expected_emi = calculate_emi(150000, 12.0, 24)
    assert s["metrics"]["new_loan_emi"] == pytest.approx(expected_emi)
    assert s["metrics"]["total_emi_to_income"] == pytest.approx((expected_emi + 5000) / 50000)
    assert s["metrics"]["total_interest"] == pytest.approx(expected_emi * 24 - 150000)
    assert set(s["changed_inputs"]) == {"loan_amount", "tenure_months"}
    assert "age" in s["unchanged_inputs"] and "annual_interest_rate" in s["unchanged_inputs"]
    assert s["delta_vs_base"]["new_loan_emi"] == pytest.approx(expected_emi - res["base"]["metrics"]["new_loan_emi"])
    assert any("not proven causal" in n for n in res["notes"])


def test_what_if_flags_hypothetical_debt_reduction_and_infeasible_terms(bundle):
    res = what_if(bundle, VALID_APPLICATION, [
        {"name": "Pay down debt", "changes": {"existing_emi": 0}},
        {"name": "Very long", "changes": {"tenure_months": 120}}], DemoPolicy())
    assert res["scenarios"][0]["hypothetical"] == ["existing_emi"]
    assert res["scenarios"][1]["feasibility_issues"] and not res["scenarios"][1]["meets_policy"]


def test_counterfactuals_respect_constraints_and_keep_immutables_fixed(bundle):
    policy = DemoPolicy()
    res = counterfactuals(bundle, MODERATE, policy)
    assert res["status"] in ("found", "already_meets_policy", "no_feasible_alternative")
    if res["status"] == "already_meets_policy":
        pytest.skip("fixture model already accepts this application")
    assert res["status"] == "found" and 1 <= len(res["alternatives"]) <= 3
    for alt in res["alternatives"]:
        for field in IMMUTABLE:
            assert alt["inputs"][field] == MODERATE[field] or (alt["inputs"][field] is None and MODERATE[field] is None)
        assert alt["inputs"]["annual_interest_rate"] == MODERATE["annual_interest_rate"]
        assert alt["inputs"]["loan_amount"] <= MODERATE["loan_amount"]
        assert policy.min_loan_amount <= alt["inputs"]["loan_amount"]
        assert policy.min_tenure_months <= alt["inputs"]["tenure_months"] <= policy.max_tenure_months
        assert alt["meets_policy"] and alt["metrics"]["default_probability_simulated"] <= policy.max_default_probability
        assert alt["metrics"]["total_emi_to_income"] <= policy.max_total_emi_to_income
        emi = calculate_emi(alt["inputs"]["loan_amount"], 12.0, alt["inputs"]["tenure_months"])
        assert alt["metrics"]["new_loan_emi"] == pytest.approx(emi)           # derived field recalculated
        assert alt["changed_inputs"] and alt["hypothetical"] == []             # no debt reduction unless allowed
        assert "total_interest" in alt["delta_vs_base"]
    costs = [a["change_cost"] for a in res["alternatives"]]
    assert costs == sorted(costs)


def test_hypothetical_debt_reduction_only_when_allowed(bundle):
    strict = counterfactuals(bundle, HEAVY, DemoPolicy(), allow_hypothetical_debt_reduction=False)
    assert all("existing_emi" not in a["changed_inputs"] for a in strict["alternatives"])
    allowed = counterfactuals(bundle, HEAVY, DemoPolicy(), allow_hypothetical_debt_reduction=True)
    for a in allowed["alternatives"]:
        if "existing_emi" in a["changed_inputs"]:
            assert a["hypothetical"] == ["existing_emi"]
            assert a["inputs"]["existing_emi"] < HEAVY["existing_emi"]


def test_no_feasible_alternative_is_reported_honestly(bundle):
    impossible = DemoPolicy(max_default_probability=0.001, max_total_emi_to_income=0.05)
    res = counterfactuals(bundle, HEAVY, impossible)
    assert res["status"] == "no_feasible_alternative" and res["alternatives"] == []
    assert res["closest_attempt"] and res["closest_attempt"]["meets_policy"] is False
    assert "No alternative" in res["message"] and res["search"]["candidates_evaluated"] > 10
    assert res["search"]["searched_range"]["tenure_months"] == [6, 84]


def test_already_meeting_policy_needs_no_alternative(bundle):
    easy = {**VALID_APPLICATION, "loan_amount": 30000, "existing_emi": 0, "monthly_income": 100000}
    res = counterfactuals(bundle, easy, DemoPolicy(max_default_probability=0.9))
    assert res["status"] == "already_meets_policy" and res["alternatives"] == []


def test_policy_rules_and_feasibility():
    p = DemoPolicy()
    ok = p.evaluate(0.1, 0.3)
    assert ok["passes"] and len(ok["rules"]) == 2
    assert not p.evaluate(0.3, 0.3)["passes"] and not p.evaluate(0.1, 0.6)["passes"]
    assert p.feasibility_issues(5000, 36) and p.feasibility_issues(50000, 100) and not p.feasibility_issues(50000, 36)
    assert "Experimental" in p.describe()["disclaimer"]


# ---------------- API ----------------
def test_what_if_api(trained_dir):
    r = client.post("/api/v1/scenarios/what-if", json={"application": VALID_APPLICATION, "scenarios": [
        {"name": "A", "changes": {"loan_amount": 100000}}, {"name": "B", "changes": {"tenure_months": 60}}]})
    assert r.status_code == 200
    body = r.json()
    assert [s["name"] for s in body["scenarios"]] == ["A", "B"] and body["policy"]["version"] == "demo-policy-1.0"


@pytest.mark.parametrize("changes", [{"monthly_income": 99999}, {"age": 20}, {"gender": 1}, {"tenure_months": 0}, {"loan_amount": -5}])
def test_what_if_api_rejects_bad_changes(trained_dir, changes):
    r = client.post("/api/v1/scenarios/what-if", json={"application": VALID_APPLICATION, "scenarios": [{"name": "x", "changes": changes}]})
    assert r.status_code == 422


def test_what_if_api_limits_and_validation(trained_dir):
    many = [{"name": str(i), "changes": {"loan_amount": 1000 + i}} for i in range(6)]
    assert client.post("/api/v1/scenarios/what-if", json={"application": VALID_APPLICATION, "scenarios": many}).status_code == 422
    assert client.post("/api/v1/scenarios/what-if", json={"application": VALID_APPLICATION, "scenarios": []}).status_code == 422


def test_counterfactual_api(trained_dir):
    r = client.post("/api/v1/scenarios/counterfactuals", json={"application": HEAVY,
                    "policy": {"max_default_probability": 0.3}, "allow_hypothetical_debt_reduction": True})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("found", "no_feasible_alternative") and body["policy"]["max_default_probability"] == 0.3
    assert body["search"]["never_changed"] and any("not guaranteed" in n for n in body["notes"])


def test_counterfactual_api_validation_and_missing_model(tmp_path, monkeypatch, trained_dir):
    bad = client.post("/api/v1/scenarios/counterfactuals", json={"application": HEAVY, "policy": {"max_default_probability": 5}})
    assert bad.status_code == 422
    monkeypatch.setenv("CREDITLENS_MODELS_DIR", str(tmp_path))
    assert client.post("/api/v1/scenarios/counterfactuals", json={"application": HEAVY}).status_code == 503
