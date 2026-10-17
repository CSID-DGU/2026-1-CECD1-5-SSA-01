from backend.scripts.audit_org_admin_variables import (
    classify_item,
    extract_basis_year_candidates,
    infer_canonical_key,
    infer_source_class,
)


def _item(name: str, category: str = "", struct_id: str = "s1") -> dict:
    return {
        "item_id": f"{struct_id}:{name}",
        "struct_id": struct_id,
        "item_name": name,
        "item_category": category,
    }


def test_welfare_payment_is_not_misclassified_as_organization_payroll() -> None:
    assert classify_item(_item("부모급여 지급", "지원금"), set()) is None
    assert classify_item(_item("경찰공무원 마약류 검사 비용", "사업비"), set()) is None
    assert classify_item(_item("의무사관학교 건립비용(입학정원 40명)", "사업비"), set()) is None


def test_personnel_item_is_selected_as_organization_component() -> None:
    result = classify_item(_item("신규 증원인력 인건비", "인건비"), {"organization"})
    assert result is not None
    assert result.route == "organization"
    assert result.component == "personnel"


def test_committee_secretariat_personnel_stays_on_organization_route() -> None:
    result = classify_item(_item("공익법인위원회 사무국 직원 인건비", "인건비"), set())
    assert result is not None
    assert result.route == "organization"
    assert result.component == "personnel"


def test_committee_member_allowance_stays_on_committee_route() -> None:
    result = classify_item(_item("지원위원회 위촉위원 수당", "인건비"), set())
    assert result is not None
    assert result.route == "committee"
    assert result.component == "committee_meeting"


def test_asset_requires_organization_sibling_context() -> None:
    assert classify_item(_item("자산취득비", "사업비"), set()) is None
    result = classify_item(_item("자산취득비", "사업비"), {"organization"})
    assert result is not None
    assert result.component == "asset"
    assert result.confidence == "medium"


def test_variable_mapping_prefers_specific_committee_and_basic_expense_roles() -> None:
    assert infer_canonical_key("unit_cost", "회의참석수당 단가") == (
        "meeting_unit_price",
        "high",
    )
    assert infer_canonical_key("rate", "인건비 대비 기본경비 비율") == (
        "basic_expense_ratio",
        "high",
    )
    assert infer_canonical_key("target_count", "회의수당 지급 대상자 수") == (
        "paid_member_count",
        "high",
    )
    assert infer_canonical_key("unit_cost", "보수(2023년 기준)") == (
        "salary_per_person",
        "high",
    )
    assert infer_canonical_key(
        "unit_cost", "회의참석 사례금", "committee_operation"
    ) == ("meeting_unit_price", "medium")
    assert infer_canonical_key("target_count", "시·도 위원회 수") == (
        "committee_instance_count",
        "high",
    )


def test_source_and_year_are_candidates_not_silent_constants() -> None:
    text = "유사기관의 2025년 예산을 준용하고 2026년부터 적용"
    assert infer_source_class(text) == "similar_case"
    assert extract_basis_year_candidates(text) == (2025, 2026)
