from backend.erce_web.llm_profiles import (
    SOLAR_PRO2_PROFILE_ID,
    dedicated_staff_value_prompt,
    normalize_response,
    research_direct_prompt,
    system_instruction,
    use_unique_prequalified_organization_value,
)


def test_solar_pro2_event_profile_is_task_specific() -> None:
    instruction = system_instruction(
        SOLAR_PRO2_PROFILE_ID,
        "법안의 '추가 공공재정 비용사건'을 구조화한다.",
    )
    assert "동일 object" in instruction
    assert "organization_change" in instruction
    assert "committee_operation" in instruction
    assert "정답 금액" in instruction


def test_solar_pro2_variable_profile_protects_cadence_semantics() -> None:
    instruction = system_instruction(
        SOLAR_PRO2_PROFILE_ID,
        "빈 변수값을 채울 공식 선례 선정자다.",
    )
    assert "frequency" in instruction
    assert "사건 발생량" in instruction
    assert "option_id" in instruction


def test_unknown_profile_does_not_change_common_prompting() -> None:
    assert system_instruction("", "비용추계 선례를 선택하는 reranker다.") == ""
    assert (
        use_unique_prequalified_organization_value(
            "",
            candidate_count=1,
            target_organization_form="legislative_committee",
        )
        is False
    )


def test_solar_uses_one_prequalified_known_form_without_rejudging_it() -> None:
    assert (
        use_unique_prequalified_organization_value(
            SOLAR_PRO2_PROFILE_ID,
            candidate_count=1,
            target_organization_form="legislative_committee",
        )
        is True
    )
    assert (
        use_unique_prequalified_organization_value(
            SOLAR_PRO2_PROFILE_ID,
            candidate_count=2,
            target_organization_form="legislative_committee",
        )
        is False
    )
    assert (
        use_unique_prequalified_organization_value(
            SOLAR_PRO2_PROFILE_ID,
            candidate_count=1,
            target_organization_form="unknown",
        )
        is False
    )


def test_solar_builds_direct_value_prompt_only_for_dedicated_staff() -> None:
    candidates = [
        {
            "bill_no": "1",
            "bill_name": "공공기관법안",
            "precedent_context": "공공기관 직원 인건비",
            "components": [],
        }
    ]
    prompt = dedicated_staff_value_prompt(
        SOLAR_PRO2_PROFILE_ID,
        target_events=[
            {
                "action": "지정",
                "object": "여성농어업인담당관",
                "explanation": "기존 직원 중 담당관 지정",
            }
        ],
        candidates=candidates,
    )
    assert prompt is not None
    assert "단일 reranking" in prompt
    assert '"bill_no": "1"' in prompt
    assert (
        dedicated_staff_value_prompt(
            SOLAR_PRO2_PROFILE_ID,
            target_events=[
                {
                    "action": "신설",
                    "object": "지방법원",
                    "explanation": "법원 조직 신설",
                }
            ],
            candidates=candidates,
        )
        is None
    )


def test_solar_research_reranker_uses_small_recall_window() -> None:
    candidates = [
        {"candidate_id": f"C{index}", "bill_name": f"법안{index}"}
        for index in range(12)
    ]
    result = research_direct_prompt(
        SOLAR_PRO2_PROFILE_ID,
        event={"object": "국립대학병원 종합계획"},
        source_text="국립대학병원 발전 종합계획을 수립한다.",
        candidates=candidates,
    )
    assert result is not None
    prompt, window = result
    assert len(window) == 8
    assert "C7" in prompt
    assert "C8" not in prompt
    assert "target_relation_type" in prompt
    assert "artifact_purpose_match" in prompt
    assert "same_named_entity" in prompt


def test_solar_wraps_one_event_and_drops_only_ungrounded_quotes() -> None:
    prompt = """법안의 '추가 공공재정 비용사건'을 구조화한다.
[S001 | 제3조 | 신설]
위원회를 둔다.
[S002 | 제4조 | 신설]
위원은 20명으로 구성한다.
"""
    payload = {
        "segment_ids": ["S001", "S002"],
        "event_type": "committee_operation",
        "quotes": ["위원회를 둔다.", "위원은 21명으로 구성한다."],
    }
    result = normalize_response(SOLAR_PRO2_PROFILE_ID, prompt, payload)
    assert isinstance(result, dict)
    assert len(result["events"]) == 1
    assert result["events"][0]["quotes"] == ["위원회를 둔다."]


def test_solar_merges_jurisdiction_table_into_new_institution() -> None:
    prompt = """법안의 '추가 공공재정 비용사건'을 구조화한다.
[S001 | 별표1 | 신설]
동부지방법원을 신설한다.
[S002 | 별표2 | 개정]
동부지방법원 관할구역을 정한다.
[S003 | 별표3 | 개정]
서부고등법원 관할구역을 변경한다.
"""
    payload = {
        "events": [
            {
                "segment_ids": ["S001"],
                "article_refs": ["별표1"],
                "quotes": ["동부지방법원을 신설한다."],
                "event_type": "organization_change",
                "object": "동부지방법원",
            },
            {
                "segment_ids": ["S002"],
                "article_refs": ["별표2"],
                "quotes": ["동부지방법원 관할구역을 정한다."],
                "event_type": "organization_change",
                "object": "동부지방법원 관할구역",
            },
            {
                "segment_ids": ["S003"],
                "article_refs": ["별표3"],
                "quotes": ["서부고등법원 관할구역을 변경한다."],
                "event_type": "organization_change",
                "object": "서부고등법원 관할구역",
            },
        ]
    }
    result = normalize_response(SOLAR_PRO2_PROFILE_ID, prompt, payload)
    assert len(result["events"]) == 1
    assert result["events"][0]["segment_ids"] == ["S001", "S002"]
    assert result["events"][0]["article_refs"] == ["별표1", "별표2"]


def test_solar_routes_subordinate_policy_body_to_one_committee_event() -> None:
    prompt = """법안의 '추가 공공재정 비용사건'을 구조화한다.
[S001 | 제6조 | 제정]
임금에 관한 중요사항을 심의하기 위하여 인사혁신처 소속으로 임금위원회를 둔다.
[S002 | 제8조 | 제정]
위원회는 위원장 1명을 포함하여 21명의 위원으로 구성한다.
[S003 | 제10조 | 제정]
위원장은 위원회의 회의를 소집한다.
[S004 | 제11조 | 제정]
위원회는 9명 이내의 소위원회를 둘 수 있다.
[S005 | 제12조 | 제정]
위원장은 별도의 실무협의회를 둘 수 있다.
[S006 | 제15조 | 제정]
위원회의 회의에 출석한 위원에게 수당을 지급할 수 있다.
"""
    payload = {
        "events": [
            {
                "segment_ids": ["S001"],
                "article_refs": ["제6조"],
                "quotes": [
                    "임금에 관한 중요사항을 심의하기 위하여 인사혁신처 소속으로 임금위원회를 둔다."
                ],
                "event_type": "organization_change",
                "cost_mechanism": "organization_change",
                "action": "설치",
                "object": "임금위원회",
            },
            {
                "segment_ids": ["S002"],
                "article_refs": ["제8조"],
                "quotes": [
                    "위원회는 위원장 1명을 포함하여 21명의 위원으로 구성한다."
                ],
                "event_type": "committee_operation",
                "object": "위원회 구성원",
            },
            {
                "segment_ids": ["S003"],
                "article_refs": ["제10조"],
                "quotes": ["위원장은 위원회의 회의를 소집한다."],
                "event_type": "committee_operation",
                "object": "위원회 회의",
            },
            {
                "segment_ids": ["S004"],
                "article_refs": ["제11조"],
                "quotes": ["위원회는 9명 이내의 소위원회를 둘 수 있다."],
                "event_type": "committee_operation",
                "object": "소위원회",
            },
            {
                "segment_ids": ["S005"],
                "article_refs": ["제12조"],
                "quotes": ["위원장은 별도의 실무협의회를 둘 수 있다."],
                "event_type": "committee_operation",
                "object": "실무협의회",
            },
            {
                "segment_ids": ["S006"],
                "article_refs": ["제15조"],
                "quotes": [
                    "위원회의 회의에 출석한 위원에게 수당을 지급할 수 있다."
                ],
                "event_type": "subsidy",
                "object": "수당",
            },
        ]
    }
    result = normalize_response(SOLAR_PRO2_PROFILE_ID, prompt, payload)
    assert isinstance(result, dict)
    assert len(result["events"]) == 2
    committee = result["events"][0]
    assert committee["event_type"] == "committee_operation"
    assert committee["cost_mechanism"] == "internal_administration"
    assert committee["segment_ids"] == ["S001", "S002", "S003", "S004", "S006"]
    assert committee["article_refs"] == ["제6조", "제8조", "제10조", "제11조", "제15조"]
    assert result["events"][1]["object"] == "실무협의회"


def test_solar_does_not_route_independently_staffed_commission_to_committee() -> None:
    prompt = """법안의 '추가 공공재정 비용사건'을 구조화한다.
[S001 | 제3조 | 제정]
권리구제에 관한 사항을 심의하기 위하여 국무총리 소속으로 권리위원회를 둔다.
[S002 | 제20조 | 제정]
위원회에 사무처를 둔다.
"""
    payload = {
        "events": [
            {
                "segment_ids": ["S001"],
                "article_refs": ["제3조"],
                "quotes": [
                    "권리구제에 관한 사항을 심의하기 위하여 국무총리 소속으로 권리위원회를 둔다."
                ],
                "event_type": "organization_change",
                "cost_mechanism": "organization_change",
                "object": "권리위원회",
            }
        ]
    }
    result = normalize_response(SOLAR_PRO2_PROFILE_ID, prompt, payload)
    assert result["events"][0]["event_type"] == "organization_change"
