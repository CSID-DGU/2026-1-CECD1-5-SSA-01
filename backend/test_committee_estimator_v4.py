from __future__ import annotations

from backend.committee_estimator_v4.structure import (
    extract_committee_nodes,
    select_formula_plan,
)
from backend.committee_estimator_v4.precedents import (
    parse_support_bundle_operands,
)


def _article(no: str, text: str) -> dict[str, str]:
    return {"no": no, "text": text, "change_type": "new"}


def test_detects_mandatory_distributed_committee() -> None:
    nodes = extract_committee_nodes([
        _article(
            "제32조",
            "다만, 인구 25만 이상의 지방자치단체는 "
            "시민고충처리위원회를 두어야 한다.",
        )
    ])
    assert [node.name for node in nodes] == ["시민고충처리위원회"]
    assert select_formula_plan(nodes[0]).family == "multi_instance_operating_baseline"


def test_local_government_policy_context_is_not_distributed_installation() -> None:
    nodes = extract_committee_nodes([
        _article(
            "제5조(특별지방자치단체지원협의회)",
            "특별지방자치단체의 효율적인 운영을 지원하기 위하여 "
            "국무총리 소속으로 특별지방자치단체지원협의회를 둔다. "
            "위원에는 지방자치단체의 장을 포함한다. "
            "협의회를 지원하기 위하여 지원단을 둔다.",
        )
    ])
    assert len(nodes) == 1
    assert select_formula_plan(nodes[0]).family == "analog_flat_operating_budget"


def test_title_alias_is_merged_into_formal_name() -> None:
    nodes = extract_committee_nodes([
        _article(
            "제89조(기본계획심의회)",
            "인공지능에너지문화수도조성기본계획을 심의하기 위하여 "
            "인공지능에너지문화수도조성기본계획심의회를 둔다. "
            "심의회는 위원장을 포함하여 20명 이내의 위원으로 구성한다.",
        )
    ])
    assert len(nodes) == 1
    assert nodes[0].name == "인공지능에너지문화수도조성기본계획심의회"
    assert select_formula_plan(nodes[0]).family == "meeting_allowance"


def test_support_bundle_is_routed_as_compound_formula() -> None:
    nodes = extract_committee_nodes([
        _article(
            "제10조(지원위원회의 설치)",
            "정책을 심의하기 위하여 국무총리 소속으로 "
            "통합특별시지원위원회를 둔다. "
            "안건을 검토하기 위하여 실무위원회를 둔다. "
            "사무를 지원하기 위하여 실무지원단을 설치할 수 있다.",
        )
    ])
    assert len(nodes) == 1
    plan = select_formula_plan(nodes[0])
    assert plan.family == "committee_support_bundle"
    assert {relation.relation_type for relation in nodes[0].relations} == {
        "subordinate_committee",
        "support_organization",
    }


def test_specific_composition_reference_routes_to_meeting_formula() -> None:
    nodes = extract_committee_nodes([
        _article(
            "제278조(산림복지에 관한 특례)",
            "사무를 심의하기 위하여 산림복지심의위원회를 둔다. "
            "이 경우 산림복지심의위원회의 구성 및 운영은 "
            "「산림복지진흥에 관한 법률」을 준용한다.",
        )
    ])
    assert len(nodes) == 1
    assert select_formula_plan(nodes[0]).family == "meeting_allowance"


def test_unrelated_later_staff_does_not_contaminate_context() -> None:
    nodes = extract_committee_nodes([
        _article(
            "제1조(문화정책위원회)",
            "문화정책을 심의하기 위하여 문화정책위원회를 둔다. "
            "위원회는 15명 이내의 위원으로 구성한다.",
        ),
        _article(
            "제2조(사업단)",
            "별도의 사업단을 설치하고 직원과 정원을 둔다.",
        ),
    ])
    assert len(nodes) == 1
    assert len(nodes[0].article_refs) == 1
    assert select_formula_plan(nodes[0]).family == "meeting_allowance"


def test_follows_contiguous_governance_articles_without_fixed_window() -> None:
    nodes = extract_committee_nodes([
        _article(
            "제6조(임금위원회의 설치)",
            "임금을 심의하기 위하여 임금위원회를 둔다.",
        ),
        _article("제7조(위원회의 기능)", "위원회는 임금제도를 심의한다."),
        _article("제8조(위원회의 구성)", "위원회는 21명 이내의 위원으로 구성한다."),
        _article("제9조(위원장)", "위원장은 위원회를 대표한다."),
        _article("제10조(회의)", "위원회의 회의는 재적위원 과반수로 의결한다."),
        _article(
            "제11조(소위원회)",
            "업무를 수행하기 위하여 9명 이내의 소위원회를 둘 수 있다.",
        ),
        _article("제12조(실무협의회)", "실무 검토를 위하여 실무협의회를 둘 수 있다."),
        _article("제13조(간사)", "위원회의 사무를 처리하기 위하여 간사를 둔다."),
        _article("제14조(관계기관 등에 대한 협조요청)", "위원회는 자료를 요청할 수 있다."),
        _article("제15조(수당 등)", "위원회 위원에게 수당을 지급할 수 있다."),
        _article("제16조(운영세칙)", "위원회 운영세칙은 위원장이 정한다."),
        _article("제17조(실태조사)", "정부는 매년 실태를 조사한다."),
    ])
    assert len(nodes) == 1
    assert len(nodes[0].article_refs) == 11
    assert select_formula_plan(nodes[0]).family == "compound_committee_allowance"


def test_optional_unquantified_subcommittee_does_not_force_compound_formula() -> None:
    nodes = extract_committee_nodes([
        _article(
            "제6조(헌법개정자문위원회의 설치)",
            "전문가의 의견을 수렴하기 위하여 헌법개정자문위원회"
            "(이하 자문위원회라 한다)를 둘 수 있다.",
        ),
        _article(
            "제7조(자문위원회의 구성 및 운영)",
            "자문위원회는 30명 이상의 위원으로 구성한다. "
            "자문위원회는 분과위원회를 둘 수 있다.",
        ),
    ])
    assert len(nodes) == 1
    assert nodes[0].relations[0].cost_bearing is False
    assert select_formula_plan(nodes[0]).family == "meeting_allowance"


def test_subordinate_body_is_not_promoted_to_independent_event() -> None:
    nodes = extract_committee_nodes([
        _article(
            "제5조(지원협의회)",
            "지원을 협의하기 위하여 국무총리 소속으로 지원협의회를 둔다. "
            "안건 검토를 위하여 분야별 전문위원회를 둘 수 있다.",
        ),
        _article(
            "제6조(회의)",
            "지원협의회의 정기회의는 반기에 1회 개최한다.",
        ),
    ])
    assert [node.name for node in nodes] == ["지원협의회"]


def test_generic_subcommittee_article_does_not_create_prose_named_root() -> None:
    nodes = extract_committee_nodes([
        _article(
            "제8조(소위원회)",
            "필요한 경우에는 위원회가 위임한 사항을 심의하는 "
            "소위원회를 둘 수 있다.",
        )
    ])
    assert nodes == []


def test_participation_assembly_is_treated_as_deliberative_body() -> None:
    nodes = extract_committee_nodes([
        _article(
            "제8조(헌법개정국민참여회의 설치)",
            "국민의 참여를 보장하기 위하여 국회에 "
            "500명 이상의 헌법개정국민참여회의를 둔다.",
        )
    ])
    assert [node.name for node in nodes] == ["헌법개정국민참여회의"]
    assert select_formula_plan(nodes[0]).family == "meeting_allowance"


def test_parliamentary_special_committee_routes_to_staffed_formula() -> None:
    nodes = extract_committee_nodes([
        _article(
            "제45조의2(헌법특별위원회)",
            "헌법개정안을 심사하기 위하여 헌법특별위원회를 둔다. "
            "위원 수는 30명으로 하고 위원장은 본회의에서 선거한다.",
        )
    ])
    assert len(nodes) == 1
    plan = select_formula_plan(nodes[0])
    assert plan.family == "staffed_committee_operation"
    assert "사업비" in plan.formula


def test_internal_employee_disciplinary_body_is_not_bill_level_event() -> None:
    nodes = extract_committee_nodes([
        _article(
            "제22조(징계위원회)",
            "조사위원회 직원에 대한 징계처분을 의결하기 위하여 "
            "징계위원회를 둔다.",
        )
    ])
    assert nodes == []


def test_location_phrase_is_removed_from_formal_body_name() -> None:
    nodes = extract_committee_nodes([
        _article(
            "제5조의2(위원후보추천위원회)",
            "위원 후보자의 추천을 위하여 각 선출기관에 "
            "인권위원후보추천위원회를 둔다. "
            "추천위원회는 선출할 때마다 10명의 위원으로 구성한다.",
        )
    ])
    assert [node.name for node in nodes] == ["인권위원후보추천위원회"]


def test_staffed_committee_takes_precedence_over_support_bundle() -> None:
    nodes = extract_committee_nodes([
        _article(
            "제22조(공익법인위원회의 설치 및 구성)",
            "법무부에 공익법인위원회를 둔다. "
            "상임위원 1명을 포함하여 구성하며, "
            "사무를 처리하기 위하여 사무기구를 둔다.",
        )
    ])
    assert len(nodes) == 1
    assert nodes[0].name == "공익법인위원회"
    assert select_formula_plan(nodes[0]).family == "staffed_committee_operation"


def test_vague_unnamed_committees_are_not_entities() -> None:
    nodes = extract_committee_nodes([
        _article(
            "제5조(외국교육기관)",
            "시장과 교육감은 심의를 위하여 각각에 소속되는 위원회를 둔다.",
        )
    ])
    assert nodes == []


def test_parses_complete_support_bundle_without_table_total() -> None:
    evidence = """
    지원위원회의 위원은 총 30명이며, 이 중 민간위원은 20명으로 가정
    실무위원회의 위원은 25명이며, 이 중 민간위원은 15명으로 가정
    회의당 25만원을 지급하며 각각 연 4회 회의를 실시
    실무지원단 운영비
    51
    105
    107
    109
    111
    483
    합 계
    """
    values = parse_support_bundle_operands(evidence)
    assert values is not None
    assert values.main_paid_members == 20
    assert values.subordinate_paid_members == 15
    assert values.annual_meetings == 4
    assert values.unit_price_won == 250_000
    assert values.support_annual_budget_thousand == 108_000
    assert values.annual_amount_thousand == 143_000
