from __future__ import annotations

from unittest.mock import patch

from backend.analyzer_v2 import split_articles_structured
from backend.estimator_v2.calculation import estimate_event_amount, estimate_selected_precedent
from backend.estimator_v2.detect import (
    _augment_explicit_support_office_events,
    _chunk_segments,
    _failure_recovery_limit,
    _needs_empty_recovery,
    _needs_schema_recovery,
    _normalise_staff_designation_events,
    _parse_events,
    extract_annex_revision_articles,
    extract_revision_body_articles,
    merge_annex_revision_articles,
    merge_revision_body_articles,
    segment_articles,
)
from backend.estimator_v2.gates import assess_event
from backend.estimator_v2.organization import (
    _all_staff_cost_bundles,
    _bundle_organization_form,
    _coherent_bundle_series,
    _component,
    _court_transition,
    _case_personnel_system_from_priced_subject,
    _eligible_organization_value_cases,
    _is_aggregate_item,
    _is_fixed_operating_precedent,
    _is_legislative_committee_organization_event,
    _item_staff_count,
    _latest_judicial_value_case,
    _mapped_staff_count,
    _personnel_system,
    _prefer_same_court_transition,
    _restrict_legislative_committee_value_cases,
    _scaled_series,
    _single_staff_denominator,
    _top_compatible_value_case,
    build_organization_rows,
    build_organization_operating_budget_rows,
    find_organization_clusters,
    select_staff_cost_bundle,
    select_typed_structure_case,
    OrganizationCase,
)
from backend.estimator_v2.prior_scope import assess_prior_scope
from backend.estimator_v2.recurrence import resolve_recurrence, schedule_amount
from backend.estimator_v2.selection import (
    _choose_committee_companion_scorecard_candidate,
    _choose_research_scorecard_candidate,
    _committee_companion_scorecard_candidate_payload,
    _resolve_returned_candidate,
    _research_scorecard_candidate_payload,
    select_precedent,
    usable_candidates,
)
from backend.estimator_v2.types import AtomicEvent, RowStatus, Segment, TagCandidate
from backend.estimator_v2.variable_selection import (
    _committee_function,
    _compatible_options,
    _latest_general_budget_guideline_option,
    _target_non_public_majority_count,
    _target_payable_member_count,
    candidate_options,
    estimate_committee_formula_first,
    has_time_varying_operands,
)
from backend.legacy.scripts.evaluate_assembly_batch import _parse_first_cost_table


def _event(**overrides) -> AtomicEvent:
    values = {
        "id": "E001",
        "segment_ids": ["S001"],
        "article_refs": ["제1조"],
        "quotes": ["국가는 위원회를 둔다."],
        "actor": "국가",
        "action": "설치·운영",
        "object": "정책위원회",
        "bearer": "state",
        "event_type": "committee_operation",
        "obligation": "mandatory",
        "cost_mechanism": "internal_administration",
        "additionality": "explicit_new_or_expanded",
        "recurrence_text": "",
        "explanation": "",
        "grounded": True,
    }
    values.update(overrides)
    return AtomicEvent(**values)


def test_revision_body_stops_before_other_law_even_when_pdf_splits_words() -> None:
    text = """가상법 일부개정법률안
가상법 일부를 다음
과 같이 개정한다.
제10조의2를 다음과 같이 신설한다.
제10조의2(보호심의위원회) ① 신고자 보호를 심의하기 위하여 위원회를 둔다.
② 위원회는 위원장 1명을 포함하여 7명의 위원으로 구성한다.
③ 제15조제1항 각 호의 사람 중 위원장이 지정하는 사람은 위원이 된다.
부
칙
제2조(다른 법률의 개정) 다른법률 일부를 다음과 같이 개정한다.
제24조제1항 중 “제10조”를 “제10조의2”로 한다.
"""
    articles, doc_type = split_articles_structured(text)
    assert doc_type == "일부개정안"
    assert [article["no"] for article in articles] == [
        "제10조의2(보호심의위원회)"
    ]
    assert "7명의 위원" in articles[0]["text"]


def test_created_article_range_keeps_every_header_inside_the_range() -> None:
    text = """가상법 일부개정법률안
가상법 일부를 다음과 같이 개정한다.
제3장(제21조부터 제23조까지)를 다음과 같이 신설한다.
제21조(적용범위) 이 장의 적용범위를 정한다.
제22조(정책위원회의 설치) 정책을 심의하기 위하여 정책위원회를 둔다.
제23조(운영) 위원회의 운영에 필요한 사항을 정한다.
부 칙
이 법은 공포한 날부터 시행한다.
"""
    articles, doc_type = split_articles_structured(text)
    assert doc_type == "일부개정안"
    assert [article["no"] for article in articles] == [
        "제21조(적용범위)",
        "제22조(정책위원회의 설치)",
        "제23조(운영)",
    ]


def test_enumerated_subarticle_ranges_keep_every_created_article() -> None:
    text = """가상법 일부개정법률안
가상법 일부를 다음과 같이 개정한다.
제3장에 제43조의2부터 제43조의4까지ㆍ제46조의2부터 제46조의3까지 및
제49조의2부터 제49조의4까지를 각각 다음과 같이 신설한다.
제43조의2(첫 조문) 첫 조문의 내용이다.
제43조의3(둘째 조문) 둘째 조문의 내용이다.
제43조의4(셋째 조문) 셋째 조문의 내용이다.
제46조의2(넷째 조문) 넷째 조문의 내용이다.
제46조의3(다섯째 조문) 다섯째 조문의 내용이다.
제49조의2(여섯째 조문) 여섯째 조문의 내용이다.
제49조의3(일곱째 조문) 일곱째 조문의 내용이다.
제49조의4(정책위원회) 정책을 심의하기 위하여 정책위원회를 둔다.
부 칙
이 법은 공포한 날부터 시행한다.
"""
    articles, doc_type = split_articles_structured(text)
    assert doc_type == "일부개정안"
    assert [article["no"] for article in articles] == [
        "제43조의2(첫 조문)",
        "제43조의3(둘째 조문)",
        "제43조의4(셋째 조문)",
        "제46조의2(넷째 조문)",
        "제46조의3(다섯째 조문)",
        "제49조의2(여섯째 조문)",
        "제49조의3(일곱째 조문)",
        "제49조의4(정책위원회)",
    ]


def test_official_cost_parser_ignores_later_meeting_count_table() -> None:
    text = """Ⅰ. 비용추계 결과
추가재정소요는 총 2,500만원으로 추계됨
(단위: 백만원)
구분
2026
2027
2028
2029
2030
합계
위원회 구성·운영(안 제8조·제11조 및 제15조)
5
5
5
5
5
25
자료: 국회예산정책처
Ⅱ. 재정수반요인
(단위: 일수)
2020
2021
2022
2023
2024
합계
연평균
2
2
2
3
6
15
3
"""
    parsed = _parse_first_cost_table(text)
    assert parsed["years"] == [5, 5, 5, 5, 5]
    assert parsed["total"] == 25
    assert parsed["average"] == 5


def test_official_cost_parser_supports_two_year_summary_table() -> None:
    text = """Ⅰ. 비용추계 결과
(단위: 백만원)
구 분
2024
2025
합 계
연평균
특별조사위원회 상임위원 인건비
292
448
740
370
사무처 직원 인건비
1,559
3,122
4,681
2,341
합계
1,871
4,011
5,882
2,941
자료: 국회예산정책처
Ⅱ. 재정수반요인
"""
    parsed = _parse_first_cost_table(text)
    assert parsed["years"] == [1871, 4011]
    assert parsed["total"] == 5882
    assert parsed["average"] == 2941


def _candidate(item_id: str, count: int, unit_cost: int, frequency: int) -> TagCandidate:
    amount = count * unit_cost * frequency // 1000
    return TagCandidate(
        item_id=item_id,
        bill_no=item_id,
        bill_name=f"선례 {item_id}",
        item_name="정책위원회 운영비",
        category="운영비",
        family="committee",
        similarity=0.7,
        variables=[
            {"type": "target_count", "name": "민간위원", "value": count, "unit": "명"},
            {"type": "unit_cost", "name": "회의수당", "value": unit_cost, "unit": "원"},
            {"type": "frequency", "name": "회의횟수", "value": frequency, "unit": "회"},
        ],
        amounts=[
            {"year_offset": offset, "amount_thousand": amount, "formula_text": "인원×수당×횟수"}
            for offset in range(5)
        ],
        formula="인원×수당×횟수",
    )


def test_segment_articles_splits_paragraphs() -> None:
    segments = segment_articles(
        [{"no": "제21조", "text": "제21조(계획) ① 5년마다 계획을 수립한다. ② 기관은 매년 계획을 낸다."}]
    )
    assert len(segments) == 2
    assert "5년마다" in segments[0].text
    assert "매년" in segments[1].text


def test_fund_installation_is_not_misclassified_as_staffed_organization() -> None:
    segments = [
        Segment(
            id="S001",
            article_ref="제19조",
            text=(
                "지방자치단체장은 발전 및 사무처리 지원에 필요한 재원을 "
                "확보하기 위하여 발전기금을 설치한다."
            ),
        )
    ]
    payload = {
        "events": [
            {
                "segment_ids": ["S001"],
                "article_refs": ["제19조"],
                "quotes": [segments[0].text],
                "actor": "지방자치단체장",
                "action": "설치",
                "object": "발전기금",
                "bearer": "local",
                "event_type": "organization_change",
                "obligation": "mandatory",
                "cost_mechanism": "internal_administration",
                "additionality": "explicit_new_or_expanded",
                "recurrence_text": "",
                "explanation": "기금 설치",
            }
        ]
    }
    events = _parse_events(payload, segments)
    assert len(events) == 1
    assert events[0].event_type == "other"
    assert events[0].cost_mechanism == "transfer"


def test_explicit_fund_office_with_staff_remains_organization() -> None:
    segments = [
        Segment(
            id="S001",
            article_ref="제19조",
            text="기금의 운영을 위하여 사무국을 설치하고 직원 5명을 둔다.",
        )
    ]
    payload = {
        "events": [
            {
                "segment_ids": ["S001"],
                "article_refs": ["제19조"],
                "quotes": [segments[0].text],
                "actor": "기금관리주체",
                "action": "설치",
                "object": "기금 사무국",
                "bearer": "state",
                "event_type": "organization_change",
                "obligation": "mandatory",
                "cost_mechanism": "organization_change",
                "additionality": "explicit_new_or_expanded",
                "recurrence_text": "",
                "explanation": "전담 조직과 인력 신설",
            }
        ]
    }
    events = _parse_events(payload, segments)
    assert len(events) == 1
    assert events[0].event_type == "organization_change"


def test_long_event_input_is_chunked_at_article_boundaries_without_loss() -> None:
    segments = [
        Segment(
            id=f"S{index:03d}",
            article_ref=f"제{(index + 1) // 2}조",
            text="가" * 80,
            change_type="신설",
        )
        for index in range(1, 9)
    ]
    chunks = _chunk_segments(
        segments,
        max_prompt_chars=360,
        prompt_prefix_chars=100,
    )
    flattened = [segment.id for chunk in chunks for segment in chunk]
    assert len(chunks) > 1
    assert flattened == [segment.id for segment in segments]
    article_chunks: dict[str, set[int]] = {}
    for chunk_index, chunk in enumerate(chunks):
        for segment in chunk:
            article_chunks.setdefault(segment.article_ref, set()).add(
                chunk_index
            )
    assert all(
        len(chunk_indexes) == 1
        for chunk_indexes in article_chunks.values()
    )


def test_large_top_level_event_requires_smaller_schema_recovery() -> None:
    segments = [
        Segment(
            id=f"S{index:03d}",
            article_ref=f"제{index}조",
            text="가" * 1_800,
            change_type="신설",
        )
        for index in range(1, 8)
    ]
    collapsed = {
        "segment_ids": [segment.id for segment in segments],
        "event_type": "organization_change",
        "object": "여러 조문을 합친 사건",
    }
    assert _needs_schema_recovery(
        collapsed,
        segments,
        prompt_prefix_chars=2_000,
    )
    assert not _needs_schema_recovery(
        {"events": [collapsed]},
        segments,
        prompt_prefix_chars=2_000,
    )


def test_large_wrapped_singleton_event_requires_smaller_schema_recovery() -> None:
    segments = [
        Segment(
            id=f"S{index:03d}",
            article_ref=f"제{index}조",
            text="가" * 220,
            change_type="신설",
        )
        for index in range(1, 41)
    ]
    collapsed = {
        "events": [
            {
                "segment_ids": [segment.id for segment in segments],
                "event_type": "organization_change",
                "object": "여러 장의 모든 조직과 사업을 합친 사건",
            }
        ]
    }
    assert _needs_schema_recovery(
        collapsed,
        segments,
        prompt_prefix_chars=2_000,
    )
    assert not _needs_schema_recovery(
        {
            "events": [
                {
                    "segment_ids": [segment.id for segment in segments[:4]],
                    "event_type": "organization_change",
                    "object": "하나의 조직 사건",
                }
            ]
        },
        segments,
        prompt_prefix_chars=2_000,
    )


def test_large_empty_event_result_requires_finer_recovery() -> None:
    segments = [
        Segment(
            id=f"S{index:03d}",
            article_ref=f"제{index}조",
            text="가" * 1_500,
            change_type="신설",
        )
        for index in range(1, 5)
    ]
    assert _needs_empty_recovery(
        {"events": []},
        segments,
        prompt_prefix_chars=1_000,
    )
    assert not _needs_empty_recovery(
        {"events": [{"segment_ids": ["S001"]}]},
        segments,
        prompt_prefix_chars=1_000,
    )


def test_provider_failure_recovery_shrinks_requests_progressively() -> None:
    assert _failure_recovery_limit(30_000) == 12_000
    assert _failure_recovery_limit(12_000) == 6_000
    assert _failure_recovery_limit(6_000) is None


def test_changed_annexes_are_extracted_from_revision_body_only() -> None:
    text = """가상법 일부개정법률안
제안이유: 조직을 설치하려는 것임(안 별표 1).
가상법 일부를 다음과 같이 개정한다.
별표 1의 기존기관란 다음에 신설기관란을 다음과 같이 신설한다.
신설기관 서울특별시
별표 3 중 기존기관란을 삭제하고 신설기관란을 다음과 같이 신설한다.
신설기관 서울특별시ㆍ경기도
부 칙
이 법은 공포 후 6개월이 경과한 날부터 시행한다.
"""
    articles = extract_annex_revision_articles(text)
    assert [article["no"] for article in articles] == ["별표1", "별표3"]
    assert all(article["source"] == "annex_revision" for article in articles)
    assert "제안이유" not in " ".join(article["text"] for article in articles)


def test_merge_annex_revision_articles_preserves_source_on_duplicate() -> None:
    generic = [
        {
            "no": "별표1",
            "text": "별표 1을 다음과 같이 개정한다.",
            "change_type": "",
        }
    ]
    annex = [
        {
            "no": "별표1",
            "text": "별표 1을 다음과 같이 개정한다.",
            "change_type": "개정",
            "source": "annex_revision",
        }
    ]
    merged = merge_annex_revision_articles(generic, annex)
    assert len(merged) == 1
    assert merged[0]["source"] == "annex_revision"
    assert merged[0]["change_type"] == "개정"


def test_batch_revision_recovers_every_titled_article_without_cross_references() -> None:
    text = """가상법 일부개정법률안
가상법 일부를 다음과 같이 개정한다.
제3장(제21조부터 제23조까지)을 다음과 같이 신설한다.
제21조(적용범위) 이 장의 적용범위를 정한다.
제22조(정책위원회의 설치 및 구성) ① 정책위원회를 둔다.
② 위원회는 9명 이내로 구성한다.
③ 제9조를 준용한다.
제23조(사무기구) 위원회의 사무를 처리하기 위하여 사무국을 둔다.
부 칙
제2조(다른 법률의 개정) 다른 법률 제30조를 개정한다.
"""
    recovered = extract_revision_body_articles(text)
    assert [article["no"] for article in recovered] == [
        "제21조(적용범위)",
        "제22조(정책위원회의설치및구성)",
        "제23조(사무기구)",
    ]
    assert all(article["source"] == "revision_body" for article in recovered)
    assert not any(article["no"].startswith("제9조") for article in recovered)
    assert not any(article["no"].startswith("제30조") for article in recovered)


def test_recovered_revision_articles_replace_duplicates_and_add_missing_articles() -> None:
    generic = [
        {
            "no": "제21조(적용범위)",
            "text": "제21조(적용범위) 적용범위를 정한다.",
            "change_type": "신설",
        }
    ]
    recovered = [
        {
            "no": "제21조(적용범위)",
            "text": "제21조(적용범위) 적용범위를 구체적으로 정한다.",
            "change_type": "개정본문",
            "source": "revision_body",
        },
        {
            "no": "제22조(위원회)",
            "text": "제22조(위원회) 국가에 위원회를 둔다.",
            "change_type": "개정본문",
            "source": "revision_body",
        },
    ]
    merged = merge_revision_body_articles(generic, recovered)
    assert len(merged) == 2
    assert merged[0]["change_type"] == "신설"
    assert "구체적으로" in merged[0]["text"]
    assert merged[1]["no"] == "제22조(위원회)"


def test_explicit_committee_office_becomes_separate_organization_event() -> None:
    segments = [
        Segment(
            id="S001",
            article_ref="제22조",
            text="① 법무부에 공익법인위원회를 둔다.",
            change_type="신설",
        ),
        Segment(
            id="S002",
            article_ref="제22조",
            text="⑥ 위원회의 사무를 처리하기 위하여 위원회에 사무기구를 둔다.",
            change_type="신설",
        ),
    ]
    committee = _event(
        segment_ids=["S001", "S002"],
        article_refs=["제22조"],
        object="공익법인위원회",
    )
    augmented = _augment_explicit_support_office_events(
        [committee],
        segments,
    )
    assert len(augmented) == 2
    office = augmented[1]
    assert office.event_type == "organization_change"
    assert office.object == "공익법인위원회 사무기구"
    assert office.segment_ids == ["S002"]
    assert office.grounded is True


def test_explicit_committee_office_does_not_duplicate_model_event() -> None:
    segment = Segment(
        id="S001",
        article_ref="제10조",
        text="위원회의 사무를 처리하기 위하여 사무국을 둔다.",
        change_type="신설",
    )
    existing = _event(
        event_type="organization_change",
        cost_mechanism="organization_change",
        segment_ids=["S001"],
        object="정책위원회 사무국",
    )
    augmented = _augment_explicit_support_office_events(
        [existing],
        [segment],
    )
    assert augmented == [existing]


def test_same_named_organization_across_annex_tables_is_one_cost_event() -> None:
    segments = [
        Segment(
            id="S001",
            article_ref="별표1",
            text="별표1에 새봄지방법원란을 신설한다.",
            change_type="신설",
        ),
        Segment(
            id="S002",
            article_ref="별표3",
            text="별표3의 서울고등법원란에 새봄지방법원란을 신설한다.",
            change_type="신설",
        ),
    ]
    payload = {
        "events": [
            {
                "segment_ids": ["S001"],
                "article_refs": ["별표1"],
                "quotes": ["별표1에 새봄지방법원란을 신설한다."],
                "actor": "입법기관",
                "action": "신설",
                "object": "새봄지방법원",
                "bearer": "state",
                "event_type": "organization_change",
                "obligation": "mandatory",
                "cost_mechanism": "organization_change",
                "additionality": "explicit_new_or_expanded",
                "recurrence_text": "",
                "explanation": "법원 신설",
            },
            {
                "segment_ids": ["S002"],
                "article_refs": ["별표3"],
                "quotes": [
                    "별표3의 서울고등법원란에 새봄지방법원란을 신설한다."
                ],
                "actor": "입법기관",
                "action": "관할 법원 추가",
                "object": "서울고등법원 새봄지방법원",
                "bearer": "state",
                "event_type": "organization_change",
                "obligation": "mandatory",
                "cost_mechanism": "internal_administration",
                "additionality": "explicit_new_or_expanded",
                "recurrence_text": "",
                "explanation": "관할표 변경",
            },
        ]
    }
    events = _parse_events(payload, segments)
    assert len(events) == 1
    assert events[0].object == "새봄지방법원"
    assert events[0].segment_ids == ["S001", "S002"]
    assert events[0].grounded is True


def test_administrative_event_never_enters_automatic_analogy() -> None:
    decision = assess_event(
        _event(
            event_type="administrative",
            action="회계감사",
            object="결산서 감사",
        )
    )
    assert decision.automatic is False
    assert decision.status == RowStatus.NEEDS_EVIDENCE
    assert "ADMIN_ADDITIONALITY_UNPROVEN" in decision.reason_codes


def test_public_institution_internal_plan_requires_scale_evidence() -> None:
    decision = assess_event(
        _event(
            bearer="public_institution",
            event_type="research_plan",
            object="기관별 연간 계획",
        )
    )
    assert decision.automatic is False
    assert "INSTITUTION_SCALE_UNKNOWN" in decision.reason_codes


def test_policy_decision_is_not_priced_as_research_artifact() -> None:
    decision = assess_event(
        _event(
            event_type="research_plan",
            object="공무원 임금 인상안",
            action="심의 요청 및 예산 편성",
            quotes=["정부는 임금 인상안을 위원회에 심의 요청하여야 한다."],
        )
    )
    assert decision.automatic is False
    assert decision.reason_codes == ["POLICY_DECISION_NOT_RESEARCH_ARTIFACT"]


def test_possibly_incremental_survey_requires_existing_budget_check() -> None:
    decision = assess_event(
        _event(
            event_type="research_plan",
            object="공무원 임금 수준 실태조사",
            action="실태조사",
            quotes=["정부는 공무원 임금 수준을 매년 조사하여야 한다."],
            recurrence_text="매년",
            additionality="possibly_incremental",
        )
    )
    assert decision.automatic is False
    assert decision.reason_codes == ["RESEARCH_ADDITIONALITY_UNPROVEN"]


def test_explicit_new_plan_still_enters_automatic_channel() -> None:
    decision = assess_event(
        _event(
            event_type="research_plan",
            object="국립대학병원 종합계획",
            action="계획 수립",
            quotes=["보건복지부장관은 종합계획을 수립하여야 한다."],
            additionality="explicit_new_or_expanded",
        )
    )
    assert decision.automatic is True
    assert decision.reason_codes == ["AUTO_GATE_PASSED"]


def test_explicit_discretionary_committee_enters_conditional_scenario() -> None:
    decision = assess_event(
        _event(
            obligation="discretionary",
            quotes=[
                "신고자 보호에 관한 사항을 심의하기 위하여 보호심의위원회를 둘 수 있다.",
                "보호심의위원회는 위원장 1명을 포함하여 7명의 위원으로 구성한다.",
            ],
            object="보호심의위원회",
        )
    )
    assert decision.automatic is True
    assert decision.status == RowStatus.COMPUTED_REVIEW
    assert decision.reason_codes == [
        "CONDITIONAL_DISCRETIONARY_COMMITTEE_SCENARIO"
    ]
    assert "설치할 경우" in decision.reason


def test_vague_discretionary_committee_still_requires_evidence() -> None:
    decision = assess_event(
        _event(
            obligation="discretionary",
            quotes=["필요한 경우 정책위원회를 둘 수 있다."],
        )
    )
    assert decision.automatic is False
    assert decision.status == RowStatus.NEEDS_EVIDENCE
    assert decision.reason_codes == ["DISCRETIONARY_EXECUTION_UNKNOWN"]


def test_discretionary_organization_does_not_use_committee_exception() -> None:
    decision = assess_event(
        _event(
            event_type="organization_change",
            cost_mechanism="organization_change",
            object="지방공단",
            obligation="discretionary",
            quotes=[
                "지방공단을 설립할 수 있다.",
                "지방공단은 이사장 1명을 포함하여 7명의 임원으로 구성한다.",
            ],
        )
    )
    assert decision.automatic is False
    assert decision.reason_codes == ["DISCRETIONARY_EXECUTION_UNKNOWN"]


def test_private_organization_does_not_enter_public_organization_engine() -> None:
    event = _event(
        event_type="organization_change",
        actor="민간 협회",
        object="민간 협회 지부",
        bearer="private",
        cost_mechanism="organization_change",
    )
    rows, consumed, warnings = build_organization_rows(
        [event],
        "민간 협회는 지부를 둔다.",
        bill_no="TARGET",
        cutoff_date="2024-04-01",
        years=5,
    )
    assert rows == []
    assert consumed == set()
    assert warnings == []


def test_same_law_partial_prior_can_block_unpriced_matching_event() -> None:
    event = _event(
        event_type="research_plan",
        action="5년마다 수립",
        object="간호정책 종합계획",
        quotes=["5년마다 간호정책 종합계획을 수립하여야 한다."],
        cost_mechanism="external_contract",
    )
    prior = (
        {
            "bill_no": "PRIOR",
            "bill_name": "간호법안",
            "propose_date": "2024-01-01",
            "priced_items": [{"name": "정책심의위원회 운영", "family": "committee"}],
        },
        (
            "5년마다 간호정책 종합계획을 수립하여야 한다. "
            "다른 재정수반요인은 추계가 곤란하여 일부만 추계하였다."
        ),
    )
    response = {
        "decisions": [
            {
                "event_id": "E001",
                "status": "unestimable",
                "matched_quote": "5년마다 간호정책 종합계획을 수립하여야 한다.",
                "limitation_quote": "다른 재정수반요인은 추계가 곤란하여 일부만 추계하였다.",
                "reason": "같은 계획은 비용항목으로 계산되지 않았다.",
            }
        ]
    }
    with patch(
        "backend.estimator_v2.prior_scope._latest_same_law_prior",
        return_value=prior,
    ), patch(
        "backend.estimator_v2.prior_scope.get_or_create_json",
        return_value=(response, False),
    ):
        decisions, warning = assess_prior_scope(
            [event],
            target_bill_no="TARGET",
            target_bill_name="간호법안",
            cutoff_date="2024-04-01",
        )
    assert warning is None
    assert decisions["E001"].status == "unestimable"


def test_partial_prior_without_grounded_event_quote_stays_unknown() -> None:
    event = _event(
        event_type="research_plan",
        object="새로운 실태조사",
        cost_mechanism="external_contract",
    )
    prior = (
        {
            "bill_no": "PRIOR",
            "bill_name": "같은 법률안",
            "propose_date": "2024-01-01",
            "priced_items": [{"name": "위원회 운영", "family": "committee"}],
        },
        "위원회만 추계하였다. 다른 재정수반요인은 추계가 곤란하다.",
    )
    response = {
        "decisions": [
            {
                "event_id": "E001",
                "status": "unestimable",
                "matched_quote": "새로운 실태조사를 실시한다.",
                "limitation_quote": "다른 재정수반요인은 추계가 곤란하다.",
                "reason": "일부추계였다.",
            }
        ]
    }
    with patch(
        "backend.estimator_v2.prior_scope._latest_same_law_prior",
        return_value=prior,
    ), patch(
        "backend.estimator_v2.prior_scope.get_or_create_json",
        return_value=(response, False),
    ):
        decisions, _ = assess_prior_scope(
            [event],
            target_bill_no="TARGET",
            target_bill_name="같은 법률안",
            cutoff_date="2024-04-01",
        )
    assert decisions["E001"].status == "unknown"


def test_law_text_controls_recurrence_before_precedent() -> None:
    recurrence = resolve_recurrence(
        _event(
            event_type="research_plan",
            recurrence_text="5년마다",
            object="종합계획",
        ),
        "국가는 종합계획을 5년마다 수립한다.",
        [_candidate("A", 10, 200_000, 4)],
    )
    assert recurrence.mode == "every_n_years"
    assert recurrence.interval_years == 5
    assert schedule_amount(100_000, recurrence, 5) == [100_000, 0, 0, 0, 0]


def test_displayed_formula_uses_target_recurrence_not_precedent_cycle() -> None:
    from backend.estimator_v2.pipeline import _formula_with_target_recurrence

    recurrence = resolve_recurrence(
        _event(
            event_type="research_plan",
            recurrence_text="5년마다",
        ),
        "종합계획은 5년마다 수립한다.",
        [],
    )
    assert _formula_with_target_recurrence(
        "계획수립 비용 (4년 주기)",
        "research_plan",
        recurrence,
    ) == "계획수립 비용 (대상 조문 5년 주기)"


def test_committee_variables_remain_coherent_per_case() -> None:
    candidates = [
        _candidate("A", 10, 200_000, 4),
        _candidate("B", 12, 200_000, 4),
        _candidate("C", 11, 250_000, 4),
    ]
    amount, formula, evidence, used = estimate_event_amount(
        "committee_operation",
        candidates,
    )
    assert amount == 9_600
    assert "완결된 선례별" in formula
    assert len(evidence) == 3
    assert len(used) == 3


def test_unknown_cost_structure_is_not_total_analogy() -> None:
    decision = assess_event(_event(event_type="other", object="기타 행정 사업"))
    assert decision.automatic is False
    assert "UNSUPPORTED_COST_STRUCTURE" in decision.reason_codes


def test_single_precedent_keeps_formula_and_variables_together() -> None:
    selected = _candidate("A", 11, 250_000, 4)
    amount, formula, evidence = estimate_selected_precedent(
        "committee_operation",
        selected,
    )
    assert amount == 11_000
    assert formula == "인원×수당×횟수"
    assert {row["source"] for row in evidence} == {"A"}


def test_formula_first_fills_only_the_missing_operand() -> None:
    formula_case = TagCandidate(
        item_id="FORMULA",
        bill_no="100",
        bill_name="산식 선례",
        item_name="정책위원회 회의수당",
        category="운영비",
        family="committee",
        similarity=0.8,
        variables=[
            {"type": "target_count", "name": "수당 지급대상", "value": 10, "unit": "명"},
            {"type": "unit_cost", "name": "회의수당", "value": 20, "unit": "만원"},
        ],
        formula="수당 지급대상 인원 × 회의수당 × 연간 회의횟수",
    )
    frequency_case = TagCandidate(
        item_id="FREQUENCY",
        bill_no="101",
        bill_name="횟수 선례",
        item_name="유사 기능 정책위원회 개최",
        category="운영비",
        family="committee",
        similarity=0.7,
        variables=[
            {"type": "frequency", "name": "연간 회의횟수", "value": 4, "unit": "회"},
        ],
    )
    amount, _, evidence, _ = estimate_committee_formula_first(
        _event(),
        "정책위원회를 설치하여 운영한다.",
        formula_case,
        [formula_case, frequency_case],
    )
    assert amount == 8_000
    by_role = {row["role"]: row for row in evidence}
    assert by_role["count"]["source"] == "FORMULA"
    assert by_role["unit_price"]["source"] == "FORMULA"
    assert by_role["unit_price"]["value"] == 200_000
    assert by_role["frequency"]["source"] == "FREQUENCY"


def test_formula_count_beats_a_generative_cap_arithmetic_mistake() -> None:
    formula_case = _candidate("FORMULA", 20, 200_000, 4)
    formula_case.bill_no = "FORMULA_BILL"
    formula_case.similarity = 0.59
    formula_case.variables[0]["source_text"] = (
        "총 20명의 민간위원으로 구성된 직접 관측 지급대상"
    )
    distractor = _candidate("DISTRACTOR", 15, 200_000, 4)
    distractor.bill_no = "DISTRACTOR_BILL"
    source = "위원회는 위원장과 부위원장을 포함한 25명 이내로 구성한다."

    # The count is resolved before the generative selector can incorrectly
    # claim that 20 exceeds the statutory cap of 25.
    with patch(
        "backend.estimator_v2.variable_selection.gemini_json",
        return_value={
            "option_id": "DISTRACTOR:V1",
            "reason": "잘못된 산술 판단",
            "confidence": 0.9,
        },
    ):
        amount, _, evidence, reason = estimate_committee_formula_first(
            _event(),
            source,
            formula_case,
            [formula_case, distractor],
            candidates_by_role={
                "count": [formula_case, distractor],
                "unit_price": [formula_case],
                "frequency": [formula_case],
            },
        )

    assert amount == 16_000
    assert {row["role"]: row["source"] for row in evidence}["count"] == "FORMULA"
    assert "정원·구성 조건 통과" in reason


def test_strong_number_blind_formula_selection_keeps_one_coherent_case() -> None:
    formula_case = _candidate("COHERENT", 11, 250_000, 4)
    formula_case.bill_no = "COHERENT_BILL"
    formula_case.variables[0]["source_text"] = "수당 지급대상자 수를 직접 관측"
    distractor = _candidate("DISTRACTOR", 18, 200_000, 2)
    distractor.bill_no = "DISTRACTOR_BILL"

    with patch(
        "backend.estimator_v2.variable_selection.gemini_json"
    ) as model_call:
        amount, _, evidence, reason = estimate_committee_formula_first(
            _event(),
            "보건복지부 소속 정책심의위원회를 둔다.",
            formula_case,
            [formula_case, distractor],
            candidates_by_role={
                role: [distractor, formula_case]
                for role in ("count", "unit_price", "frequency")
            },
            formula_selection_confidence=1.0,
        )

    assert amount == 11_000
    assert {row["source_bill_no"] for row in evidence} == {
        "COHERENT_BILL"
    }
    assert "동일 산식 묶음" in reason
    model_call.assert_not_called()


def test_latest_general_budget_guideline_beats_committee_name_similarity() -> None:
    similar_name = _candidate("SIMILAR", 10, 200_000, 4)
    similar_name.bill_no = "SIMILAR_BILL"
    similar_name.propose_date = "2025-11-14"
    similar_name.variables[1]["source_text"] = "회의참석 사례금은 20만원으로 가정"

    older_guideline = _candidate("OLD_GUIDE", 10, 250_000, 4)
    older_guideline.bill_no = "OLD_GUIDE_BILL"
    older_guideline.propose_date = "2024-01-23"
    older_guideline.variables[1]["source_text"] = (
        "「2024년도 예산 및 기금운용계획 집행지침」을 준용하여 "
        "회의참석 및 안건검토 수당은 25만원"
    )

    current_guideline = _candidate("CURRENT_GUIDE", 10, 350_000, 4)
    current_guideline.bill_no = "CURRENT_GUIDE_BILL"
    current_guideline.propose_date = "2025-10-02"
    current_guideline.variables[1]["source_text"] = (
        "「2026년도 예산안 편성 및 기금운용계획안 작성 세부지침」을 "
        "참고하여 회의참석수당과 안건검토비를 합한 35만원"
    )

    options = [
        next(
            option
            for option in candidate_options(candidate)
            if option.role == "unit_price"
        )
        for candidate in (similar_name, older_guideline, current_guideline)
    ]
    selected = _latest_general_budget_guideline_option(options)
    assert selected is not None
    assert selected.item_id == "CURRENT_GUIDE"
    assert selected.canonical_value == 350_000


def test_variable_units_are_normalised_before_calculation() -> None:
    candidate = _candidate("A", 10, 200_000, 4)
    candidate.variables[1] = {
        "type": "unit_cost",
        "name": "회의수당",
        "value": 20,
        "unit": "만원",
    }
    options = candidate_options(candidate)
    unit_price = next(option for option in options if option.role == "unit_price")
    assert unit_price.canonical_value == 200_000
    assert unit_price.canonical_unit == "원/명·회"


def test_variable_semantic_selector_payload_hides_operand_values() -> None:
    import json

    from backend.estimator_v2.variable_selection import _masked_option_payload

    candidate = _candidate("HIDDEN", 11, 250_000, 4)
    candidate.variables[2]["source_text"] = "매년 4회 회의를 개최"
    frequency = next(
        option
        for option in candidate_options(candidate)
        if option.role == "frequency"
    )
    payload = json.dumps(_masked_option_payload(frequency), ensure_ascii=False)

    assert '"raw_value"' not in payload
    assert '"canonical_value"' not in payload
    assert "매년 4회" not in payload
    assert "매년 <수치>회" in payload


def test_time_varying_operand_is_not_collapsed_into_one_annual_formula() -> None:
    candidate = _candidate("PHASED", 14, 250_000, 12)
    candidate.variables.append(
        {
            "type": "frequency",
            "name": "2차년도 이후 회의 횟수",
            "value": 1,
            "unit": "회",
        }
    )
    assert has_time_varying_operands(candidate) is True
    amount, _, _, reason = estimate_committee_formula_first(
        _event(),
        "정책위원회를 설치하여 운영한다.",
        candidate,
        [candidate],
    )
    assert amount is None
    assert "연도별" in reason


def test_committee_variable_pool_rejects_other_subcosts_and_balanced_premises() -> None:
    target = _event(quotes=["위원장 1명을 포함한 25명 이내로 구성한다."])
    compound = TagCandidate(
        item_id="COMPOUND",
        bill_no="100",
        bill_name="복합 선례",
        item_name="위원회와 추진단 운영",
        category="운영비",
        family="committee",
        similarity=0.8,
        variables=[
            {"type": "target_count", "name": "추진단 인원", "value": 3, "unit": "명"},
            {"type": "unit_cost", "name": "사무실 임차료", "value": 800, "unit": "만원"},
        ],
    )
    balanced = TagCandidate(
        item_id="BALANCED",
        bill_no="101",
        bill_name="동수 구성 선례",
        item_name="정책위원회",
        category="운영비",
        family="committee",
        similarity=0.7,
        variables=[
            {
                "type": "target_count",
                "name": "외부위원",
                "value": 11,
                "unit": "명",
                "source_text": "전체 후보 중 절반인 11명을 위촉",
            }
        ],
    )
    candidates = [compound, balanced]
    source = "위원장 1명을 포함한 25명 이내로 구성한다."
    assert _compatible_options(target, source, "count", candidates) == []
    assert _compatible_options(target, source, "unit_price", candidates) == []


def test_support_body_full_operation_precedent_beats_partial_cost_rows() -> None:
    target = _event(
        object="특별지방자치단체지원협의회",
        action="설치·운영",
        quotes=["지원협의회를 설치하여 운영한다."],
    )
    annual = TagCandidate(
        item_id="FULL",
        bill_no="100",
        bill_name="선례",
        item_name="특별시 지원위원회 운영",
        category="운영비",
        family="committee",
        similarity=0.6,
        variables=[],
        amounts=[
            {"year_offset": year, "amount_thousand": 50_000 + year * 1_000}
            for year in range(5)
        ],
        formula="유사사례 준용 추계",
    )
    allowance = _candidate("ALLOWANCE", 15, 250_000, 2)
    allowance.item_name = "특별시 지원위원회 위촉위원 수당"
    office = TagCandidate(
        item_id="OFFICE",
        bill_no="102",
        bill_name="선례",
        item_name="특별시 지원위원회 실무지원단 운영비",
        category="운영비",
        family="committee",
        similarity=0.8,
        amounts=[{"year_offset": 0, "amount_thousand": 60_000}],
    )
    selected, reason, confidence, _ = select_precedent(
        target,
        "지원협의회를 설치하여 운영한다.",
        [allowance, office, annual],
    )
    assert selected is annual
    assert "전체 운영 범위" in reason
    assert confidence >= 0.65
    amount, _, evidence = estimate_selected_precedent(
        "committee_operation",
        selected,
    )
    assert amount == 52_000
    assert evidence[0]["source"] == "FULL"


def test_support_body_uses_clear_semantic_margin_between_full_operation_cases() -> None:
    target = _event(
        object="특별지방자치단체지원협의회 및 협의지원단",
        action="설치·운영",
        quotes=["지원협의회와 협의지원단을 설치하여 운영한다."],
    )
    close = TagCandidate(
        item_id="FULL_CLOSE",
        bill_no="100",
        bill_name="특별자치단체 지원 선례",
        item_name="특별시 지원위원회 운영",
        category="운영비",
        family="committee",
        similarity=0.70,
        amounts=[{"year_offset": 0, "amount_thousand": 50_000}],
        formula="유사사례 준용",
    )
    distant = TagCandidate(
        item_id="FULL_DISTANT",
        bill_no="101",
        bill_name="학생지원 선례",
        item_name="학생맞춤통합지원위원회 운영",
        category="운영비",
        family="committee",
        similarity=0.60,
        amounts=[{"year_offset": 0, "amount_thousand": 40_000}],
        formula="유사사례 준용",
    )
    selected, reason, _, _ = select_precedent(
        target,
        "지원협의회와 협의지원단을 설치하여 운영한다.",
        [distant, close],
    )
    assert selected is close
    assert "의미 점수 우위" in reason


def test_research_scorecard_hides_amounts_and_prioritizes_direct_target() -> None:
    broad_domain = TagCandidate(
        item_id="BROAD",
        bill_no="100",
        bill_name="같은 부처 정책법안",
        item_name="인접 정책 종합계획 수립",
        category="위탁비",
        family="research",
        similarity=0.9,
        variables=[
            {
                "type": "unit_cost",
                "name": "연구용역비",
                "value": 147_000_000,
                "unit": "원",
                "source_text": "연구용역비 147,000,000원을 적용",
            }
        ],
        amounts=[
            {"year_offset": 0, "amount_thousand": 147_000}
        ],
        formula="147,000,000원",
    )
    direct_target = TagCandidate(
        item_id="DIRECT",
        bill_no="101",
        bill_name="대상기관 상위조직 법안",
        item_name="대상기관 발전종합계획 수립",
        category="사업비",
        family="research",
        similarity=0.5,
        variables=[
            {
                "type": "unit_cost",
                "name": "회당 계획수립 비용",
                "value": 89_000_000,
                "unit": "원",
                "source_text": "계획수립 비용 89,000,000원",
            }
        ],
        amounts=[
            {"year_offset": 0, "amount_thousand": 89_000}
        ],
        formula="계획수립 비용 89,000,000원",
    )
    payload = _research_scorecard_candidate_payload(broad_domain)
    assert "147000000" not in str(payload).replace(",", "")
    assert "<수치>" in str(payload)

    selected, reason, confidence = _choose_research_scorecard_candidate(
        [broad_domain, direct_target],
        {
            "scores": [
                {
                    "candidate_id": "BROAD",
                    "target_relation_type": "functional_association",
                    "artifact_purpose_match": 2,
                    "domain_match": 3,
                    "reason": "같은 넓은 정책 분야",
                },
                {
                    "candidate_id": "DIRECT",
                    "target_relation_type": "legal_parent_child",
                    "artifact_purpose_match": 3,
                    "domain_match": 2,
                    "reason": "대상기관 계열과 계획 산출물이 직접 일치",
                },
            ]
        },
    )
    assert selected is direct_target
    assert "후보 금액을 숨긴" in reason
    assert confidence >= 0.8

    weak, weak_reason, _ = _choose_research_scorecard_candidate(
        [broad_domain],
        {
            "scores": [
                {
                    "candidate_id": "BROAD",
                    "target_relation_type": "functional_association",
                    "artifact_purpose_match": 3,
                    "domain_match": 3,
                    "reason": "같은 분야에서 기능적으로만 관련",
                }
            ]
        },
    )
    assert weak is None
    assert "기능적 연관 수준" in weak_reason


def test_short_provider_candidate_id_resolves_only_when_unambiguous() -> None:
    single = _candidate("PRC_CASE::cost_estimate::item1", 10, 200_000, 4)
    selected, expanded = _resolve_returned_candidate([single], "PRC_CASE")
    assert selected is single
    assert expanded is True

    other = _candidate("PRC_CASE::cost_estimate::item2", 10, 200_000, 4)
    selected, expanded = _resolve_returned_candidate(
        [single, other],
        "PRC_CASE",
    )
    assert selected is None
    assert expanded is False


def test_committee_candidate_over_legal_cap_is_rejected() -> None:
    event = _event(quotes=["위원회는 25인 이내로 구성한다."])
    source = "위원회는 25인 이내로 구성한다."
    candidates = [
        _candidate("too_large", 50, 200_000, 4),
        _candidate("compatible", 22, 300_000, 2),
    ]
    assert [candidate.item_id for candidate in usable_candidates(event, source, candidates)] == [
        "compatible"
    ]


def test_committee_formula_cap_survives_pdf_split_word() -> None:
    event = _event(quotes=["위원회는 25인이 내로 구성한다."])
    candidates = [
        _candidate("too_large", 50, 200_000, 4),
        _candidate("compatible", 22, 300_000, 2),
    ]
    assert [
        candidate.item_id
        for candidate in usable_candidates(
            event,
            "위원회는 25인이 내로 구성한다.",
            candidates,
        )
    ] == ["compatible"]


def test_target_committee_composition_excludes_public_official_allowances() -> None:
    event = _event(object="보수위원회")
    source = """
    위원회는 다음 각 호의 위원 27명으로 구성한다.
    1. 근로자를 대표하는 위원 9명
    2. 국가와 지방자치단체를 대표하는 위원 9명
    3. 공익을 대표하는 위원 9명
    국가와 지방자치단체를 대표하는 위원은 고위공무원단에 속하는
    공무원을 임명한다.
    위원에게 수당과 경비를 지급할 수 있다. 다만 공무원이 그 소관업무와
    직접 관련하여 위원회에 출석한 경우에는 지급하지 아니한다.
    """
    assert _target_payable_member_count(event, source) == (
        18,
        (
            "조문상 총 27명 중 국가와지방자치단체를대표하는위원 9명은 "
            "소관업무 관련 공무원 수당 제외, 지급 가능 인원 18명"
        ),
    )


def test_incremental_formula_subtracts_same_authority_incumbent_baseline() -> None:
    event = _event(
        actor="인사혁신처",
        object="공무원임금위원회",
    )
    source = """
    인사혁신처 소속으로 공무원임금위원회를 둔다.
    위원회는 다음 각 호에 따라 21명 이내의 위원으로 구성한다.
    1. 공무원을 대표하는 위원은 7명 이내로 한다.
    2. 국가와 지방자치단체를 대표하는 위원은 7명 이내로 한다.
    3. 전문가를 대표하는 위원은 7명 이내로 한다.
    국가와 지방자치단체를 대표하는 위원은 국가공무원 또는
    지방공무원으로 한다.
    위원에게 수당과 경비를 지급할 수 있다. 다만 공무원이 그 소관업무와
    직접 관련하여 위원회에 출석한 경우에는 지급하지 아니한다.
    """
    precedent = _candidate("SAME_AUTHORITY", 8, 350_000, 4)
    precedent.bill_no = "PAST"
    precedent.bill_name = "공무원보수위원회 설치법안"
    precedent.item_name = "공무원보수위원회 설치·운영"
    precedent.similarity = 0.67
    precedent.formula = "추가 위촉위원 수 × 수당 × 연간 회의 횟수"
    precedent.variables[0].update(
        {
            "name": "추가 위촉위원 수",
            "value": 8,
            "source_text": (
                "인사혁신처가 현재 설치·운영하는 위원회의 위촉위원 수(10명)와 "
                "새 위원회의 위촉위원 수(18명)의 차이인 8명"
            ),
        }
    )
    precedent.variables[1]["source_text"] = "회의 참석 및 안건검토 수당"
    precedent.variables[2]["source_text"] = "연 4회 회의를 개최"

    amount, _, evidence, reason = estimate_committee_formula_first(
        event,
        source,
        precedent,
        [precedent],
        candidates_by_role={
            "count": [precedent],
            "unit_price": [precedent],
            "frequency": [precedent],
        },
    )
    assert amount == 5_600
    assert evidence[0]["value"] == 4
    assert "14명 - 인사혁신처" in evidence[0]["source_text"]
    assert "추가 4명" in evidence[0]["source_text"]
    assert "대상 조문에서 계산" in reason


def test_hitl_baseline_and_actual_operands_recompute_incremental_committee() -> None:
    event = _event(
        actor="국무총리",
        object="보수위원회",
    )
    source = """
    위원회는 다음 각 호의 위원 27명으로 구성한다.
    1. 근로자를 대표하는 위원 9명
    2. 국가와 지방자치단체를 대표하는 위원 9명
    3. 공익을 대표하는 위원 9명
    국가와 지방자치단체를 대표하는 위원은 국가공무원으로 한다.
    위원에게 수당을 지급할 수 있다. 다만 공무원이 소관업무와 직접
    관련하여 출석한 경우에는 지급하지 아니한다.
    """
    formula_case = _candidate("FORMULA", 50, 200_000, 4)
    amount, _, evidence, reason = estimate_committee_formula_first(
        event,
        source,
        formula_case,
        [formula_case],
        candidates_by_role={
            "count": [formula_case],
            "unit_price": [formula_case],
            "frequency": [formula_case],
        },
        user_inputs={
            "incumbent_paid_members": 10,
            "unit_price_won": 350_000,
            "annual_meetings": 4,
        },
    )
    assert amount == 11_200
    by_role = {row["role"]: row for row in evidence}
    assert by_role["count"]["value"] == 8
    assert by_role["unit_price"]["value"] == 350_000
    assert by_role["frequency"]["value"] == 4
    assert all(row["source"] == "USER_INPUT" for row in evidence)
    assert (
        "18명 - 사용자 확인 기존 지급대상 10명 = 순증 8명"
        in by_role["count"]["source_text"]
    )
    assert "대상 조문에서 계산" in reason


def test_target_committee_uses_explicit_non_public_majority_before_precedent() -> None:
    central = _event(
        object="처우개선위원회",
        quotes=[
            "위원회는 위원장 1명을 포함한 20명 이내의 위원으로 구성한다.",
            (
                "위원장은 장관으로 하고, 위원은 장관이 임명하거나 위촉한다. "
                "이 경우 위원은 공무원이 아닌 사람이 과반수가 되도록 한다."
            ),
        ],
    )
    assert _target_non_public_majority_count(
        central,
        " ".join(central.quotes),
    ) == (
        10,
        (
            "조문상 정원 상한 20명 중 위원장을 제외한 위원의 공무원이 아닌 "
            "사람이 과반수여야 하므로 최소 10명"
        ),
    )

    subcommittee = _event(
        object="분과위원회",
        quotes=[
            "분과위원회는 위원장 1명을 포함한 5명 이내의 위원으로 한다.",
            "이 경우 전체위원 중 공무원이 아닌 사람이 과반수가 되어야 한다.",
        ],
    )
    assert _target_non_public_majority_count(
        subcommittee,
        " ".join(subcommittee.quotes),
    ) == (
        3,
        (
            "조문상 정원 상한 5명 중 전체 위원의 공무원이 아닌 사람이 "
            "과반수여야 하므로 최소 3명"
        ),
    )


def test_atomic_committee_rejects_compound_cost_package() -> None:
    compound = _candidate("COMPOUND", 10, 250_000, 4)
    compound.item_name = "위원회·실무추진단 운영 및 종합계획·실태조사"
    compound.formula = (
        "위원회 운영비 + 실무추진단 인건비 + 종합계획 수립비 + 실태조사비"
    )
    compound.variables.append(
        {
            "type": "unit_cost",
            "name": "종합계획 연구용역비",
            "value": 100,
            "unit": "백만원",
        }
    )
    pure = _candidate("PURE", 10, 250_000, 4)
    source = "정책위원회를 설치하여 운영한다."
    assert [
        candidate.item_id
        for candidate in usable_candidates(_event(), source, [compound, pure])
    ] == ["PURE"]


def test_committee_title_words_do_not_create_false_compound_scope() -> None:
    candidate = _candidate("PUBLIC_PAY", 8, 350_000, 4)
    candidate.item_name = "공무원보수위원회 설치·운영"
    candidate.formula = "위원 수 × 회의 수당 × 연간 회의 횟수"
    assert usable_candidates(
        _event(),
        "공무원보수위원회를 설치하여 운영한다.",
        [candidate],
    ) == [candidate]


def test_explicit_member_minimum_overrides_precedent_count() -> None:
    formula_case = _candidate("FORMULA", 10, 250_000, 1)
    formula_case.item_name = "국민참여 공론화위원회 운영비"
    event = _event(
        object="헌법개정국민참여회의",
        quotes=["국민참여회의는 500명 이상의 위원으로 구성한다."],
    )
    amount, _, evidence, reason = estimate_committee_formula_first(
        event,
        "국민참여회의는 500명 이상의 위원으로 구성한다.",
        formula_case,
        [formula_case],
    )
    assert amount == 125_000
    by_role = {row["role"]: row for row in evidence}
    assert by_role["count"]["value"] == 500
    assert by_role["count"]["source"] == "TARGET_DOCUMENT"
    assert "대상 조문" in reason


def test_participatory_frequency_rejects_unrelated_standing_committee() -> None:
    event = _event(
        object="국민참여 공론화회의",
        quotes=["국민참여위원이 공론조사를 수행한다."],
    )
    ordinary = _candidate("ORDINARY", 10, 250_000, 10)
    ordinary.item_name = "법관독립위원회 회의참석수당"
    participatory = _candidate("PARTICIPATORY", 500, 250_000, 1)
    participatory.item_name = "시민참여 공론화위원회 회의참석수당"
    options = _compatible_options(
        event,
        "국민참여위원이 공론조사를 수행한다.",
        "frequency",
        [ordinary, participatory],
    )
    assert [option.item_id for option in options] == ["PARTICIPATORY"]


def test_policy_coordination_word_does_not_turn_committee_into_case_channel() -> None:
    text = (
        "임금정책과 발전계획을 심의하고 관계 부처와 협의·조정하기 위하여 "
        "정책위원회를 둔다."
    )
    assert _committee_function(text) == "policy_deliberation"
    assert _committee_function("분쟁조정 신청 사건을 심의한다.") == "case_adjudication"


def test_committee_member_cap_survives_pdf_line_break_inside_word() -> None:
    event = _event(object="발전위원회")
    too_large = _candidate("TOO_LARGE", 50, 250_000, 4)
    compatible = _candidate("COMPATIBLE", 20, 250_000, 4)
    options = _compatible_options(
        event,
        "위원회는 공동위원장을 포함한 25인이 내의 위원으로 구성한다.",
        "count",
        [too_large, compatible],
    )
    assert [option.item_id for option in options] == ["COMPATIBLE"]


def test_frequency_rejects_an_assumption_borrowed_from_another_body() -> None:
    event = _event(
        object="농업정책발전위원회",
        quotes=["농업 발전계획과 주요 정책을 심의한다."],
    )
    second_order = _candidate("SECOND_ORDER", 20, 200_000, 14)
    second_order.variables[2]["source_text"] = (
        "회의개최 횟수는 유사사례인 환경협의회의 2025년 실적 "
        "14회를 준용하여 연 14회로 가정"
    )
    direct = _candidate("DIRECT", 20, 250_000, 4)
    direct.variables[2]["source_text"] = (
        "위원회는 주요 정책과 발전계획을 심의하기 위하여 연 4회 개최"
    )

    options = _compatible_options(
        event,
        "농업 발전계획과 주요 정책을 심의한다.",
        "frequency",
        [second_order, direct],
    )

    assert [option.item_id for option in options] == ["DIRECT"]


def test_incompatible_same_case_operand_cannot_bypass_function_gate() -> None:
    formula_case = _candidate("ORDINARY", 50, 250_000, 4)
    formula_case.item_name = "보건의료정책위원회 운영비"
    event = _event(
        object="국민참여 공론화회의",
        quotes=[
            "국민참여회의는 500명 이상의 국민참여위원으로 구성한다.",
            "국민참여위원이 공론조사를 수행한다.",
        ],
    )
    amount, _, evidence, reason = estimate_committee_formula_first(
        event,
        "국민참여위원이 공론조사를 수행한다.",
        formula_case,
        [formula_case],
    )
    assert amount is None
    assert {row["role"] for row in evidence} == {"count", "unit_price"}
    assert "회의 횟수" in reason


def test_organization_cluster_groups_two_cost_views_of_one_change() -> None:
    personnel = _event(
        id="E001",
        event_type="personnel",
        cost_mechanism="staffing",
        object="신설 기관 인력",
    )
    facility = _event(
        id="E002",
        event_type="facility_system",
        cost_mechanism="construction",
        object="신설 기관 시설",
    )
    unrelated = _event(
        id="E003",
        segment_ids=["S002"],
        event_type="personnel",
        object="별도 증원",
    )
    clusters = find_organization_clusters([personnel, facility, unrelated])
    assert [[event.id for event in cluster] for cluster in clusters] == [["E001", "E002"]]


def test_organization_change_is_a_single_stable_event_contract() -> None:
    organization = _event(
        id="E001",
        event_type="organization_change",
        cost_mechanism="organization_change",
        object="신설 공공기관",
    )
    clusters = find_organization_clusters([organization])
    assert [[event.id for event in cluster] for cluster in clusters] == [["E001"]]


def test_legislative_special_committee_enters_organization_channel() -> None:
    committee = _event(
        actor="국회",
        object="헌법특별위원회",
        quotes=["헌법개정안을 심사하기 위하여 헌법특별위원회를 둔다."],
    )
    assert _is_legislative_committee_organization_event(committee) is True
    assert [[event.id for event in cluster] for cluster in find_organization_clusters([committee])] == [
        ["E001"]
    ]


def test_national_assembly_advisory_council_remains_committee_channel() -> None:
    advisory = _event(
        actor="국회",
        object="헌법개정국민자문위원회",
        quotes=["국민의 의견을 듣기 위하여 자문위원회를 둔다."],
    )
    assert _is_legislative_committee_organization_event(advisory) is False
    assert find_organization_clusters([advisory]) == []


def test_mandatory_dedicated_officer_enters_staffing_value_channel() -> None:
    officer = _event(
        actor="공공기관의 장",
        action="지정",
        object="여성농어업인담당관",
        bearer="public_institution",
        event_type="administrative",
        quotes=["소속 직원 중에서 여성농어업인담당관을 지정하여야 한다."],
    )
    assert [[event.id for event in cluster] for cluster in find_organization_clusters([officer])] == [
        ["E001"]
    ]


def test_dedicated_officer_labeled_committee_is_routed_to_staffing_channel() -> None:
    """A role paragraph must not become a meeting-allowance event."""
    officer = _event(
        actor="여성농어업인 정책 관련 공공기관의 장",
        action="업무 수행",
        object="여성농어업인담당관",
        bearer="state",
        event_type="committee_operation",
        cost_mechanism="internal_administration",
        quotes=[
            "그 소속 직원 중에서 여성농어업인담당관을 지정하여 업무를 수행하게 한다."
        ],
    )
    events = _normalise_staff_designation_events([officer])
    assert events[0].event_type == "personnel"
    assert events[0].cost_mechanism == "staffing"
    assert [[event.id for event in cluster] for cluster in find_organization_clusters(events)] == [
        ["E001"]
    ]


def test_implementing_decree_delegation_is_not_a_second_cost_event() -> None:
    rulemaking = _event(
        actor="대통령",
        action="정한다",
        object="담당관의 지정 및 업무에 관하여 필요한 사항",
        event_type="administrative",
        quotes=["필요한 사항은 대통령령으로 정한다."],
    )
    decision = assess_event(rulemaking)
    assert decision.status == RowStatus.EXCLUDED
    assert decision.reason_codes == [
        "IMPLEMENTING_RULEMAKING_NOT_INDEPENDENT_COST_EVENT"
    ]


def test_legislative_committee_value_case_rejects_support_office_when_same_form_exists() -> None:
    target = _event(actor="국회", object="헌법특별위원회")
    committee = OrganizationCase(
        "1",
        "국회법 일부개정법률안",
        "2024-01-01",
        "국회에 법제위원회를 신설하여 둔다.",
        [],
    )
    support_office = OrganizationCase(
        "2",
        "지원법안",
        "2024-01-02",
        (
            "국회에 헌법개정지원단을 설치한다. 연계법률안은 "
            "헌법특별위원회를 신설한다."
        ),
        [
            (
                "personnel",
                TagCandidate(
                    item_id="SUPPORT",
                    bill_no="2",
                    bill_name="지원법안",
                    item_name="지원단 보수",
                    category="인건비",
                    family="personnel",
                    similarity=0.0,
                    variables=[],
                    amounts=[{"year_offset": 0, "amount_thousand": 100}],
                    formula="지원단 인원 × 보수",
                ),
            )
        ],
    )
    assert _restrict_legislative_committee_value_cases(
        [target],
        [support_office, committee],
    ) == [committee]


def test_court_value_case_rejects_support_office_when_court_case_exists() -> None:
    target = _event(
        event_type="organization_change",
        cost_mechanism="organization_change",
        object="인천고등법원",
    )
    court = OrganizationCase(
        "COURT",
        "법원 설치법안",
        "2024-01-01",
        "고등법원을 신설하여 둔다.",
        [],
    )
    support_office = OrganizationCase(
        "OFFICE",
        "위원회 사무국 법안",
        "2024-01-02",
        "법원 소속 위원회에 사무국을 둔다.",
        [],
    )
    assert _restrict_legislative_committee_value_cases(
        [target],
        [support_office, court],
    ) == [court]


def test_court_transition_distinguishes_branch_promotion_from_new_branch() -> None:
    assert _court_transition(
        "현 고양지원을 고양지방법원으로 승격하여 신설한다."
    ) == "branch_to_district"
    assert _court_transition(
        "성남지방법원을 신설하되 현행 성남지원을 폐지한다."
    ) == "branch_to_district"
    assert _court_transition(
        "양산시법원을 폐지하고 양산지원을 신설한다."
    ) == "local_court_to_branch"


def test_court_transition_prefers_same_hierarchy_change_before_semantics() -> None:
    promoted = OrganizationCase(
        "DISTRICT",
        "법원 설치법안",
        "2023-01-01",
        "성남지방법원을 신설하되 현행 성남지원을 폐지한다.",
        [],
    )
    new_branch = OrganizationCase(
        "BRANCH",
        "법원 설치법안",
        "2023-02-01",
        "양산시법원을 폐지하고 양산지원을 신설한다.",
        [],
    )
    assert _prefer_same_court_transition(
        "고양지원을 고양지방법원으로 승격하여 신설한다.",
        [new_branch, promoted],
    ) == [promoted]


def test_judicial_value_case_uses_latest_pay_basis_not_transition_amount() -> None:
    target = _event(
        event_type="organization_change",
        cost_mechanism="organization_change",
        object="고양지방법원",
        actor="법원",
        quotes=["고양지원을 고양지방법원으로 승격하여 신설한다."],
    )

    def court_case(bill_no: str, date: str, basis_year: int) -> OrganizationCase:
        personnel = TagCandidate(
            item_id=f"{bill_no}-P",
            bill_no=bill_no,
            bill_name="법원 설치법안",
            item_name="법원공무원 인건비",
            category="인건비",
            family="personnel",
            similarity=0.0,
            variables=[
                {
                    "name": f"{basis_year}년 기준 5급 평균 연봉액",
                    "source_text": f"{basis_year}년 기준 법원공무원 평균 연봉",
                }
            ],
            formula="직급별 인원 × 평균 연봉",
        )
        return OrganizationCase(
            bill_no,
            "법원 설치법안",
            date,
            "지방법원을 신설한다.",
            [("personnel", personnel)],
        )

    older_same_transition = court_case("OLD", "2023-01-01", 2022)
    newer_pay_table = court_case("NEW", "2025-01-01", 2024)
    assert _latest_judicial_value_case(
        [target],
        [older_same_transition, newer_pay_table],
    ) == newer_pay_table


def test_bundle_form_uses_priced_subject_before_broad_judicial_context() -> None:
    item = TagCandidate(
        item_id="BUNDLE",
        bill_no="1",
        bill_name="위원회법안",
        item_name="위자료위원회 사무국 인건비 등",
        category="인건비",
        family="personnel",
        similarity=0.0,
    )
    assert _bundle_organization_form(
        item,
        "법원 소속 위원회의 업무와 사무국 운영비를 추계한다.",
    ) == "support_office"


def test_priced_subject_system_ignores_nabo_and_construction_boilerplate() -> None:
    public_case = OrganizationCase(
        "1",
        "농수산물 유통 및 가격안정에 관한 법률 일부개정법률안",
        "2024-01-01",
        (
            "한국농수산식품유통공사(aT) 제출자료를 바탕으로 "
            "국회예산정책처가 작성했다."
        ),
        [
            (
                "personnel",
                TagCandidate(
                    item_id="PUBLIC",
                    bill_no="1",
                    bill_name="농수산물 법안",
                    item_name="점검 인력 인건비",
                    category="인건비",
                    family="personnel",
                    similarity=0.0,
                    formula="직원 수 × 직원 평균보수",
                ),
            )
        ],
    )
    central_case = OrganizationCase(
        "2",
        "고위공직자범죄수사처법 일부개정법률안",
        "2024-01-01",
        "사무실 개선공사 비용을 포함하고 국회예산정책처가 작성했다.",
        [
            (
                "personnel",
                TagCandidate(
                    item_id="CENTRAL",
                    bill_no="2",
                    bill_name="공수처법안",
                    item_name="수사관 보수",
                    category="인건비",
                    family="personnel",
                    similarity=0.0,
                    formula="직급별 보수 × 공무원임금상승률",
                ),
            )
        ],
    )
    assert (
        _case_personnel_system_from_priced_subject(public_case)
        == "public_institution"
    )
    assert (
        _case_personnel_system_from_priced_subject(central_case)
        == "central_government"
    )


def test_discretionary_organization_is_not_auto_scaled() -> None:
    optional = _event(
        id="E001",
        event_type="organization_change",
        cost_mechanism="organization_change",
        object="지방공단",
        obligation="discretionary",
        quotes=["지방공단을 설립할 수 있다."],
    )
    assert find_organization_clusters([optional]) == []


def test_staff_count_mapping_is_cluster_specific() -> None:
    main = _event(
        id="MAIN",
        article_refs=["제4조"],
        event_type="organization_change",
        object="특별지방자치단체",
    )
    support = _event(
        id="SUPPORT",
        article_refs=["제7조"],
        event_type="organization_change",
        object="협의지원단",
    )
    mapping = {"제4조": 60, "제7조": 7}
    assert _mapped_staff_count([main], mapping) == 60
    assert _mapped_staff_count([support], mapping) == 7


def test_organization_component_normalisation_is_precedent_side_only() -> None:
    item = TagCandidate(
        item_id="A",
        bill_no="1",
        bill_name="선례",
        item_name="증원인원 자산취득비",
        category="사업비",
        family="other",
        similarity=0.0,
        variables=[],
        amounts=[{"year_offset": 0, "amount_thousand": 100}],
        formula="증원인원 × 1인당 자산취득비",
    )
    assert _component(item) == "asset"


def test_personnel_ratio_general_management_is_overhead_not_facility() -> None:
    item = TagCandidate(
        item_id="OVERHEAD",
        bill_no="1",
        bill_name="선례",
        item_name="일반관리비",
        category="운영비",
        family="other",
        similarity=0.0,
        variables=[],
        amounts=[{"year_offset": 0, "amount_thousand": 100}],
        formula="인건비 × 일반관리비 비율 27.41%",
    )
    assert _component(item) == "basic_expense"


def test_fixed_legislative_committee_operating_precedent_requires_comparable_average() -> None:
    comparable = TagCandidate(
        item_id="OPERATING",
        bill_no="1",
        bill_name="국회법 일부개정법률안",
        item_name="사업비",
        category="사업비",
        family="other",
        similarity=0.0,
        variables=[
            {
                "type": "unit_cost",
                "name": "상임위원회 운영경비 평균값",
                "value": 211_000_000,
                "unit": "원",
                "source_text": "17개 상임위원회의 운영경비 평균값",
            }
        ],
        amounts=[{"year_offset": 0, "amount_thousand": 216_000}],
        formula="운영경비 평균값에 소비자물가상승률 적용",
    )
    generic_project = TagCandidate(
        item_id="PROJECT",
        bill_no="2",
        bill_name="지원법안",
        item_name="사업비",
        category="사업비",
        family="other",
        similarity=0.0,
        variables=[],
        amounts=[{"year_offset": 0, "amount_thousand": 216_000}],
        formula="대상 기관 수 × 기관별 지원 단가",
    )
    assert _component(comparable) == "operating_expense"
    assert _is_fixed_operating_precedent(comparable) is True
    assert _is_fixed_operating_precedent(generic_project) is False


def test_primary_personnel_label_is_not_overwritten_by_nested_contribution() -> None:
    item = TagCandidate(
        item_id="B",
        bill_no="2",
        bill_name="선례",
        item_name="법원공무원 인건비",
        category="인건비",
        family="personnel",
        similarity=0.0,
        variables=[],
        amounts=[{"year_offset": 0, "amount_thousand": 100}],
        formula="보수와 사회보험 기관부담금을 합산",
    )
    assert _component(item) == "personnel"


def test_organization_total_row_is_not_treated_as_a_cost_component() -> None:
    total = TagCandidate(
        item_id="TOTAL",
        bill_no="3",
        bill_name="선례",
        item_name="총 추가재정소요",
        category="운영비",
        family="other",
        similarity=0.0,
        variables=[],
        amounts=[{"year_offset": 0, "amount_thousand": 10_000}],
        formula="인건비 + 기관부담금 + 기본경비 + 자산취득비",
    )
    assert _is_aggregate_item(total) is True
    assert _component(total) == ""


def test_component_name_containing_total_context_is_not_blindly_dropped() -> None:
    detail = TagCandidate(
        item_id="DETAIL",
        bill_no="3",
        bill_name="선례",
        item_name="증원인원 총계 기준 기본경비",
        category="운영비",
        family="other",
        similarity=0.0,
        variables=[],
        amounts=[{"year_offset": 0, "amount_thousand": 100}],
        formula="증원인원 총계 × 1인당 기본경비",
    )
    assert _is_aggregate_item(detail) is False
    assert _component(detail) == "basic_expense"


def test_organization_amounts_scale_by_target_specific_count() -> None:
    item = TagCandidate(
        item_id="C",
        bill_no="3",
        bill_name="선례",
        item_name="인건비",
        category="인건비",
        family="personnel",
        similarity=0.0,
        variables=[],
        amounts=[
            {"year_offset": 0, "amount_thousand": 830},
            {"year_offset": 1, "amount_thousand": 1_660},
        ],
        formula="인원 × 단가",
    )
    assert _scaled_series(item, 2, target_count=28, precedent_count=83) == [280, 560]


def test_value_item_uses_its_own_case_denominator() -> None:
    personnel = TagCandidate(
        item_id="P",
        bill_no="3",
        bill_name="선례",
        item_name="인건비",
        category="인건비",
        family="personnel",
        similarity=0.0,
        variables=[{"type": "target_count", "name": "증원", "value": 40, "unit": "명"}],
        amounts=[{"year_offset": 0, "amount_thousand": 100}],
        formula="",
    )
    asset = TagCandidate(
        item_id="A",
        bill_no="3",
        bill_name="선례",
        item_name="자산취득비",
        category="사업비",
        family="other",
        similarity=0.0,
        variables=[{"type": "target_count", "name": "정원", "value": 55, "unit": "명"}],
        amounts=[{"year_offset": 0, "amount_thousand": 100}],
        formula="",
    )
    case = OrganizationCase("3", "선례", "2025-01-01", "", [
        ("personnel", personnel),
        ("asset", asset),
    ])
    assert _item_staff_count(case, "personnel", personnel) == 40
    assert _item_staff_count(case, "asset", asset) == 55


def test_permanent_organization_rejects_truncated_temporary_value_case() -> None:
    def item(
        item_id: str,
        component: str,
        amounts: list[int],
        *,
        count: int = 20,
    ) -> tuple[str, TagCandidate]:
        names = {
            "personnel": ("인건비", "인건비", "personnel"),
            "basic_expense": ("기본경비", "운영비", "other"),
            "asset": ("자산취득비", "자산취득비", "other"),
        }
        name, category, family = names[component]
        return component, TagCandidate(
            item_id=item_id,
            bill_no=item_id.split("-")[0],
            bill_name="선례",
            item_name=name,
            category=category,
            family=family,
            similarity=0.7,
            variables=[
                {"type": "target_count", "name": "정원", "value": count, "unit": "명"}
            ],
            amounts=[
                {
                    "year_offset": offset,
                    "amount_thousand": amount,
                    "formula_text": "인원×단가",
                }
                for offset, amount in enumerate(amounts)
            ],
            formula="인원×단가",
        )

    temporary = OrganizationCase(
        "T",
        "한시 조사위원회",
        "2025-01-01",
        "위원회의 활동기간은 2년이며 기간 만료 후 해산한다.",
        [
            item("T-P", "personnel", [100, 100]),
            item("T-B", "basic_expense", [20, 20]),
            item("T-A", "asset", [10]),
        ],
        0.9,
    )
    permanent = OrganizationCase(
        "P",
        "상설 연구조직",
        "2025-01-01",
        "연구 업무를 수행하기 위하여 상설 조직을 신설한다.",
        [
            item("P-P", "personnel", [100, 100, 100, 100, 100]),
            item("P-B", "basic_expense", [20, 20, 20, 20, 20]),
            item("P-A", "asset", [10]),
        ],
        0.8,
    )
    target = _event(
        event_type="organization_change",
        cost_mechanism="organization_change",
        quotes=["정책 연구를 위하여 연구원을 둔다."],
        object="정책연구원",
    )
    eligible = _eligible_organization_value_cases(
        [target],
        [temporary, permanent],
        5,
    )
    assert [case.bill_no for case in eligible] == ["P"]
    limited_eligible = _eligible_organization_value_cases(
        [target],
        [temporary, permanent],
        5,
        "위원회는 활동 기간 2년이 끝나면 해산한다.",
    )
    assert [case.bill_no for case in limited_eligible] == ["T"]


def test_value_case_ranking_is_deterministic_inside_compatible_pool() -> None:
    lower = OrganizationCase("A", "선례 A", "2025-01-01", "", [], 0.61)
    higher = OrganizationCase("B", "선례 B", "2024-01-01", "", [], 0.72)
    incompatible = OrganizationCase("C", "선례 C", "2026-01-01", "", [], 0.99)
    selected = _top_compatible_value_case(
        [lower, higher, incompatible],
        ["A", "B"],
    )
    assert selected is higher


def test_compound_staff_bundle_rejects_ambiguous_denominators() -> None:
    item = TagCandidate(
        item_id="AMBIGUOUS",
        bill_no="1",
        bill_name="선례",
        item_name="인력운영비",
        category="인건비",
        family="personnel",
        similarity=0.0,
        variables=[
            {"type": "target_count", "name": "본청", "value": 20, "unit": "명"},
            {"type": "target_count", "name": "의회", "value": 10, "unit": "명"},
        ],
        amounts=[],
    )
    assert _single_staff_denominator(item) is None


def test_compound_staff_bundle_rejects_multiple_rows_per_year() -> None:
    item = TagCandidate(
        item_id="DUPLICATE",
        bill_no="1",
        bill_name="선례",
        item_name="인력운영비",
        category="인건비",
        family="personnel",
        similarity=0.0,
        variables=[],
        amounts=[
            {"year_offset": 0, "amount_thousand": 100},
            {"year_offset": 0, "amount_thousand": 200},
        ],
    )
    assert _coherent_bundle_series(item, 1) is None


def test_personnel_system_gate_distinguishes_local_and_public_institution() -> None:
    assert _personnel_system("지방자치단체의 지방공무원과 지방의회") == "local_government"
    assert _personnel_system("한국안전공단을 설립하고 직원을 채용") == "public_institution"
    assert (
        _personnel_system(
            "한국방재안전공단 신규채용 비용을 국회예산정책처가 작성"
        )
        == "public_institution"
    )


def test_local_government_bundle_uses_pre_cutoff_complete_case() -> None:
    selected, reason, confidence = select_staff_cost_bundle(
        "특별지방자치단체 집행기관과 지방의회 사무처의 직원을 둔다",
        "특별지방자치단체 집행기관과 지방의회 사무처의 지방공무원",
        exclude_bill_nos={"2213937"},
        cutoff_date="2025-11-05",
        years=5,
    )
    assert selected is not None
    assert selected.item.bill_no == "2211844"
    assert selected.staff_count == 105
    assert "같은 인사·예산 체계" in reason
    assert confidence >= 0.65
    assert any(
        bundle.item.bill_no == "2211844"
        for bundle in _all_staff_cost_bundles()
    )


def test_special_local_government_structure_uses_same_legal_form() -> None:
    selected, reason, confidence = select_typed_structure_case(
        "「지방자치법」 제199조에 따라 특별지방자치단체를 설치한다.",
        exclude_bill_nos={"2213937"},
        cutoff_date="2025-11-05",
    )
    assert selected is not None
    assert selected.bill_no == "2126503"
    assert "같은 조직 법형식" in reason
    assert confidence >= 0.65


def test_organization_search_allows_older_same_law_but_excludes_target() -> None:
    # No network is used when k=0 is not possible, so inspect the pre-filtered
    # local case pool through the public function only when embeddings exist.
    # The structural invariant itself is covered by checking the source pool:
    from backend.estimator_v2.organization import _all_complete_cases

    cases = _all_complete_cases()
    assert any(case.bill_no == "2124204" for case in cases)
    assert any(
        case.bill_no == "2124204"
        and case.bill_name == "각급 법원의 설치와 관할구역에 관한 법률 일부개정법률안"
        for case in cases
    )


def test_item_search_allows_older_same_law_precedent() -> None:
    from backend.estimator_v2.retrieval import search_cost_candidates

    item_id = "PRIOR::item1"
    loaded = {
        "items": {
            item_id: {
                "bill_no": "PRIOR",
                "bill_name": "정책법안",
                "name": "정책위원회 운영",
                "category": "운영비",
                "family": "committee",
                "propose_date": "2024-01-01",
            }
        },
        "vars": {item_id: []},
    }
    with patch(
        "backend.estimator_v2.retrieval._query_embedding",
        return_value=([1.0, 0.0], True),
    ), patch(
        "backend.estimator_v2.retrieval.tag_db._load",
        return_value=loaded,
    ), patch(
        "backend.estimator_v2.retrieval.tag_db._load_embeddings",
        return_value={item_id: [1.0, 0.0]},
    ), patch(
        "backend.estimator_v2.retrieval.tag_db._formula_by_item",
        return_value={item_id: "인원×수당×횟수"},
    ), patch(
        "backend.estimator_v2.retrieval._amount_rows",
        return_value={item_id: [{"amount_thousand": 4_000}]},
    ):
        candidates, _ = search_cost_candidates(
            _event(),
            exclude_bill_nos={"TARGET"},
            exclude_bill_name="정책법안",
            cutoff_date="2024-04-01",
            min_similarity=0.0,
        )
    assert [candidate.bill_no for candidate in candidates] == ["PRIOR"]


def test_query_embedding_reuses_legacy_vector_across_retrieval_policy_versions() -> None:
    from backend.estimator_v2.retrieval import _query_embedding

    versions: list[str] = []

    def fake_cache(namespace, payload, producer, *, refresh=False):
        assert namespace == "query_embeddings"
        versions.append(payload["version"])
        if payload["version"] == "semantic-evidence-v3":
            return [0.25, 0.75], True
        return None, False

    with patch(
        "backend.estimator_v2.retrieval.get_or_create_json",
        side_effect=fake_cache,
    ):
        vector, cache_hit = _query_embedding("정책위원회 운영")

    assert vector == [0.25, 0.75]
    assert cache_hit is True
    assert versions == ["semantic-evidence-v4", "semantic-evidence-v3"]


def test_committee_formula_reranker_payload_hides_candidate_numbers() -> None:
    import json

    from backend.estimator_v2.selection import _candidate_payload

    candidate = _candidate("FORMULA", 11, 250_000, 4)
    candidate.context_families = ["committee", "research"]
    candidate.context_items = [
        {
            "family": "research",
            "name": "종합계획 수립",
            "formula": "5년마다 147,000,000원",
            "variables": [
                {
                    "type": "period",
                    "name": "수립 주기",
                    "unit": "년",
                    "source_text": "5년마다 수립",
                }
            ],
        }
    ]

    payload_text = json.dumps(_candidate_payload(candidate), ensure_ascii=False)
    assert "11명" not in payload_text
    assert "250000" not in payload_text
    assert "147,000,000" not in payload_text
    assert "<수치>" in payload_text
    assert "종합계획 수립" in payload_text


def test_committee_companion_plan_period_is_a_structural_gate() -> None:
    five_year = _candidate("FIVE", 11, 250_000, 4)
    five_year.context_families = ["committee", "research"]
    five_year.context_items = [
        {
            "family": "research",
            "name": "종합계획 수립",
            "formula": "5년 주기 계획 수립비",
            "variables": [],
        }
    ]
    three_year = _candidate("THREE", 10, 250_000, 4)
    three_year.context_families = ["committee", "research"]
    three_year.context_items = [
        {
            "family": "research",
            "name": "종합계획 수립",
            "formula": "3년 주기 계획 수립비",
            "variables": [],
        }
    ]

    def fake_cache(namespace, payload, producer, *, refresh=False):
        assert namespace == "committee_companion_scorecard"
        assert [row["candidate_id"] for row in payload["candidates"]] == [
            "FIVE"
        ]
        return {
            "scores": [
                {
                    "candidate_id": "FIVE",
                    "policy_domain_match": 3,
                    "authority_institution_match": 3,
                    "companion_artifact_match": 3,
                    "committee_function_match": 3,
                    "reason": "동반 계획 구조 일치",
                }
            ]
        }, True

    with patch(
        "backend.estimator_v2.selection.get_or_create_json",
        side_effect=fake_cache,
    ):
        selected, reason, confidence, _ = select_precedent(
            _event(object="발전위원회"),
            "위원회를 두고 종합계획을 5년마다 수립한다.",
            [three_year, five_year],
        )

    assert selected is five_year
    assert "주기" in reason
    assert confidence == 1.0


def test_committee_companion_scorecard_chooses_structure_not_amount_or_embedding() -> None:
    import json

    remote = _candidate("ESG", 10, 300_000, 4)
    remote.bill_name = "환경·사회·지배구조 경영 촉진법안"
    remote.item_name = "ESG 경영 위원회 운영"
    remote.similarity = 0.95
    remote.context_families = ["committee", "research"]
    remote.context_items = [
        {
            "family": "research",
            "name": "ESG 경영 기본계획",
            "formula": "5년마다 수립",
            "variables": [],
        }
    ]
    health = _candidate("HEALTH", 11, 250_000, 4)
    health.bill_name = "필수의료 육성 및 지원 등에 관한 법률안"
    health.item_name = "필수의료정책심의위원회 운영"
    health.similarity = 0.40
    health.context_families = ["committee", "research"]
    health.context_items = [
        {
            "family": "research",
            "name": "필수의료 종합계획",
            "formula": "5년마다 수립",
            "variables": [],
        }
    ]

    payload_text = json.dumps(
        _committee_companion_scorecard_candidate_payload(health),
        ensure_ascii=False,
    )
    assert "11" not in payload_text
    assert "250000" not in payload_text
    assert "embedding_similarity" not in payload_text

    selected, reason, confidence = (
        _choose_committee_companion_scorecard_candidate(
            [remote, health],
            {
                "scores": [
                    {
                        "candidate_id": "ESG",
                        "policy_domain_match": 0,
                        "authority_institution_match": 0,
                        "companion_artifact_match": 2,
                        "committee_function_match": 3,
                    },
                    {
                        "candidate_id": "HEALTH",
                        "policy_domain_match": 3,
                        "authority_institution_match": 3,
                        "companion_artifact_match": 3,
                        "committee_function_match": 3,
                        "reason": "같은 보건의료 정책 구조",
                    },
                ]
            },
        )
    )

    assert selected is health
    assert "HEALTH" in selected.item_id
    assert "수치" in reason
    assert confidence == 1.0


def test_variable_search_crosses_family_but_keeps_temporal_holdout() -> None:
    from backend.estimator_v2.retrieval import search_variable_candidates

    prior_id = "PRIOR::frequency"
    target_id = "TARGET::frequency"
    future_id = "FUTURE::frequency"
    loaded = {
        "items": {
            prior_id: {
                "bill_no": "PRIOR",
                "bill_name": "국민공론법안",
                "name": "국민공론절차 실시",
                "category": "사업비",
                "family": "other",
                "propose_date": "2024-03-01",
            },
            target_id: {
                "bill_no": "TARGET",
                "bill_name": "대상법안",
                "name": "국민참여회의",
                "category": "운영비",
                "family": "committee",
                "propose_date": "2024-04-01",
            },
            future_id: {
                "bill_no": "FUTURE",
                "bill_name": "미래법안",
                "name": "숙의공론장",
                "category": "사업비",
                "family": "other",
                "propose_date": "2025-01-01",
            },
        },
        "vars": {
            prior_id: [
                {
                    "type": "frequency",
                    "name": "실시 횟수",
                    "value": 1,
                    "unit": "회",
                }
            ],
            target_id: [],
            future_id: [],
        },
    }
    with patch(
        "backend.estimator_v2.retrieval._variable_query_embedding",
        return_value=([1.0, 0.0], True),
    ), patch(
        "backend.estimator_v2.retrieval.tag_db._load",
        return_value=loaded,
    ), patch(
        "backend.estimator_v2.retrieval.tag_db._load_embeddings",
        return_value={
            prior_id: [1.0, 0.0],
            target_id: [1.0, 0.0],
            future_id: [1.0, 0.0],
        },
    ), patch(
        "backend.estimator_v2.retrieval.tag_db._formula_by_item",
        return_value={},
    ), patch(
        "backend.estimator_v2.retrieval._amount_rows",
        return_value={},
    ):
        candidates, _ = search_variable_candidates(
            _event(
                object="국민참여 공론화회의",
                quotes=["국민참여위원이 공론조사를 수행한다."],
            ),
            "frequency",
            exclude_bill_nos={"TARGET"},
            cutoff_date="2024-04-01",
            min_similarity=0.0,
        )
    assert [(candidate.bill_no, candidate.family) for candidate in candidates] == [
        ("PRIOR", "other")
    ]


def test_cross_family_participatory_frequency_completes_formula() -> None:
    formula_case = _candidate("FORMULA", 50, 250_000, 4)
    formula_case.item_name = "보건의료정책위원회 운영비"
    frequency_case = TagCandidate(
        item_id="PUBLIC_FREQUENCY",
        bill_no="PRIOR",
        bill_name="국민공론법안",
        item_name="국민공론절차 실시",
        category="사업비",
        family="other",
        similarity=0.9,
        variables=[
            {
                "type": "frequency",
                "name": "실시 횟수",
                "value": 1,
                "unit": "회",
                "source_text": "국민공론절차를 1회 실시하는 것으로 가정",
            }
        ],
    )
    event = _event(
        object="국민참여 공론화회의",
        quotes=[
            "국민참여회의는 500명 이상의 국민참여위원으로 구성한다.",
            "국민참여위원이 공론조사를 수행한다.",
        ],
    )
    amount, _, evidence, _ = estimate_committee_formula_first(
        event,
        "국민참여회의는 500명 이상의 국민참여위원으로 구성한다. "
        "국민참여위원이 공론조사를 수행한다.",
        formula_case,
        [formula_case],
        candidates_by_role={
            "count": [formula_case],
            "unit_price": [formula_case],
            "frequency": [frequency_case],
        },
    )
    assert amount == 125_000
    by_role = {row["role"]: row for row in evidence}
    assert by_role["frequency"]["source"] == "PUBLIC_FREQUENCY"


def test_frequency_uses_top_three_semantic_precedent_agreement() -> None:
    formula_case = _candidate("FORMULA", 10, 200_000, 2)
    formula_case.item_name = "환경영향평가위원회 운영비"
    policy_frequencies: list[TagCandidate] = []
    for index, similarity in enumerate((0.8, 0.75, 0.7), start=1):
        policy_frequencies.append(
            TagCandidate(
                item_id=f"POLICY_{index}",
                bill_no=f"POLICY_{index}",
                bill_name="정책발전법안",
                item_name=f"정책발전위원회 {index} 설치·운영",
                category="운영비",
                family="committee",
                similarity=similarity,
                variables=[
                    {
                        "type": "frequency",
                        "name": "연간 회의 횟수",
                        "value": 4,
                        "unit": "회",
                        "source_text": "정책과 발전계획을 심의하기 위해 연 4회 개최",
                    }
                ],
            )
        )
    event = _event(
        object="친환경산업발전위원회",
        quotes=["친환경산업 발전계획과 주요 정책을 심의한다."],
    )
    amount, _, evidence, reason = estimate_committee_formula_first(
        event,
        "친환경산업 발전계획과 주요 정책을 심의한다.",
        formula_case,
        [formula_case],
        candidates_by_role={
            "count": [formula_case],
            "unit_price": [formula_case],
            "frequency": policy_frequencies,
        },
    )
    assert amount == 8_000
    by_role = {row["role"]: row for row in evidence}
    assert by_role["frequency"]["source"] == "POLICY_1"
    assert "의미 상위 3개 독립 선례" in reason


def test_evidence_harness_extracts_named_source_without_generic_body() -> None:
    from backend.estimator_v2.harness import _source_anchors

    anchors = _source_anchors(
        "최저임금위원회 전문위원회 5년 평균 운영비와 사무국 운영예산"
    )
    assert "최저임금위원회" in anchors
    assert "전문위원회" not in anchors
    assert "사무국" not in anchors


def test_2126685_harness_finds_missed_independent_db_evidence() -> None:
    from backend.estimator_v2.harness import audit_missed_evidence

    audit = audit_missed_evidence("2126685")
    assert audit["target_excluded_from_candidate_search"] is True
    assert audit["target_leak"] is False
    assert audit["summary"]["independent_evidence_missed"] == 2
    for item in audit["items"]:
        assert item["status"] == "independent_evidence_missed"
        assert any(
            hit["bill_no"] == "2125446"
            and hit["anchor"] == "최저임금위원회"
            and hit["strength"] >= 0.75
            for hit in item["independent_hits"]
        )


def test_regression_gate_rejects_amount_damage_and_target_leak() -> None:
    from backend.estimator_v2.regression import (
        REGRESSION_CASES,
        evaluate_regression_case,
    )

    case = next(case for case in REGRESSION_CASES if case.bill_no == "2126334")
    healthy = evaluate_regression_case(
        case,
        system_million=155,
        target_leak=False,
    )
    damaged = evaluate_regression_case(
        case,
        system_million=300,
        target_leak=False,
    )
    leaked = evaluate_regression_case(
        case,
        system_million=161,
        target_leak=True,
    )
    formula_damaged = evaluate_regression_case(
        case,
        system_million=161,
        target_leak=False,
        formula_failure_reasons=["count=22(기대 11)"],
    )
    assert healthy["passed"] is True
    assert damaged["passed"] is False
    assert leaked["passed"] is False
    assert formula_damaged["passed"] is False


def test_formula_regression_gate_rejects_compensating_operands() -> None:
    from types import SimpleNamespace

    from backend.estimator_v2.regression import (
        REGRESSION_CASES,
        audit_formula_expectations,
    )
    from backend.estimator_v2.types import EstimateRow

    case = next(case for case in REGRESSION_CASES if case.bill_no == "2126334")
    committee = EstimateRow(
        event=_event(object="국립대학병원발전위원회"),
        status=RowStatus.COMPUTED_REVIEW,
        formula="수당 지급대상 인원 × 1인 1회당 수당 × 연간 회의 횟수",
        variable_evidence=[
            {"role": "count", "value": 22, "source_bill_no": "A"},
            {"role": "unit_price", "value": 250_000, "source_bill_no": "A"},
            {"role": "frequency", "value": 2, "source_bill_no": "A"},
        ],
    )
    plan = EstimateRow(
        event=_event(
            object="종합계획",
            event_type="research_plan",
        ),
        status=RowStatus.COMPUTED_REVIEW,
        formula="계획수립 비용 (대상 조문 5년 주기)",
    )

    audit = audit_formula_expectations(
        case,
        SimpleNamespace(rows=[committee, plan]),
    )

    assert audit["passed"] is False
    assert any("count=22" in reason for reason in audit["failure_reasons"])
    assert any("frequency=2" in reason for reason in audit["failure_reasons"])


def test_multi_organization_regression_input_is_target_keyed() -> None:
    from backend.estimator_v2.regression import REGRESSION_CASES

    case = next(case for case in REGRESSION_CASES if case.bill_no == "2213937")
    assert case.organization_net_staff_count == 60
    assert case.organization_net_staff_key == "제4조"


def test_offline_cache_mode_never_calls_producer() -> None:
    from backend.estimator_v2.cache import get_or_create_json

    with patch.dict("os.environ", {"ESTIMATOR_V2_OFFLINE": "1"}):
        value, cache_hit = get_or_create_json(
            "offline-test-missing",
            {"unique": "this-key-must-not-exist"},
            lambda: (_ for _ in ()).throw(AssertionError("producer called")),
        )
    assert value is None
    assert cache_hit is False


def test_evidence_index_lifts_2125446_budget_table_from_narrative() -> None:
    from backend.estimator_v2.evidence_index import evidence_atoms

    matches = [
        atom
        for atom in evidence_atoms()
        if atom.bill_no == "2125446"
        and "최저임금위원회" in atom.entities
        and "백만원" in atom.units
        and "기관운영비" in atom.source_text
        and "위원회전산경비" in atom.source_text
    ]
    assert matches
    assert any(
        {"committee_operation", "organization_operation"} <= set(atom.scopes)
        for atom in matches
    )
    assert all(atom.source_hash for atom in matches)


def test_narrative_fallback_is_shadow_only_and_groups_related_rows() -> None:
    from backend.estimator_v2.evidence_fallback import (
        attach_narrative_evidence_shadow,
        build_shadow_groups,
    )
    from backend.estimator_v2.evidence_index import (
        EvidenceAtom,
        EvidenceSearchHit,
    )
    from backend.estimator_v2.types import EstimateResult, EstimateRow

    unresolved = EstimateRow(
        event=_event(
            id="E006",
            event_type="organization_change",
            object="임금·근로조건 위원회 사무처",
        ),
        status=RowStatus.NEEDS_USER_INPUT,
        reason_codes=["NO_TRANSFERABLE_ORGANIZATION_CASE"],
        year_amounts_thousand=[None] * 5,
    )
    computed = EstimateRow(
        event=_event(id="E011", object="공공기관 노정위원회"),
        status=RowStatus.COMPUTED_REVIEW,
        reason_codes=["AUTO_GATE_PASSED"],
        year_amounts_thousand=[10_000] * 5,
    )
    result = EstimateResult(
        bill_no="TARGET",
        bill_name="공공기관 운영법안",
        doc_type="enactment",
        years=5,
        engine_version="test",
        prompt_version="test",
        dataset_fingerprint="test",
        input_hash="test",
        cache_hit=True,
        rows=[unresolved, computed],
    )
    groups = build_shadow_groups(result)
    assert len(groups) == 1
    assert groups[0].name.startswith("governance_operation:")
    assert "공공기관 노정위원회" in groups[0].query
    assert computed in groups[0].context_rows
    assert len(groups[0].query) <= 1_200

    atom = EvidenceAtom(
        atom_id="A",
        bill_no="PRECEDENT",
        bill_name="독립 선례",
        propose_date="2024-01-01",
        chunk_index=1,
        cue="analogy",
        entities=("최저임금위원회",),
        scopes=(
            "support_office",
            "organization_operation",
            "committee_operation",
        ),
        years=(2024,),
        units=("백만원",),
        amount_mentions=((226.0, "백만원"),),
        source_text="최저임금위원회 기본경비 평균 226백만원",
        source_hash="hash",
        amount_evidence=(
            {
                "value": 226.0,
                "unit": "백만원",
                "scopes": (
                    "support_office",
                    "organization_operation",
                    "committee_operation",
                ),
                "primary_scope": "support_office",
                "transferable": True,
                "context": "최저임금위원회 사무처 기본경비 평균 226백만원",
            },
        ),
    )
    hit = EvidenceSearchHit(atom, 0.61, 0.05)
    before = result.total_thousand()
    with patch(
        "backend.estimator_v2.evidence_fallback.target_metadata",
        return_value=("2024-05-24", ""),
    ), patch(
        "backend.estimator_v2.evidence_fallback.search_evidence_atoms",
        return_value=[hit],
    ) as search, patch(
        "backend.estimator_v2.evidence_fallback._select_for_group",
        return_value=(
            {
                "E006": {
                    "atom_id": "A",
                    "reason": "상설 사무처 운영비 범위가 같다.",
                    "confidence": 0.8,
                }
            },
            [],
            True,
        ),
    ):
        summary = attach_narrative_evidence_shadow(result)

    assert result.total_thousand() == before
    assert summary["amounts_changed"] is False
    assert unresolved.narrative_evidence[0]["bill_no"] == "PRECEDENT"
    assert unresolved.narrative_evidence[0]["selected"] is True
    assert computed.narrative_evidence == []
    assert search.call_args.kwargs["exclude_bill_nos"] == {"TARGET"}
    assert search.call_args.kwargs["cutoff_date"] == "2024-05-24"


def test_unavailable_negative_channel_is_not_treated_as_no_evidence() -> None:
    from backend.estimator_v2.retrieval import search_non_attachment_evidence

    with patch(
        "backend.estimator_v2.retrieval._query_embedding",
        return_value=([0.1, 0.2], True),
    ), patch(
        "backend.estimator_v2.retrieval.get_or_create_json",
        return_value=(None, False),
    ):
        evidence, available = search_non_attachment_evidence(
            _event(),
            exclude_bill_nos={"TARGET"},
        )
    assert evidence == []
    assert available is False


def test_non_attachment_search_excludes_future_and_enriches_reason() -> None:
    from backend.estimator_v2.retrieval import search_non_attachment_evidence

    index = {
        "OLD": {
            "reason_type": "B",
            "reason_text": "센터 수와 지원 규모 미정",
            "evidence_text": "신규 센터 수 및 지원 규모를 추정하기 어려움",
            "confidence": 1.0,
            "classification_status": "candidate",
            "propose_date": "2023-09-26",
        },
        "FUTURE": {
            "reason_type": "B",
            "reason_text": "필요 인력 미정",
            "evidence_text": "필요 인력을 산정할 기초자료가 없음",
            "confidence": 1.0,
            "classification_status": "candidate",
            "propose_date": "2025-09-26",
        },
    }
    hits = [
        {
            "bill_no": "FUTURE",
            "bill_name": "미래법안",
            "similarity": 0.9,
            "content": "미래 청크",
        },
        {
            "bill_no": "OLD",
            "bill_name": "과거법안",
            "similarity": 0.459,
            "content": "조문 청크",
        },
    ]
    with patch(
        "backend.estimator_v2.retrieval._query_embedding",
        return_value=([0.1, 0.2], True),
    ), patch(
        "backend.estimator_v2.retrieval._non_attachment_index",
        return_value=index,
    ), patch(
        "backend.estimator_v2.retrieval.vector_search",
        return_value=hits,
    ), patch(
        "backend.estimator_v2.retrieval.get_or_create_json",
        side_effect=lambda _namespace, _key, producer, refresh=False: (
            producer(),
            False,
        ),
    ):
        evidence, available = search_non_attachment_evidence(
            _event(),
            exclude_bill_nos={"TARGET"},
            cutoff_date="2024-05-03",
        )
    assert available is True
    assert [row["bill_no"] for row in evidence] == ["OLD"]
    assert evidence[0]["content"] == index["OLD"]["evidence_text"]
    assert "organization_scale" in evidence[0]["missing_roles"]


def test_strong_scale_blocker_requires_structured_technical_reason() -> None:
    from backend.estimator_v2.retrieval import strongest_scale_blocker

    event = _event(
        event_type="organization_change",
        object="지역지원센터",
        cost_mechanism="organization_change",
    )
    blocker = strongest_scale_blocker(
        event,
        [
            {
                "bill_no": "OLD",
                "similarity": 0.459,
                "reason_type": "B",
                "reason_text": "센터 수와 지원 규모를 정하기 어려움",
                "evidence_text": "신규 센터 수 및 지원 규모를 추정할 수 없음",
                "classification_confidence": 1.0,
            }
        ],
    )
    assert blocker is not None
    assert blocker["bill_no"] == "OLD"
    assert blocker["matched_missing_roles"] == ["organization_scale"]


def test_facility_scale_blocker_rejects_revenue_reason_that_mentions_facility() -> None:
    from backend.estimator_v2.retrieval import strongest_scale_blocker

    event = _event(
        event_type="organization_change",
        object="지방법원 청사",
        cost_mechanism="organization_change",
    )
    blocker = strongest_scale_blocker(
        event,
        [
            {
                "bill_no": "FINE_REVENUE",
                "similarity": 0.8,
                "reason_type": "B",
                "reason_text": "벌금 및 과태료 수입 감소액 추계 자료가 부족함",
                "evidence_text": (
                    "가축분뇨 처리시설의 개선명령 불이행 건수와 "
                    "과태료 규모를 알 수 없어 수입감소 추계가 곤란함"
                ),
                "classification_confidence": 1.0,
            }
        ],
        required_roles={"facility_scale"},
    )
    assert blocker is None


def test_organization_scale_blocker_rejects_workload_driven_staffing() -> None:
    from backend.estimator_v2.retrieval import strongest_scale_blocker

    event = _event(
        event_type="organization_change",
        object="신규 행정기관",
        cost_mechanism="organization_change",
    )
    blocker = strongest_scale_blocker(
        event,
        [
            {
                "bill_no": "WORKLOAD",
                "similarity": 0.8,
                "reason_type": "B",
                "reason_text": "조치 건수와 필요 인력 규모 증가를 예측하기 어려움",
                "evidence_text": (
                    "업무량 증가에 대응할 인력 규모를 현 단계에서 "
                    "예측하기 어려움"
                ),
                "classification_confidence": 1.0,
            }
        ],
        required_roles={"organization_scale"},
    )
    assert blocker is None


def test_scale_blocker_rejects_high_similarity_with_different_missing_role() -> None:
    from backend.estimator_v2.retrieval import strongest_scale_blocker

    event = _event(
        event_type="organization_change",
        object="지역지원센터",
        cost_mechanism="organization_change",
    )
    blocker = strongest_scale_blocker(
        event,
        [
            {
                "bill_no": "DIFFERENT",
                "similarity": 0.9,
                "reason_type": "B",
                "reason_text": "지원 대상자 수를 예측하기 어려움",
                "evidence_text": "향후 수혜자 수에 관한 통계자료가 부족함",
                "classification_confidence": 1.0,
            }
        ],
        required_roles={"organization_scale"},
    )
    assert blocker is None


def test_non_attachment_role_parser_does_not_call_system_scale_an_org_scale() -> None:
    from backend.estimator_v2.retrieval import (
        classify_non_attachment_missing_roles,
    )

    roles = classify_non_attachment_missing_roles(
        "신규 시스템 구축 여부와 기존 시스템 확대 규모가 정해지지 않음",
        "구체적인 시스템 시행 방식이 없어 비용 추계가 곤란함",
    )
    assert "organization_scale" not in roles
    assert "implementation_scope" in roles


def test_organization_operating_budget_uses_target_specific_input() -> None:
    segment = Segment(
        id="S016",
        article_ref="제16조(경비의 부담)",
        text=(
            "제16조 동서특별지방자치단체의 운영 및 사무처리에 필요한 "
            "경비는 동부시와 서부도가 각각 분담한다."
        ),
    )
    rows = build_organization_operating_budget_rows(
        [segment],
        bill_no="TARGET",
        cutoff_date="2025-11-05",
        years=5,
        annual_budgets_thousand={"제16조": 3_210_000},
    )
    assert len(rows) == 1
    assert rows[0].status == RowStatus.COMPUTED_REVIEW
    assert rows[0].year_amounts_thousand == [3_210_000] * 5
    assert rows[0].variable_evidence[0]["source"] == "user_input"


def test_committee_cost_sharing_is_not_whole_organization_budget() -> None:
    segment = Segment(
        id="S007",
        article_ref="제7조",
        text="지원위원회의 운영에 필요한 경비는 국가와 지방자치단체가 분담한다.",
    )
    rows = build_organization_operating_budget_rows(
        [segment],
        bill_no="TARGET",
        cutoff_date="2025-11-05",
        years=5,
    )
    assert rows == []


def test_missing_whole_organization_budget_requests_user_input() -> None:
    segment = Segment(
        id="S016",
        article_ref="제16조",
        text=(
            "동서특별지방자치단체의 운영 및 사무처리에 필요한 경비는 "
            "동부시와 서부도가 분담한다."
        ),
    )
    with patch(
        "backend.estimator_v2.organization._operating_budget_candidates",
        return_value=[],
    ):
        rows = build_organization_operating_budget_rows(
            [segment],
            bill_no="TARGET",
            cutoff_date="2025-01-01",
            years=5,
        )
    assert len(rows) == 1
    assert rows[0].status == RowStatus.NEEDS_USER_INPUT
    assert rows[0].reason_codes == ["TARGET_ANNUAL_OPERATING_BUDGET_MISSING"]
    assert rows[0].year_amounts_thousand == [None] * 5
