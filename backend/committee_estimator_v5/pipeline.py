from __future__ import annotations

from backend.analyzer_v2 import (
    _extract_bill_name,
    _extract_current_bill_no,
    _extract_pdf_text_from_bytes,
    split_articles,
    strip_appendices,
)
from backend.committee_estimator_v4 import estimate_committee_from_pdf_v4

from .structure import extract_committee_events, plan_committee_cost
from .types import CommitteeEstimateResultV5, CommitteeEstimateV5


ENGINE_VERSION = "committee-estimator-v5.3.1"


def _key(value: str) -> str:
    return "".join((value or "").replace("ㆍ", "").replace("·", "").split())


def _match_v4(event_name: str, v4_result):
    target = _key(event_name)
    for estimate in v4_result.estimates:
        actual = _key(estimate.committee_name)
        if target and actual and (target in actual or actual in target):
            return estimate
    return None


def estimate_committee_from_pdf_v5(
    pdf_bytes: bytes,
    *,
    filename: str = "uploaded.pdf",
    years: int = 5,
    user_inputs: dict[str, dict[str, float | bool]] | None = None,
    refresh: bool = False,
) -> CommitteeEstimateResultV5:
    raw_text = _extract_pdf_text_from_bytes(pdf_bytes)
    if not raw_text:
        raise ValueError("PDF에서 텍스트를 추출하지 못했습니다.")
    legal_text = strip_appendices(raw_text)
    articles, _ = split_articles(legal_text)
    if not articles:
        raise ValueError("법안 조문을 분리하지 못했습니다.")

    bill_no = _extract_current_bill_no(raw_text, filename)
    bill_name = _extract_bill_name(legal_text, filename)
    events = extract_committee_events(raw_text, articles)

    # v4 remains the evidence executor for formula shapes it already handles.
    # v5 never changes a component topology merely because v4 lacks operands.
    v4_result = estimate_committee_from_pdf_v4(
        pdf_bytes,
        filename=filename,
        years=years,
        user_inputs=user_inputs,
        refresh=refresh,
    )
    estimates: list[CommitteeEstimateV5] = []
    for event in events:
        plan = plan_committee_cost(event)
        prior = _match_v4(event.name, v4_result)
        executable_simple = (
            plan.family == "meeting_allowance"
            and prior is not None
            and prior.formula_plan.family == "meeting_allowance"
        )
        numeric = bool(
            executable_simple
            and prior.decision == "numeric_draft"
            and prior.five_year_amount_thousand is not None
        )
        selected_scores = (
            prior.selected_candidate.scores
            if prior is not None and prior.selected_candidate is not None
            else {}
        )
        trusted_gross_draft = bool(
            executable_simple
            and prior.decision == "numeric_draft"
            and prior.gross_draft_annual_thousand is not None
            and event.change_kind == "establishment"
            and selected_scores.get("institutional_identity", 0) >= 2
            and selected_scores.get("formula_completeness", 0) == 3
            and selected_scores.get("direct_provenance", 0) == 3
        )
        numeric = numeric or trusted_gross_draft
        annual_amount = None
        five_year_amount = None
        if numeric:
            annual_amount = (
                prior.annual_amount_thousand
                if prior.annual_amount_thousand is not None
                else prior.gross_draft_annual_thousand
            )
            five_year_amount = (
                prior.five_year_amount_thousand
                if prior.five_year_amount_thousand is not None
                else annual_amount * years
            )
        variables = []
        selected_bill = None
        if executable_simple:
            variables = [
                {
                    "key": value.key,
                    "label": value.label,
                    "value": value.value,
                    "unit": value.unit,
                    "provenance": value.provenance,
                    "source_id": value.source_id,
                    "source_text": value.source_text,
                }
                for value in prior.variables
            ]
            selected_bill = (
                prior.selected_candidate.bill_no
                if prior.selected_candidate is not None
                else None
            )
        if executable_simple and prior.review_fields:
            missing_fields = [
                {**field, "optional": False}
                for field in prior.review_fields
            ]
        else:
            missing_fields = [
                {
                    "key": operand,
                    "label": operand,
                    "reason": (
                        "선택적 구성요소로 실제 운영 여부를 먼저 확인해야 합니다."
                        if not component.required
                        else "조문·공식 기준·독립 선례 중 하나의 직접 근거가 필요합니다."
                    ),
                    "optional": not component.required,
                }
                for component in plan.components
                for operand in component.operands
            ]
        missing_fields += [
            {
                "key": f"optional_subordinate:{name}",
                "label": f"{name} 실제 운영 여부",
                "reason": "둘 수 있는 재량규정이므로 실제 운영할 때만 계상합니다.",
                "optional": True,
            }
            for name in event.optional_subordinate_bodies
        ]
        estimates.append(CommitteeEstimateV5(
            committee_name=event.name,
            article_refs=list(event.article_refs),
            source_quotes=list(event.texts),
            change_kind=event.change_kind,
            multiplicity=event.multiplicity,
            formula_plan=plan,
            status="computed_review" if numeric else "review_required",
            decision="numeric_draft" if numeric else "human_input_required",
            reason_codes=(
                [
                    "V5_COMPONENT_PLAN_COMPLETE",
                    (
                        "EXPLICIT_NEW_BODY_SAME_INSTITUTION_GROSS_ACCEPTED"
                        if trusted_gross_draft
                        else "V4_EVIDENCE_GATE_PASSED"
                    ),
                ]
                if numeric
                else [
                    "V5_COMPONENT_PLAN_COMPLETE",
                    (
                        "UNCONFIRMED_OPERAND_EVIDENCE"
                        if variables
                        else "OPERAND_EVIDENCE_REQUIRED"
                    ),
                ]
            ),
            reason=(
                "구성요소 산식과 모든 피연산자의 직접 근거가 확인되었습니다."
                if numeric
                else "비용 구조는 확정했지만 모든 필수 변수의 직접 근거가 완결되지 않았습니다."
            ),
            structure_facts={
                "subordinate_bodies": list(event.subordinate_bodies),
                "optional_subordinate_bodies": list(event.optional_subordinate_bodies),
                "support_organizations": list(event.support_organizations),
                "has_standing_members": event.has_standing_members,
                "has_standing_staff": event.has_standing_staff,
            },
            variables=variables,
            selected_precedent_bill=selected_bill,
            annual_amount_thousand=annual_amount,
            five_year_amount_thousand=five_year_amount,
            review_fields=[] if numeric else missing_fields,
        ))

    warnings = [
        "v5는 산식군 하나를 결측 여부로 바꾸지 않고 비용 구성요소를 먼저 조립합니다.",
        "설치·범위확대·위원구성 개편을 서로 다른 법률 변화 사건으로 탐지합니다.",
        "대상 의안의 공식 정답 추계서는 런타임에서 읽지 않습니다.",
        "필수 구성요소의 근거가 완결되지 않으면 숫자를 생성하지 않습니다.",
    ]
    if "전부개정법률안" in "".join(raw_text.split())[:1200]:
        warnings.append(
            "전부개정안에서 기존 제도의 재서술은 신규 비용으로 보지 않고, "
            "명시적 하위기구·사무조직 관계의 증분만 후보로 유지합니다."
        )
    return CommitteeEstimateResultV5(
        bill_no=bill_no,
        bill_name=bill_name,
        engine_version=ENGINE_VERSION,
        years=years,
        estimates=estimates,
        warnings=warnings,
    )
