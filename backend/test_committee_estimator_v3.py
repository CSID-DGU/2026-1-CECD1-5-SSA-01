from __future__ import annotations

from backend.committee_estimator_v3.pipeline import (
    _CommitteeTarget,
    _candidate_audit,
    _cohort_paid_member_count,
    _event_driven_result,
    _find_targets,
    _has_compound_committee_scope,
    _is_multi_instance,
    _manual_evidence_result,
    _organization_scope_context,
    _precedent_disagreement,
)
from backend.committee_estimator_v3 import pipeline as committee_pipeline
from backend.committee_estimator_v3 import evidence_store
from backend.estimator_v2.types import AtomicEvent, TagCandidate
from backend.committee_estimator_v3.types import CandidateAudit


def _target(context: str, name: str = "발전위원회") -> _CommitteeTarget:
    event = AtomicEvent(
        id="COMMITTEE-001",
        segment_ids=[],
        article_refs=["제3조", "제4조", "제14조"],
        quotes=[context],
        actor="장관",
        action="설치 및 운영",
        object=name,
        bearer="state",
        event_type="committee_operation",
        obligation="mandatory",
        cost_mechanism="internal_administration",
        additionality="explicit_new_or_expanded",
        recurrence_text="",
        explanation="",
    )
    return _CommitteeTarget(
        name=name,
        article_refs=("제3조", "제4조", "제14조"),
        texts=(context,),
        change_type="제정",
        event=event,
    )


def _candidate(
    *,
    bill_no: str,
    name: str,
    count: float,
    meetings: float = 4,
    unit_price: float = 250_000,
) -> TagCandidate:
    return TagCandidate(
        item_id=f"{bill_no}::item1",
        bill_no=bill_no,
        bill_name=name,
        item_name=name,
        category="운영비",
        family="committee",
        similarity=0.55,
        variables=[
            {"type": "target_count", "name": "민간위원 수", "value": count, "unit": "명", "source_text": "민간위원 직접 산정"},
            {"type": "frequency", "name": "연간 회의 횟수", "value": meetings, "unit": "회", "source_text": "직접 운영 실적"},
            {"type": "unit_cost", "name": "회의 참석수당", "value": unit_price, "unit": "원", "source_text": "예산지침 직접 적용"},
        ],
        amounts=[],
        formula="민간위원 수 × 연간 회의 횟수 × 회의 참석수당",
    )


def test_find_targets_uses_establishment_article_and_following_composition() -> None:
    articles = [
        {
            "no": "제3조(농업발전위원회)",
            "text": "농업 발전계획을 심의하기 위하여 장관 소속으로 농업발전위원회를 둔다.",
            "change_type": "신설",
        },
        {
            "no": "제4조(위원회의 구성)",
            "text": "위원회는 위원장을 포함한 25명 이내의 위원으로 구성한다.",
            "change_type": "신설",
        },
    ]
    targets = _find_targets(articles)
    assert len(targets) == 1
    assert targets[0].name == "농업발전위원회"
    assert "25명" in targets[0].context


def test_page_marker_inside_establishment_verb_is_removed() -> None:
    articles = [
        {
            "no": "제3조(환경발전위원회)",
            "text": "환경 발전계획을 심의하기 위하여 환경발전위원회를 둔 - 4 - 다.",
            "change_type": "신설",
        }
    ]
    targets = _find_targets(articles)
    assert [target.name for target in targets] == ["환경발전위원회"]


def test_legal_title_prefix_is_not_part_of_established_committee_name() -> None:
    articles = [
        {
            "no": "제49조의4(전북자치도갯벌관리위원회 설치에 관한 특례)",
            "text": "전북자치도에 갯벌관리위원회를 둔다.",
            "change_type": "신설",
        }
    ]
    targets = _find_targets(articles)
    assert [target.name for target in targets] == ["갯벌관리위원회"]


def test_support_body_clause_does_not_create_a_second_committee() -> None:
    articles = [
        {
            "no": "제3조(정책위원회)",
            "text": "정책을 심의하기 위하여 정책위원회를 둔다.",
            "change_type": "신설",
        },
        {
            "no": "제4조(위원회의 지원)",
            "text": "위원회에는 사무국을 둘 수 있다.",
            "change_type": "신설",
        },
    ]
    targets = _find_targets(articles)
    assert [target.name for target in targets] == ["정책위원회"]


def test_subcommittee_clause_stays_attached_to_main_committee_target() -> None:
    articles = [
        {
            "no": "제6조(헌법개정자문위원회의 설치)",
            "text": "전문가의 의견을 수렴하기 위하여 헌법개정자문위원회를 둘 수 있다.",
            "change_type": "제정",
        },
        {
            "no": "제7조(자문위원회의 구성 및 운영)",
            "text": (
                "자문위원회는 위원장을 포함한 30명 이상의 위원으로 구성한다. "
                "자문위원회는 분과위원회를 둘 수 있다."
            ),
            "change_type": "제정",
        },
        {
            "no": "제8조(국민참여회의 설치)",
            "text": "공론조사를 위하여 국민참여회의를 둔다.",
            "change_type": "제정",
        },
    ]
    targets = _find_targets(articles)
    assert [target.name for target in targets] == ["헌법개정자문위원회"]
    assert "30명 이상" in targets[0].context


def test_unrelated_later_article_cannot_make_committee_organization_heavy() -> None:
    target = _target("정책위원회를 둔다.", "정책위원회")
    target = _CommitteeTarget(
        name=target.name,
        article_refs=("제3조(정책위원회 설치)", "제20조(업무계획)"),
        texts=(
            "정책위원회를 둔다.",
            "업무계획을 소관 상임위원회에 보고한다.",
        ),
        change_type="제정",
        event=target.event,
    )
    assert "상임위원회" not in _organization_scope_context(target)


def test_multi_instance_committee_is_detected_from_establishment_clause() -> None:
    target = _target(
        "지방자치단체에 지역 정책을 심의하기 위하여 지역정책위원회를 둔다.",
        "지역정책위원회",
    )
    assert _is_multi_instance(target)


def test_later_local_government_reference_does_not_make_central_body_multi_instance() -> None:
    target = _target(
        "국무총리 소속으로 대전지원위원회를 둔다. 위원은 관계 지방자치단체의 장 중에서 임명한다.",
        "대전지원위원회",
    )
    assert not _is_multi_instance(target)


def test_main_and_subcommittee_are_a_compound_cost_scope() -> None:
    target = _target(
        "임금위원회를 두고, 업무를 효율적으로 수행하기 위하여 9명 이내의 소위원회를 둘 수 있다.",
        "임금위원회",
    )
    assert _has_compound_committee_scope(target)


def test_subcommittee_itself_is_not_recursively_compound() -> None:
    target = _target(
        "업무를 효율적으로 수행하기 위하여 9명 이내의 소위원회를 둘 수 있다.",
        "소위원회",
    )
    assert not _has_compound_committee_scope(target)


def test_operating_function_rejects_forecast_panel_for_strategy_committee() -> None:
    target = _target("25명 이내로 구성하여 농업 육성계획과 발전계획을 심의한다.")
    candidate = _candidate(
        bill_no="A",
        name="보건의료인력 수급추계지원위원회",
        count=22,
    )
    audit = _candidate_audit(target, candidate, target_count=None)
    assert audit.scores["committee_function"] == 0
    assert not audit.accepted


def test_function_classification_uses_only_named_committee_mandate() -> None:
    target = _target("기본계획을 심의하는 발전위원회를 둔다.")
    target = _CommitteeTarget(
        name=target.name,
        article_refs=("제3조", "제4조"),
        texts=(
            "기본계획을 심의하는 발전위원회를 둔다.",
            "별도 사업은 주민참여 의견수렴을 한다.",
        ),
        change_type="제정",
        event=target.event,
    )
    assert committee_pipeline._target_function(target) == "standing_strategy"


def test_exact_precedent_identity_is_not_rejected_as_function_uncertainty() -> None:
    target = _target(
        "신고자 보호 제도를 심의하기 위하여 보호심의위원회를 둔다.",
        "보호심의위원회",
    )
    candidate = _candidate(
        bill_no="A",
        name="보호심의위원회",
        count=5,
        meetings=4,
        unit_price=250_000,
    )
    original = committee_pipeline.candidate_profile
    committee_pipeline.candidate_profile = lambda _candidate: {
        "normalized_name": "보호심의위원회",
        "function_class": "general",
        "lifecycle": "standing",
        "formula_signature": "paid_members*annual_meetings*meeting_unit_price",
        "profile_status": "partial",
    }
    try:
        audit = _candidate_audit(target, candidate, target_count=None)
    finally:
        committee_pipeline.candidate_profile = original
    assert audit.scores["institutional_identity"] == 3
    assert audit.accepted


def test_second_order_operands_require_strong_structural_identity() -> None:
    target = _target(
        "위원회는 20명 이내로 구성하여 기본계획을 심의한다.",
        "국가데이터진흥전문위원회",
    )
    candidate = _candidate(
        bill_no="A",
        name="국가데이터진흥위원회",
        count=6,
        meetings=3,
        unit_price=200_000,
    )
    candidate.similarity = 0.85
    for variable in candidate.variables:
        variable["source_text"] = "유사 사례를 참고하여 산정"
    original = committee_pipeline.candidate_profile
    committee_pipeline.candidate_profile = lambda _candidate: {
        "normalized_name": "국가데이터진흥위원회",
        "function_class": "standing_strategy",
        "lifecycle": "standing",
        "formula_signature": "paid_members*annual_meetings*meeting_unit_price",
        "total_member_count": 20,
        "profile_status": "complete",
    }
    try:
        audit = _candidate_audit(target, candidate, target_count=None)
    finally:
        committee_pipeline.candidate_profile = original
    assert audit.scores["institutional_identity"] == 2
    assert audit.scores["direct_provenance"] == 2
    assert audit.accepted


def test_total_member_cap_does_not_reward_a_larger_paid_subset() -> None:
    target = _target("위원회는 25명 이내로 구성하여 발전계획을 심의한다.")
    eleven = _candidate_audit(
        target,
        _candidate(bill_no="A", name="의료발전계획 정책심의위원회", count=11),
        target_count=None,
    )
    fifteen = _candidate_audit(
        target,
        _candidate(bill_no="B", name="복지발전계획 정책심의위원회", count=15),
        target_count=None,
    )
    assert eleven.scores["target_scale_compatibility"] == 2
    assert fifteen.scores["target_scale_compatibility"] == 2


def test_paid_member_cohort_scales_ratios_when_public_roles_make_top_case_impossible() -> None:
    target = _target(
        "위원회는 당연직위원과 위촉직위원을 포함하여 15명 이내로 구성한다.",
        "정책심의위원회",
    )
    first = _candidate(bill_no="A", name="전략위원회", count=10)
    second = _candidate(bill_no="B", name="발전위원회", count=14)
    audits = [
        CandidateAudit(
            item_id=candidate.item_id,
            bill_no=candidate.bill_no,
            bill_name=candidate.bill_name,
            item_name=candidate.item_name,
            embedding_similarity=0.5,
            scores={"committee_function": 3},
            accepted=True,
        )
        for candidate in (first, second)
    ]
    profiles = {
        first.item_id: {
            "normalized_name": "전략위원회",
            "profile_status": "complete",
            "total_member_count": 20,
            "paid_member_count": 10,
        },
        second.item_id: {
            "normalized_name": "발전위원회",
            "profile_status": "complete",
            "total_member_count": 20,
            "paid_member_count": 14,
        },
    }
    original = committee_pipeline.candidate_profile
    committee_pipeline.candidate_profile = lambda candidate: profiles[candidate.item_id]
    try:
        result = _cohort_paid_member_count(
            target,
            list(zip((first, second), audits)),
            selected_count=14,
        )
    finally:
        committee_pipeline.candidate_profile = original
    assert result is not None
    assert result[0] == 9
    assert "A,B" in result[1]


def test_reverse_engineered_operand_is_not_direct_evidence() -> None:
    target = _target("위원회는 20명 이내로 구성하여 기본계획을 심의한다.")
    candidate = _candidate(bill_no="A", name="정책심의위원회", count=15, meetings=12, unit_price=150_000)
    candidate.variables[2]["source_text"] = "총 산출금액에서 15만원으로 역산하여 적용"
    audit = _candidate_audit(target, candidate, target_count=None)
    assert not audit.accepted
    assert audit.scores["direct_provenance"] == 0


def test_equally_scored_precedents_with_twofold_disagreement_abstain() -> None:
    target = _target("위원회는 20명 이내로 구성하여 기본계획을 심의한다.")
    candidates = [
        _candidate(bill_no="A", name="정책심의위원회", count=5, meetings=3, unit_price=200_000),
        _candidate(bill_no="B", name="정책심의위원회", count=10, meetings=3, unit_price=200_000),
        _candidate(bill_no="C", name="정책심의위원회", count=15, meetings=4, unit_price=250_000),
    ]
    pairs = [
        (candidate, _candidate_audit(target, candidate, target_count=None))
        for candidate in candidates
    ]
    pairs.sort(key=lambda pair: pair[1].total_score, reverse=True)
    unstable, reason = _precedent_disagreement(pairs)
    assert unstable
    assert "2배 이상 불일치" in reason


def test_event_driven_committee_uses_event_formula_not_annual_formula() -> None:
    target = _target("위원을 선출하거나 지명할 때마다 후보추천위원회를 구성한다.", "후보추천위원회")
    result = _event_driven_result(target)
    assert result.status == "review_required"
    assert result.reason_codes == ["EVENT_DRIVEN_FORMULA_REQUIRED"]
    assert "연도별 위원회 구성 건수" in result.formula


def test_manual_hitl_uses_law_count_and_only_external_values() -> None:
    target = _target("공무원보수위원회는 27명으로 구성하고 공무원 9명에게는 수당을 지급하지 않는다.", "공무원보수위원회")
    result = _manual_evidence_result(
        target,
        years=5,
        inputs={
            "incumbent_paid_members": 10,
            "unit_price_won": 350_000,
            "annual_meetings": 4,
        },
        payable=(18, "조문상 총 27명 - 수당 제외 공무원 9명 = 18명"),
        audits=[],
    )
    assert result.status == "computed"
    assert result.annual_amount_thousand == 11_200
    assert result.five_year_amount_thousand == 56_000
    assert result.calibrated_confidence == 1.0


def test_evidence_layer_fills_only_missing_candidate_roles() -> None:
    candidate = _candidate(
        bill_no="A",
        name="정책위원회",
        count=7,
        meetings=2,
        unit_price=250_000,
    )
    candidate.variables = candidate.variables[:1]
    original = evidence_store.evidence_by_item
    evidence_store.evidence_by_item = lambda: {
        candidate.item_id: [
            {
                "atom_key": "frequency",
                "evidence_role": "annual_meetings",
                "normalized_value": 4,
                "normalized_unit": "회/년",
                "transferability": "review",
                "review_status": "candidate",
                "source_text": "연 4회 직접 운영",
            },
            {
                "atom_key": "price",
                "evidence_role": "meeting_unit_price",
                "normalized_value": 200_000,
                "normalized_unit": "원",
                "transferability": "review",
                "review_status": "candidate",
                "source_text": "예산지침 20만원",
            },
        ]
    }
    try:
        enriched = evidence_store.enrich_candidate(candidate)
    finally:
        evidence_store.evidence_by_item = original
    assert [value["type"] for value in enriched.variables] == [
        "target_count",
        "frequency",
        "unit_cost",
    ]
    assert enriched.variables[0]["value"] == 7
