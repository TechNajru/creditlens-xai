from pathlib import Path

import pytest

from app.cashflow import analyze
from tests.helpers import SALARY, hand_checked_rows, r, tx_from_rows

SAMPLES = Path(__file__).resolve().parents[2] / "sample_data"


def run_sample(name):
    from app.categorizer import assign_categories
    from app.ingestion import parse_csv
    tx, _ = assign_categories(parse_csv((SAMPLES / name).read_bytes(), name).transactions)
    return analyze(tx)


def test_hand_checked_metrics_use_only_interior_months():
    tx, _ = tx_from_rows(hand_checked_rows())
    res = analyze(tx)
    m = res["metrics"]
    assert res["coverage"]["usable_interior_months"] == 3 and res["coverage"]["sufficient_for_analysis"]
    assert m["avg_monthly_income_confirmed_or_likely"] == 50000.0   # 999999 edge decoy excluded
    assert m["income_variability_cv"] == 0.0
    assert m["avg_monthly_unverified_inflow"] == pytest.approx(666.67)
    assert m["avg_monthly_outflow"] == pytest.approx(43333.33)      # (23000+24000+83000)/3
    assert m["avg_monthly_net_cashflow"] == pytest.approx(7333.33)  # (29000+26000-33000)/3
    assert m["negative_net_cashflow_months"] == 1
    assert m["avg_monthly_essential_spend"] == pytest.approx(18333.33)
    assert m["observed_monthly_debt_payments"] == 5000.0
    assert m["observed_debt_to_income"] == pytest.approx(0.1)
    assert res["used_for_risk_model"] is False


def test_internal_transfers_excluded_from_income_and_spend():
    res = analyze(tx_from_rows(hand_checked_rows())[0])
    mar = next(x for x in res["monthly"] if x["month"] == "2026-03")
    assert mar["transfer_in"] == 10000 and mar["transfer_out"] == 10000
    assert mar["net_cashflow"] == 26000   # 50000 - (15000+5000+4000); transfers ignored


def test_edge_months_flagged_and_recurring_income_found():
    res = analyze(tx_from_rows(hand_checked_rows())[0])
    roles = {x["month"]: x["role"] for x in res["monthly"]}
    assert roles["2026-01"] == roles["2026-05"] == "edge_partial_possible" and roles["2026-03"] == "usable"
    assert res["identified_recurring_income_monthly"] == 50000.0
    assert res["recurring_income_groups"][0]["months_seen"] == 3


def test_upi_inflow_is_not_verified_income():
    res = run_sample("SYNTHETIC_gig_variable.csv")
    m = res["metrics"]
    assert m["avg_monthly_income_confirmed_or_likely"] == 0.0   # no confirmed/likely income observed
    assert m["avg_monthly_unverified_inflow"] > 5000
    assert m["observed_debt_to_income"] is None                 # undefined, not 0
    assert m["income_variability_cv"] is None


def test_insufficient_coverage_gives_unknown_not_zero():
    rows = [r("2026-01-10", SALARY, 1000, "credit"), r("2026-02-10", SALARY, 1000, "credit")]
    res = analyze(tx_from_rows(rows)[0])
    assert res["metrics"] is None and not res["coverage"]["sufficient_for_analysis"]


def test_gap_month_is_unknown_and_reported():
    rows = [r(f"2026-{m:02d}-10", "RENT PAYMENT", 100, "debit") for m in (1, 2, 4, 5)]
    res = analyze(tx_from_rows(rows)[0])
    assert res["coverage"]["gap_months"] == ["2026-03"]
    assert res["coverage"]["usable_interior_months"] == 2
    assert not res["coverage"]["sufficient_for_analysis"]


def test_payment_timeliness_not_inferred_from_transactions():
    res = analyze(tx_from_rows(hand_checked_rows())[0])
    assert res["payment_timeliness"]["computed"] is False


def test_payment_timeliness_computed_when_dates_given():
    rows = [r("2026-02-05", "HOME LOAN EMI", 5000, "debit", due_date="2026-02-05", payment_date="2026-02-04"),
            r("2026-03-05", "HOME LOAN EMI", 5000, "debit", due_date="2026-03-05", payment_date="2026-03-05"),
            r("2026-04-05", "HOME LOAN EMI", 5000, "debit", due_date="2026-04-05", payment_date="2026-04-09")]
    res = analyze(tx_from_rows(rows)[0])
    assert res["payment_timeliness"] == {"computed": True, "n_obligations": 3, "on_time_rate": 0.67}


def test_user_correction_changes_category_and_totals():
    tx, rep = tx_from_rows(hand_checked_rows(), {"FRIEND-1": "income_other"})
    assert rep == []
    row = tx[tx["key"] == "FRIEND-1"].iloc[0]
    assert (row["category"], row["category_source"], row["confidence"]) == ("income_other", "user_correction", "high")
    m = analyze(tx)["metrics"]
    assert m["avg_monthly_unverified_inflow"] == 0.0
    assert m["avg_monthly_income_confirmed_or_likely"] == pytest.approx((150000 + 2000) / 3, abs=0.01)


def test_invalid_corrections_are_rejected_and_reported():
    _, rep = tx_from_rows(hand_checked_rows(), {"FRIEND-1": "rent", "NOPE": "income_other"})
    assert len(rep) == 2 and all(x["severity"] == "error" for x in rep)


def test_unrecognised_supplied_category_warns_and_falls_back():
    tx, rep = tx_from_rows([r("2026-01-12", "RENT PAYMENT", 900, "debit", "foo")])
    assert rep[0]["severity"] == "warning" and tx.iloc[0]["category"] == "rent"
    assert tx.iloc[0]["category_source"] == "rule"


def test_sample_personas_behave_as_designed():
    stable = run_sample("SYNTHETIC_salaried_stable.csv")
    assert stable["coverage"]["usable_interior_months"] == 4 and stable["coverage"]["sufficient_for_analysis"]
    assert stable["metrics"]["avg_monthly_income_confirmed_only"] == 0.0     # keyword salary = "likely"
    assert stable["metrics"]["avg_monthly_income_confirmed_or_likely"] == 60000.0
    assert stable["metrics"]["observed_monthly_debt_payments"] == 6000.0
    assert stable["metrics"]["negative_net_cashflow_months"] == 0
    assert run_sample("SYNTHETIC_stressed.csv")["metrics"]["negative_net_cashflow_months"] == 4
    assert stable["missingness"]["low_confidence_value_share"] is not None
