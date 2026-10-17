from __future__ import annotations

from backend.erce_web.analyzer_v2 import (
    _extract_bill_name,
    _extract_current_bill_no,
    _extract_pdf_text_from_bytes,
    split_articles,
    strip_appendices,
)
from backend.erce_web.committee_estimator_v3.pipeline import _estimate_target
from backend.erce_web.committee_estimator_v3.types import (
    CandidateAudit,
    CommitteeEstimate,
    EvidenceValue,
)
from backend.erce_web.estimator_v2.retrieval import target_metadata

from .precedents import resolve_support_bundle
from .structure import CommitteeNode, extract_committee_nodes, select_formula_plan
from .types import CommitteeEstimateResultV4, CommitteeEstimateV4, FormulaPlan


ENGINE_VERSION = "committee-estimator-v4.1.0"


def _hierarchical_gate(estimate: CommitteeEstimate) -> tuple[bool, str]:
    required = {
        value.key: value
        for value in estimate.variables
        if value.key in {"paid_members", "annual_meetings", "unit_price_won"}
    }
    if set(required) != {"paid_members", "annual_meetings", "unit_price_won"}:
        return False, "필수 계산변수가 완결되지 않음"
    if any(value.value is None for value in required.values()):
        return False, "필수 계산변수에 결측값이 있음"
    if all(value.provenance in {"law_text", "user_confirmed"} for value in required.values()):
        return True, "대상 조문 또는 사용자 확인값"

    selected = estimate.selected_candidate
    if selected is None:
        return False, "완결된 직접 선례 산식이 없음"
    scores = selected.scores
    complete_direct = (
        scores.get("formula_completeness", 0) == 3
        and scores.get("direct_provenance", 0) >= 2
    )
    if not complete_direct:
        return False, "완결성·출처를 동시에 충족하는 선례가 아님"
    if scores.get("institutional_identity", 0) >= 2:
        return True, "같은 제도·기관의 직접 선례"

    paid = required["paid_members"]
    cohort_supported = str(paid.source_id or "").startswith("COHORT:")
    if (
        cohort_supported
        and scores.get("committee_function", 0) >= 2
        and scores.get("profile_evidence", 0) == 3
    ):
        return True, "독립 선례군과 완결된 산식이 각각 전제를 뒷받침"
    if (
        scores.get("committee_function", 0) == 3
        and scores.get("profile_evidence", 0) == 3
        and scores.get("direct_provenance", 0) == 3
        and scores.get("semantic_recall", 0) >= 2
    ):
        return True, "작동 방식과 완결성이 동시에 검증된 직접 선례"
    return False, "단일 유사 선례만으로 숨은 전제를 확정할 수 없음"


def _from_v3(
    node: CommitteeNode,
    plan: FormulaPlan,
    estimate: CommitteeEstimate,
) -> CommitteeEstimateV4:
    eligible, basis = _hierarchical_gate(estimate)
    decision = "numeric_draft" if eligible else "human_input_required"
    status = estimate.status if eligible else "review_required"
    reason_codes = list(estimate.reason_codes)
    if not eligible and "HIERARCHICAL_EVIDENCE_INSUFFICIENT" not in reason_codes:
        reason_codes.append("HIERARCHICAL_EVIDENCE_INSUFFICIENT")
    return CommitteeEstimateV4(
        committee_name=node.name,
        article_refs=list(node.article_refs),
        source_quotes=list(node.texts),
        relations=list(node.relations),
        formula_plan=plan,
        status=status,
        decision=decision,
        reason_codes=reason_codes,
        reason=estimate.reason if eligible else basis,
        variables=list(estimate.variables),
        selected_candidate=estimate.selected_candidate,
        candidate_audits=list(estimate.candidate_audits),
        annual_amount_thousand=(
            estimate.annual_amount_thousand if eligible else None
        ),
        five_year_amount_thousand=(
            estimate.five_year_amount_thousand if eligible else None
        ),
        gross_draft_annual_thousand=(
            estimate.gross_draft_annual_thousand if eligible else None
        ),
        review_fields=list(estimate.review_fields),
    )


def _review_only(node: CommitteeNode, plan: FormulaPlan) -> CommitteeEstimateV4:
    fields = [
        {
            "key": f"component_{index}",
            "label": component,
            "reason": "현재 조문·공식 기준·직접 선례의 근거를 확인해야 합니다.",
        }
        for index, component in enumerate(plan.components, 1)
    ]
    return CommitteeEstimateV4(
        committee_name=node.name,
        article_refs=list(node.article_refs),
        source_quotes=list(node.texts),
        relations=list(node.relations),
        formula_plan=plan,
        status="review_required",
        decision="human_input_required",
        reason_codes=[f"FORMULA_{plan.family.upper()}"],
        reason=(
            f"{plan.selection_basis}. 산식 구조는 확정했지만 구성요소의 "
            "실제 값은 독립 근거나 사용자 확인이 필요합니다."
        ),
        review_fields=fields,
    )


def _support_bundle_estimate(
    node: CommitteeNode,
    plan: FormulaPlan,
    *,
    bill_no: str | None,
    bill_name: str,
    cutoff_date: str | None,
    years: int,
    refresh: bool,
) -> CommitteeEstimateV4 | None:
    match = resolve_support_bundle(
        node,
        bill_no=bill_no,
        bill_name=bill_name,
        cutoff_date=cutoff_date,
        refresh=refresh,
    )
    if match is None:
        return None
    values = match.operands
    source_id = match.candidate.item_id
    source_text = match.source_text
    variables = [
        EvidenceValue(
            "main_paid_members", "본위원회 수당 지급대상",
            values.main_paid_members, "명", "precedent", source_id, source_text,
        ),
        EvidenceValue(
            "subordinate_paid_members", "하위위원회 수당 지급대상",
            values.subordinate_paid_members, "명", "precedent", source_id, source_text,
        ),
        EvidenceValue(
            "annual_meetings", "각 위원회 연간 회의 횟수",
            values.annual_meetings, "회/년", "precedent", source_id, source_text,
        ),
        EvidenceValue(
            "unit_price_won", "1인 1회당 수당",
            values.unit_price_won, "원", "precedent", source_id, source_text,
        ),
        EvidenceValue(
            "support_annual_budget_thousand", "지원조직 연간 운영비",
            float(values.support_annual_budget_thousand), "천원/년",
            "precedent", source_id, source_text,
        ),
    ]
    annual = values.annual_amount_thousand
    audit = CandidateAudit(
        item_id=match.candidate.item_id,
        bill_no=match.candidate.bill_no,
        bill_name=match.candidate.bill_name,
        item_name=match.candidate.item_name,
        embedding_similarity=match.candidate.similarity,
        scores={
            "relation_identity": 3,
            "formula_completeness": 5,
            "direct_provenance": 3,
            "independent_support": min(match.independent_support_count, 3),
        },
        accepted=True,
    )
    return CommitteeEstimateV4(
        committee_name=node.name,
        article_refs=list(node.article_refs),
        source_quotes=list(node.texts),
        relations=list(node.relations),
        formula_plan=plan,
        status="computed_review",
        decision="numeric_draft",
        reason_codes=["STRUCTURE_IDENTICAL_COMPOUND_PRECEDENT"],
        reason=(
            "하위위원회·지원조직 관계와 전체 산식 구성요소가 모두 "
            f"일치하는 독립 선례 {match.independent_support_count}건을 확인했습니다. "
            "시행 첫해 일할·물가상승률은 반영하지 않은 경상가 초안입니다."
        ),
        variables=variables,
        selected_candidate=audit,
        candidate_audits=[audit],
        annual_amount_thousand=annual,
        five_year_amount_thousand=annual * years,
        gross_draft_annual_thousand=annual,
    )


def estimate_committee_from_pdf_v4(
    pdf_bytes: bytes,
    *,
    filename: str = "uploaded.pdf",
    years: int = 5,
    user_inputs: dict[str, dict[str, float | bool]] | None = None,
    refresh: bool = False,
) -> CommitteeEstimateResultV4:
    raw_text = _extract_pdf_text_from_bytes(pdf_bytes)
    if not raw_text:
        raise ValueError("PDF에서 텍스트를 추출하지 못했습니다.")
    legal_text = strip_appendices(raw_text)
    articles, _ = split_articles(legal_text)
    if not articles:
        raise ValueError("법안 조문을 분리하지 못했습니다.")

    bill_no = _extract_current_bill_no(raw_text, filename)
    bill_name = _extract_bill_name(legal_text, filename)
    cutoff_date, stored_name = target_metadata(bill_no)
    nodes = extract_committee_nodes(articles)
    estimates: list[CommitteeEstimateV4] = []
    for node in nodes:
        plan = select_formula_plan(node)
        if plan.family == "committee_support_bundle":
            resolved = _support_bundle_estimate(
                node,
                plan,
                bill_no=bill_no,
                bill_name=stored_name or bill_name,
                cutoff_date=cutoff_date,
                years=years,
                refresh=refresh,
            )
            estimates.append(resolved or _review_only(node, plan))
            continue
        if plan.family != "meeting_allowance":
            estimates.append(_review_only(node, plan))
            continue
        matched_inputs = None
        for selector, values in (user_inputs or {}).items():
            if selector == node.name or selector in node.name:
                matched_inputs = values
                break
        v3_estimate = _estimate_target(
            node.as_v3_target(),
            bill_no=bill_no,
            bill_name=stored_name or bill_name,
            cutoff_date=cutoff_date,
            years=years,
            user_inputs=matched_inputs,
            refresh=refresh,
        )
        estimates.append(_from_v3(node, plan, v3_estimate))

    warnings = [
        "v4는 조문 개수를 고정 범위로 묶지 않고 명시적 설치 관계로 위원회 경계를 만듭니다.",
        "산식군을 먼저 선택한 뒤 회의수당형에서만 v3 의미검색과 계층형 근거 게이트를 사용합니다.",
        "복수기관·하위기구 단독·상근인력 산식은 일반 회의수당 선례로 자동 계산하지 않습니다.",
        "지원조직 복합형은 관계와 전체 피연산자가 일치하는 직접 선례에서만 숫자 초안을 냅니다.",
        "대상 의안의 공식 정답 추계서는 런타임에서 읽지 않습니다.",
    ]
    if not nodes:
        warnings.append("원문으로 근거링할 수 있는 위원회 설치 사건이 없습니다.")
    return CommitteeEstimateResultV4(
        bill_no=bill_no,
        bill_name=bill_name,
        engine_version=ENGINE_VERSION,
        years=years,
        estimates=estimates,
        warnings=warnings,
    )
