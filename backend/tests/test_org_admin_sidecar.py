from backend.legacy.scripts.backfill_org_admin_sidecar import normalize_value_unit, stable_key


def test_stable_key_is_deterministic_and_namespaced() -> None:
    first = stable_key("orgev", "item-1", "회의 수당")
    second = stable_key("orgev", " item-1 ", "회의수당")
    assert first == second
    assert first.startswith("orgev:")


def test_percent_rate_becomes_ratio() -> None:
    value, unit, status, flags = normalize_value_unit(
        "basic_expense_ratio", 9.6, "%"
    )
    assert value == 0.096
    assert unit == "ratio"
    assert status == "normalized"
    assert flags == []


def test_committee_fee_normalizes_currency_scale_and_denominator() -> None:
    value, unit, status, flags = normalize_value_unit(
        "meeting_unit_price", 25, "만원/명·회"
    )
    assert value == 250_000
    assert unit == "KRW/person/meeting"
    assert status == "normalized"
    assert flags == []


def test_salary_without_time_basis_stays_ambiguous() -> None:
    value, unit, status, flags = normalize_value_unit(
        "salary_per_person", 154_000_000, "원", "보수(2023년 기준)"
    )
    assert value == 154_000_000
    assert unit == "KRW/person"
    assert status == "ambiguous"
    assert "salary_time_basis_unknown" in flags


def test_committee_instance_count_has_a_non_person_unit() -> None:
    value, unit, status, flags = normalize_value_unit(
        "committee_instance_count", 226, "개"
    )
    assert value == 226
    assert unit == "instance"
    assert status == "normalized"
    assert flags == []


def test_unmapped_value_is_never_silently_normalized() -> None:
    value, unit, status, flags = normalize_value_unit(None, 100, "만원")
    assert value is None
    assert unit is None
    assert status == "not_normalized"
    assert flags == ["unmapped_variable"]
