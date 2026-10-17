from backend.committee_precedent_resolver import (
    _body_is_bundled_in_profile,
    _composition_flags,
    _formula_implied_thousand,
    _standing_payroll_item,
    _target_bodies,
    _target_member_limit,
    _target_has_standing_members,
    EvidenceItem,
)


def _item(name: str, formula: str = "", profile_text: str = "") -> EvidenceItem:
    return EvidenceItem(
        item_id="I",
        bill_no="B",
        item_name=name,
        family="personnel",
        annual_thousand=1,
        formula=formula,
        numeric_variable_count=1,
        profile_names=(),
        total_member_counts=(),
        profile_text=profile_text,
    )


def test_nonstanding_allowance_is_not_standing_member_payroll() -> None:
    assert _standing_payroll_item(_item("비상임위원 수당")) is False


def test_standing_member_payroll_is_detected() -> None:
    assert _standing_payroll_item(_item("상임위원 인건비")) is True


def test_predicate_form_of_standing_member_is_detected() -> None:
    assert _target_has_standing_members("대통령령으로 정하는 수의 위원은 상임으로 한다")


def test_exact_member_count_form_is_parsed() -> None:
    assert _target_member_limit("위원장 1명을 포함한 10명의 추천위원회 위원") == 10


def test_multi_institution_installation_is_a_structure_flag() -> None:
    flags = _composition_flags("각 선출·지명기관에 추천위원회를 둔다")
    assert "multi_instance" in flags


def test_subordinate_body_is_recovered_from_source_passage() -> None:
    case = {
        "target_terms": ["과학기술국제협력전략위원회", "연구안보특별위원회"],
        "target_passages": [
            "전략위원회는 위원장 1명을 포함한 20명 이내로 구성하고 실무위원회를 둘 수 있다."
        ],
    }
    assert _target_bodies(case) == [
        "과학기술국제협력전략위원회",
        "연구안보특별위원회",
        "실무위원회",
    ]


def test_subordinate_body_can_be_bundled_only_with_exact_profile_evidence() -> None:
    item = _item(
        "사회연대경제발전위원회 설치 및 운영",
        profile_text="위원회의 심의사항을 검토하기 위해 실무위원회를 둔다.",
    )
    assert _body_is_bundled_in_profile("실무위원회", item)
    assert not _body_is_bundled_in_profile("전문위원회", item)


def test_explicit_formula_is_normalized_to_thousand_won() -> None:
    value = _formula_implied_thousand("28,426건 ÷ 23건 × 300만원")
    assert value is not None
    assert round(value) == 3_707_739


def test_internally_inconsistent_priced_item_is_not_coherent() -> None:
    item = EvidenceItem(
        item_id="I",
        bill_no="B",
        item_name="위원회 운영비",
        family="committee",
        annual_thousand=371_000,
        formula="28,426건 ÷ 23건 × 300만원",
        numeric_variable_count=5,
        profile_names=(),
        total_member_counts=(),
        profile_text="",
    )
    assert item.coherent is False


def test_internally_consistent_priced_item_remains_coherent() -> None:
    item = EvidenceItem(
        item_id="I",
        bill_no="B",
        item_name="위원회 운영비",
        family="committee",
        annual_thousand=3_708_000,
        formula="28,426건 ÷ 23건 × 300만원",
        numeric_variable_count=5,
        profile_names=(),
        total_member_counts=(),
        profile_text="",
    )
    assert item.coherent is True
