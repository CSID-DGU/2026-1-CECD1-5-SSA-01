from backend.erce_web.committee_covered_estimator import (
    _expand,
    extract_finite_activity_months,
)


def test_finite_year_duration_is_parsed() -> None:
    assert extract_finite_activity_months("이 법은 시행일부터 1년간 효력을 가진다") == 12


def test_finite_month_duration_is_parsed() -> None:
    assert extract_finite_activity_months("시행일부터 18개월간 효력을 가진다") == 18


def test_eighteen_month_committee_is_expanded_without_guessing() -> None:
    assert _expand(
        3_708_000,
        recurrence="one_time",
        activity_months=18,
        horizon_years=5,
    ) == (3_708_000, 1_854_000, 0, 0, 0)


def test_one_time_item_is_not_repeated() -> None:
    assert _expand(
        300_000,
        recurrence="one_time",
        activity_months=None,
        horizon_years=5,
    ) == (300_000, 0, 0, 0, 0)

