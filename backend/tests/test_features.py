import numpy as np
import pandas as pd
import pytest

from app.features import (FEATURE_COLUMNS, TARGET_COLUMN, InvalidInputError, build_features,
                          build_features_single, calculate_emi)
from app.synthetic import generate_synthetic_applications
from tests.conftest import VALID_APPLICATION


def test_known_emi_example():
    # 100,000 at 12% p.a. for 12 months -> 8,884.88 (standard reducing-balance EMI)
    assert calculate_emi(100_000, 12, 12) == pytest.approx(8884.88, abs=0.01)


def test_zero_interest_is_principal_over_tenure():
    assert calculate_emi(120_000, 0, 12) == pytest.approx(10_000.0)


@pytest.mark.parametrize("tenure", [0, -5])
def test_invalid_tenure_rejected(tenure):
    with pytest.raises(InvalidInputError):
        calculate_emi(100_000, 10, tenure)


def test_build_features_rejects_out_of_range_tenure_and_negative_loan():
    with pytest.raises(InvalidInputError):
        build_features_single({**VALID_APPLICATION, "tenure_months": 0})
    with pytest.raises(InvalidInputError):
        build_features_single({**VALID_APPLICATION, "loan_amount": -1})


def test_zero_income_does_not_divide_by_zero():
    with pytest.raises(InvalidInputError):
        build_features_single({**VALID_APPLICATION, "monthly_income": 0})


def test_missing_required_field_rejected():
    bad = {k: v for k, v in VALID_APPLICATION.items() if k != "age"}
    with pytest.raises(InvalidInputError):
        build_features_single(bad)


def test_total_emi_ratio_includes_existing_emi():
    f = build_features_single(VALID_APPLICATION).iloc[0]
    expected_new = calculate_emi(300000, 12.0, 36)
    assert f["new_loan_emi"] == pytest.approx(expected_new)
    assert f["total_emi"] == pytest.approx(expected_new + 5000)
    assert f["total_emi_to_income"] == pytest.approx((expected_new + 5000) / 50000)


def test_missing_credit_history_is_not_zero():
    unknown = build_features_single({**VALID_APPLICATION, "credit_history_months": None}).iloc[0]
    zero = build_features_single({**VALID_APPLICATION, "credit_history_months": 0}).iloc[0]
    assert np.isnan(unknown["credit_history_months"]) and unknown["credit_history_missing"] == 1
    assert zero["credit_history_months"] == 0 and zero["credit_history_missing"] == 0


def test_omitted_optional_field_treated_as_unknown():
    raw = {k: v for k, v in VALID_APPLICATION.items() if k != "credit_history_months"}
    assert build_features_single(raw).iloc[0]["credit_history_missing"] == 1


def test_feature_order_and_no_target_column():
    raw = generate_synthetic_applications(50, seed=1)
    feats = build_features(raw.drop(columns=[TARGET_COLUMN]))
    assert list(feats.columns) == FEATURE_COLUMNS
    assert TARGET_COLUMN not in FEATURE_COLUMNS


def test_batch_and_single_row_features_are_identical():
    """Training (batch) and API inference (single row) must give identical features."""
    raw = generate_synthetic_applications(25, seed=3).drop(columns=[TARGET_COLUMN])
    batch = build_features(raw)
    for i in range(len(raw)):
        single = build_features_single(raw.iloc[i].to_dict())
        pd.testing.assert_frame_equal(batch.iloc[[i]].reset_index(drop=True), single)
