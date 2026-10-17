from backend.scripts.evaluate_org_admin_sidecar import (
    is_simple_multiplicative_formula,
    is_suspected_scale_anomaly,
    official_constant_annual_amount,
    predicted_thousand,
    unique_operands,
)


def _evidence(key: str, value: float, unit: str) -> dict:
    return {
        "canonical_key": key,
        "normalized_value": value,
        "normalized_unit": unit,
        "unit_status": "normalized",
    }


def test_unique_operands_requires_one_value_per_role() -> None:
    rows = [
        _evidence("paid_member_count", 11, "person"),
        _evidence("annual_meetings", 4, "meeting/year"),
        _evidence("meeting_unit_price", 250_000, "KRW/person/meeting"),
    ]
    result = unique_operands(
        rows,
        ("paid_member_count", "annual_meetings", "meeting_unit_price"),
    )
    assert result is not None
    assert predicted_thousand(result[0]) == 11_000


def test_unique_operands_rejects_conflicting_scenarios() -> None:
    rows = [
        _evidence("headcount", 10, "person"),
        _evidence("headcount", 20, "person"),
        _evidence("salary_per_person", 50_000_000, "KRW/person/year"),
    ]
    assert unique_operands(rows, ("headcount", "salary_per_person")) is None


def test_unique_operands_can_sum_separate_committee_instance_scopes() -> None:
    rows = [
        _evidence("committee_instance_count", 17, "instance"),
        _evidence("committee_instance_count", 226, "instance"),
    ]
    result = unique_operands(
        rows,
        ("committee_instance_count",),
        ("committee_instance_count",),
    )
    assert result is not None
    assert result[0]["committee_instance_count"] == 243


def test_official_amount_requires_one_row_per_year_and_constant_series() -> None:
    valid = [
        {"year_offset": 0, "amount_thousand": 11_000},
        {"year_offset": 1, "amount_thousand": 11_000},
    ]
    assert official_constant_annual_amount(valid) == 11_000
    assert official_constant_annual_amount(
        [*valid, {"year_offset": 1, "amount_thousand": 12_000}]
    ) is None


def test_simple_formula_shape_rejects_extra_multiplier() -> None:
    assert is_simple_multiplicative_formula(
        ["민간위원 수 × 횟수 × 수당"], 3
    )
    assert is_simple_multiplicative_formula(
        ["민간위원 수 * 횟수 * 수당 (6명 * 12회 * 30만원)"], 3
    )
    assert not is_simple_multiplicative_formula(
        ["위원회 수 × 민간위원 수 × 횟수 × 수당"], 3
    )


def test_scale_anomaly_requires_near_power_of_ten_gap() -> None:
    assert is_suspected_scale_anomaly(1_200, 120)
    assert not is_suspected_scale_anomaly(1_200, 1_100)
    assert official_constant_annual_amount(
        [
            {"year_offset": 0, "amount_thousand": 11_000},
            {"year_offset": 1, "amount_thousand": 12_000},
        ]
    ) is None
