from __future__ import annotations

from backend.legacy.committee.committee_estimator_v5.structure import (
    extract_committee_events,
    plan_committee_cost,
)


def _article(no: str, text: str, change_type: str = "제정") -> dict[str, str]:
    return {"no": no, "text": text, "change_type": change_type}


def test_support_staff_and_meeting_costs_are_both_planned() -> None:
    articles = [
        _article(
            "제5조(분쟁조정위원회의 설치)",
            "분쟁을 조정하기 위하여 분쟁조정위원회를 둔다. "
            "위원회는 50명 이내의 위원으로 구성한다. "
            "업무를 지원하기 위하여 사무국을 둘 수 있고 전문위원을 둘 수 있다.",
        )
    ]
    event = extract_committee_events("", articles)[0]
    plan = plan_committee_cost(event)
    assert plan.family == "committee_support_operation"
    assert [value.kind for value in plan.components] == [
        "main_meeting_allowance",
        "support_staff_compensation",
        "support_operating_expense",
    ]


def test_long_support_organization_name_is_not_double_counted_by_suffix() -> None:
    articles = [
        _article(
            "제5조(지원위원회의 설치)",
            "지원을 심의하기 위하여 지원위원회를 둔다. "
            "지원위원회의 사무를 처리하기 위하여 실무지원단을 설치할 수 있다.",
        )
    ]
    event = extract_committee_events("", articles)[0]
    assert event.support_organizations == ("실무지원단",)


def test_regional_scope_expansion_becomes_multi_instance_meeting_cost() -> None:
    articles = [
        _article(
            "제8조의3",
            "‘산업별 선도기업 등으로 산업별 혁신협의회를 구성하여’를 "
            "‘산업별ㆍ지역별 선도기업 등으로 산업별ㆍ지역별 혁신협의회를 구성하여’로 한다.",
            "개정",
        )
    ]
    # Assembly PDFs use curly double quotes in amendment commands.
    articles[0]["text"] = articles[0]["text"].replace("‘", "“").replace("’", "”")
    event = extract_committee_events("", articles)[0]
    plan = plan_committee_cost(event)
    assert event.name == "지역별혁신협의회"
    assert event.multiplicity == "multi_instance"
    assert plan.family == "multi_instance_meeting_allowance"
    assert plan.components[0].operands[0] == "설치기관 수"


def test_location_attached_to_creation_is_a_multiplier_not_flat_budget() -> None:
    articles = [
        _article(
            "제7조(안전심의위원회)",
            "각 시ㆍ도본부에 지역안전심의위원회를 둔다. "
            "구성과 운영은 대통령령으로 정한다.",
        )
    ]
    event = extract_committee_events("", articles)[0]
    plan = plan_committee_cost(event)
    assert event.multiplicity == "multi_instance"
    assert plan.family == "multi_instance_meeting_allowance"


def test_detailed_optional_subcommittee_is_a_cost_component() -> None:
    articles = [
        _article(
            "제10조(미래위원회)",
            "미래전략을 심의하기 위하여 미래위원회를 둔다. "
            "위원회는 20명 이내로 구성한다.",
        ),
        _article(
            "제11조(분과위원회)",
            "위원회는 분야별 분과위원회를 둘 수 있다. "
            "분과위원회는 위원회의 위원으로 구성하고 위원장이 소집한다.",
        ),
        _article("제12조(조사)", "정부는 실태를 조사할 수 있다."),
    ]
    event = extract_committee_events("", articles)[0]
    plan = plan_committee_cost(event)
    assert event.subordinate_bodies == ("분과위원회",)
    assert plan.family == "compound_committee_allowance"


def test_renamed_and_expanded_existing_committee_is_an_event() -> None:
    raw = (
        "제안이유 현행 규제개혁위원회의 명칭을 규제합리화위원회로 변경하고 "
        "민간위원 규모를 확대한다. 법률 제1호 "
        "제6조 중 “규제개혁위원회”를 “규제합리화위원회”로 한다."
    )
    articles = [
        _article(
            "제6조",
            "제6조 중 “규제개혁위원회”를 “규제합리화위원회”로 한다.",
            "개정",
        ),
        _article(
            "제25조",
            "제25조 중 “위원 20명”을 “위원 35명”으로 한다.",
            "개정",
        ),
    ]
    event = extract_committee_events(raw, articles)[0]
    plan = plan_committee_cost(event)
    assert event.name == "규제합리화위원회"
    assert event.change_kind == "membership_expansion_or_reorganization"
    assert plan.family == "multi_activity_meeting_allowance"


def test_optional_subordinate_is_kept_as_unpriced_candidate() -> None:
    articles = [
        _article(
            "제6조(전략위원회 설치)",
            "정책을 심의하기 위하여 전략위원회를 둔다. "
            "전략위원회에 실무위원회를 둘 수 있다.",
        )
    ]
    event = extract_committee_events("", articles)[0]
    plan = plan_committee_cost(event)
    assert event.subordinate_bodies == ()
    assert event.optional_subordinate_bodies == ("실무위원회",)
    assert plan.family == "meeting_allowance"
    optional = [value for value in plan.components if not value.required]
    assert [value.kind for value in optional] == ["subordinate_meeting_allowance"]


def test_standing_members_with_secretariat_form_a_composite_budget() -> None:
    articles = [
        _article(
            "제5조(국가회계위원회 설치)",
            "회계정책을 심의하기 위하여 국가회계위원회를 둔다.",
        ),
        _article(
            "제7조(위원회의 구성 등)",
            "위원장과 위원 1명은 상임으로 한다.",
        ),
        _article(
            "제9조(실무위원회)",
            "사항을 미리 검토하기 위하여 실무위원회를 둔다.",
        ),
        _article(
            "제10조(위원회의 사무국 등)",
            "위원회의 활동을 지원하기 위하여 사무국을 둔다.",
        ),
    ]
    event = extract_committee_events("", articles)[0]
    plan = plan_committee_cost(event)
    assert event.has_standing_members
    assert plan.family == "staffed_committee_support_bundle"
    assert [value.kind for value in plan.components] == [
        "standing_member_compensation",
        "main_meeting_allowance",
        "subordinate_meeting_allowance",
        "support_staff_compensation",
        "support_operating_expense",
    ]


def test_existing_committee_standing_member_replacement_is_recovered() -> None:
    raw = (
        "제안이유 현재 항공ㆍ철도사고조사위원회의 상임위원은 고위직 공무원이 겸하고 있음. "
        "이에 고위직 공무원의 상임위원 참여를 배제하려는 것임. "
        "법률 제1호 제6조제1항 중 2인은 상임으로 한다."
    )
    articles = [
        _article(
            "제6조(위원회의 구성)",
            "제6조제1항 중 위원 중 2인은 상임으로 한다.",
            "개정",
        )
    ]
    event = extract_committee_events(raw, articles)[0]
    plan = plan_committee_cost(event)
    assert event.name == "항공ㆍ철도사고조사위원회"
    assert event.change_kind == "standing_member_replacement"
    assert plan.family == "standing_member_replacement"


def test_root_named_professional_committee_is_not_its_own_subordinate() -> None:
    articles = [
        _article(
            "제6조(국가데이터전문위원회의 설치)",
            "중요 사항을 심의하기 위하여 국가데이터전문위원회"
            "(이하 “전문위원회”라 한다)를 둔다.",
        ),
        _article(
            "제7조(전문위원회의 구성 및 운영)",
            "전문위원회는 위원장 1명을 포함한 20명 이내로 구성한다.",
        ),
    ]
    event = extract_committee_events("", articles)[0]
    plan = plan_committee_cost(event)
    assert event.subordinate_bodies == ()
    assert event.optional_subordinate_bodies == ()
    assert plan.family == "meeting_allowance"


def test_fully_delegated_optional_subordinate_is_not_required() -> None:
    articles = [
        _article(
            "제6조(임금위원회의 설치)",
            "임금을 심의하기 위하여 임금위원회를 둔다.",
        ),
        _article(
            "제11조(소위원회)",
            "위원회는 9명 이내의 소위원회를 둘 수 있다. "
            "소위원회는 재적위원 과반수의 출석으로 개의한다.",
        ),
        _article(
            "제12조(실무협의회)",
            "위원장은 실무협의회를 둘 수 있다. "
            "실무협의회의 구성 및 운영은 위원회에서 정한다.",
        ),
    ]
    event = extract_committee_events("", articles)[0]
    plan = plan_committee_cost(event)
    assert event.subordinate_bodies == ("소위원회",)
    assert event.optional_subordinate_bodies == ("실무협의회",)
    assert plan.family == "compound_committee_allowance"
    assert [component.kind for component in plan.components] == [
        "main_meeting_allowance",
        "subordinate_meeting_allowance",
    ]


def test_local_executive_attached_body_is_multi_instance() -> None:
    articles = [
        _article(
            "제12조(지역위원회)",
            "시장ㆍ군수ㆍ구청장 소속으로 지역돌봄위원회를 둔다. "
            "지역돌봄위원회는 20명 이내로 구성한다.",
        )
    ]
    event = extract_committee_events("", articles)[0]
    assert event.multiplicity == "multi_instance"
    assert plan_committee_cost(event).family == "multi_instance_meeting_allowance"


def test_single_local_executive_attachment_is_not_multi_instance() -> None:
    articles = [
        _article(
            "제12조(산림복지심의위원회)",
            "통합특별시장 소속으로 산림복지심의위원회를 둔다. "
            "위원회는 이양된 산림복지사무를 심의한다.",
        )
    ]
    event = extract_committee_events("", articles)[0]
    assert event.multiplicity == "single"
    assert plan_committee_cost(event).family == "meeting_allowance"


def test_distributed_continuous_casework_uses_operating_baseline() -> None:
    articles = [
        _article(
            "제32조(시민고충처리위원회)",
            "인구 25만 이상의 지방자치단체는 시민고충처리위원회를 두어야 한다.",
        )
    ]
    event = extract_committee_events("", articles)[0]
    assert event.multiplicity == "multi_instance"
    assert plan_committee_cost(event).family == "multi_instance_operating_baseline"


def test_full_revision_clusters_incremental_children_and_support() -> None:
    raw = (
        "기관운영법 전부개정법률안 제안이유 현행 운영위원회의 독립성을 개편한다. "
        "법률 제1호 기관운영법 전부를 다음과 같이 개정한다."
    )
    articles = [
        _article(
            "제8조(운영위원회의 설치)",
            "사항을 심의하기 위하여 운영위원회"
            "(이하 “운영위원회”라 한다)를 둔다.",
        ),
        _article(
            "제16조(전문위원회)",
            "운영위원회는 전문위원회를 둘 수 있다.",
        ),
        _article(
            "제17조(소위원회)",
            "운영위원회는 소위원회를 둘 수 있다.",
        ),
        _article(
            "제18조(사무처)",
            "운영위원회에 사무처를 둔다.",
        ),
        _article(
            "제42조(임원추천위원회)",
            "각 기관에 임원추천위원회를 둔다.",
        ),
    ]
    events = extract_committee_events(raw, articles)
    assert [event.name for event in events] == ["운영위원회"]
    event = events[0]
    assert event.change_kind == "full_revision_reorganization"
    assert event.subordinate_bodies == ("전문위원회", "소위원회")
    assert event.support_organizations == ("사무처",)
    plan = plan_committee_cost(event)
    assert plan.family == "reorganized_committee_support_bundle"
    assert [component.kind for component in plan.components] == [
        "subordinate_operating_baseline",
        "support_operating_baseline",
    ]


def test_parliamentary_standing_committee_reference_is_not_target_staff() -> None:
    articles = [
        _article(
            "제7조(기후외교위원회)",
            "정책을 심의하기 위하여 외교부장관 소속으로 기후외교위원회를 둔다. "
            "위원회는 20명 이내의 위원으로 구성한다.",
        ),
        _article(
            "제8조(보고)",
            "외교부장관은 그 결과를 국회 소관 상임위원회에 보고하여야 한다.",
        ),
    ]
    event = extract_committee_events("", articles)[0]
    assert not event.has_standing_staff
    assert not event.has_standing_members
    assert plan_committee_cost(event).family == "meeting_allowance"


def test_mandatory_title_body_is_not_replaced_by_optional_regional_body() -> None:
    articles = [
        _article(
            "제8조(공공재생에너지위원회의 설치와 운영)",
            "사항을 심의하기 위하여 국무총리 소속으로 "
            "공공재생에너지위원회를 둔다. 위원회는 20명 이내로 구성한다. "
            "지방자치단체의 장은 조례로 정하는 바에 따라 "
            "지역공공재생에너지위원회를 둘 수 있다.",
        )
    ]
    events = extract_committee_events("", articles)
    assert [event.name for event in events] == ["공공재생에너지위원회"]
    assert plan_committee_cost(events[0]).family == "meeting_allowance"
