from __future__ import annotations

import hashlib
import re
from typing import Any

from ..analyzer_v2 import (
    _extract_bill_name,
    _extract_current_bill_no,
    _extract_pdf_text_from_bytes,
    split_articles,
    strip_appendices,
)
from .calculation import estimate_selected_precedent, positive_amount
from .detect import (
    detect_atomic_events,
    extract_annex_revision_articles,
    extract_revision_body_articles,
    merge_annex_revision_articles,
    merge_revision_body_articles,
)
from .gates import assess_event
from .organization import (
    build_organization_operating_budget_rows,
    build_organization_rows,
)
from .prior_scope import PRIOR_SCOPE_VERSION, assess_prior_scope
from .recurrence import resolve_recurrence, schedule_amount
from .retrieval import (
    RETRIEVAL_VERSION,
    VARIABLE_RETRIEVAL_VERSION,
    compatible_scale_counterevidence,
    dataset_fingerprint,
    search_companion_formula_candidates,
    search_cost_candidates,
    search_non_attachment_evidence,
    search_variable_candidates,
    strongest_scale_blocker,
    target_metadata,
)
from .selection import (
    RESEARCH_SCORECARD_VERSION,
    SELECTION_VERSION,
    select_precedent,
    usable_candidates,
)
from .types import EstimateResult, EstimateRow, RowStatus
from .variable_selection import (
    VARIABLE_SELECTION_VERSION,
    committee_formula_roles,
    estimate_committee_formula_first,
)


ENGINE_VERSION = "estimator-v2.36.0"


_ORGANIZATION_SCALE_REASON_CODES = {
    "NO_TRANSFERABLE_ORGANIZATION_CASE",
    "NO_SCALABLE_ORGANIZATION_VALUE_CASE",
    "TARGET_ORGANIZATION_SCALE_MISSING",
}
_FACILITY_SCALE_REASON_CODES = {
    "NO_TRANSFERABLE_ORGANIZATION_STRUCTURE",
    "TARGET_FACILITY_SCALE_MISSING",
    "FACILITY_ADDITIONALITY_REQUIRES_CONFIRMATION",
}
_COUNTEREVIDENCE_ROLE_LABELS = {
    "organization_scale": "조직·인력 규모",
    "facility_scale": "시설·공간 규모",
    "beneficiary_volume": "지원 대상 규모",
    "unit_cost": "단가·지급 기준",
    "demand_volume": "수요·처리 건수",
    "implementation_scope": "사업 시행 범위",
    "baseline_data": "기초 실적자료",
}


def _organization_counterevidence_roles(row: EstimateRow) -> set[str]:
    """Return the structured evidence gaps that one organization row awaits."""
    reason_codes = set(row.reason_codes)
    roles: set[str] = set()
    if reason_codes.intersection(_ORGANIZATION_SCALE_REASON_CODES):
        roles.add("organization_scale")
    if reason_codes.intersection(_FACILITY_SCALE_REASON_CODES):
        roles.add("facility_scale")
    if any(
        evidence.get("value") is None
        and str(evidence.get("unit") or "") == "명"
        for evidence in row.variable_evidence
    ):
        roles.add("organization_scale")
    return roles


def _source_text(event: Any, segment_map: dict[str, Any]) -> str:
    return " ".join(
        segment_map[segment_id].text
        for segment_id in event.segment_ids
        if segment_id in segment_map
    )


def _committee_inputs_for_event(
    event: Any,
    inputs: dict[str, dict[str, float]] | None,
) -> dict[str, float] | None:
    """Resolve reusable HITL values by event id, article or object name."""
    if not inputs:
        return None
    for key, values in inputs.items():
        selector = str(key or "").strip()
        if not selector or not isinstance(values, dict):
            continue
        if (
            selector == event.id
            or selector in event.article_refs
            or selector in event.object
        ):
            return values
    return None


def _formula_with_target_recurrence(
    formula: str,
    event_type: str,
    recurrence: Any,
) -> str:
    """Keep precedent unit cost but explain scheduling from the target law.

    A precedent can price one plan correctly while using a four-year cycle.
    When the target article explicitly says five years, copying the old cycle
    into the displayed formula contradicts the schedule even though the
    calculation engine already follows the target.  Replace only that
    explanatory parenthesis; never alter the precedent amount.
    """
    if (
        event_type != "research_plan"
        or recurrence.source != "law_text"
        or recurrence.mode != "every_n_years"
        or not recurrence.interval_years
    ):
        return formula
    cleaned = re.sub(
        r"\(\s*\d+\s*년\s*(?:주기|마다)\s*\)",
        "",
        formula or "",
    ).strip()
    label = f"대상 조문 {recurrence.interval_years}년 주기"
    return f"{cleaned} ({label})" if cleaned else label


def estimate_from_pdf(
    pdf_bytes: bytes,
    *,
    filename: str = "uploaded.pdf",
    years: int = 5,
    refresh: bool = False,
    include_non_attachment_search: bool = True,
    organization_net_staff_count: int | None = None,
    organization_net_staff_counts: dict[str, int] | None = None,
    organization_staffing_scenario: str | None = None,
    organization_annual_operating_budgets_thousand: dict[str, int] | None = None,
    organization_grade_composition: dict[str, float] | None = None,
    committee_variable_inputs: dict[str, dict[str, float]] | None = None,
    committee_draft_fill: bool = False,
    adversarial_verify_committees: bool = False,
    committee_formula_bridge: bool = False,
    subsidy_reclassify: bool = False,
    research_plan_enactment_override: bool = False,
    subsidy_auto_scope: bool = False,
    subsidy_formula_presenter: bool = False,
) -> EstimateResult:
    """Run the evidence-first v2 engine without touching the legacy engine."""
    if organization_staffing_scenario not in {None, "existing_staff", "new_hires"}:
        raise ValueError(
            "organization_staffing_scenario must be existing_staff or new_hires"
        )
    raw_text = _extract_pdf_text_from_bytes(pdf_bytes)
    if not raw_text:
        raise ValueError("PDF에서 텍스트를 추출하지 못했습니다.")
    legal_text = strip_appendices(raw_text)
    articles, doc_type = split_articles(legal_text)
    recovered_articles = extract_revision_body_articles(legal_text)
    original_article_keys = {
        str(article.get("no") or "")
        for article in articles
    }
    articles = merge_revision_body_articles(
        articles,
        recovered_articles,
    )
    recovered_count = sum(
        1
        for article in articles
        if str(article.get("source") or "") == "revision_body"
        and str(article.get("no") or "") not in original_article_keys
    )
    annex_articles = extract_annex_revision_articles(legal_text)
    articles = merge_annex_revision_articles(
        articles,
        annex_articles,
    )
    if not articles:
        raise ValueError("법안 조문을 분리하지 못했습니다.")

    bill_no = _extract_current_bill_no(raw_text, filename)
    bill_name = _extract_bill_name(legal_text, filename)
    cutoff_date, stored_bill_name = target_metadata(bill_no)
    exclusion_name = stored_bill_name or bill_name
    excluded = {bill_no} if bill_no else set()
    (
        events,
        segments,
        detection_cache_hit,
        active_prompt_version,
    ) = detect_atomic_events(articles, refresh=refresh)
    segment_map = {segment.id: segment for segment in segments}
    rows: list[EstimateRow] = []
    warnings: list[str] = []
    # 격리된 opt-in 후처리: 개인 대상 급여 지급 사건이 organization_change로
    # 오분류된 경우만 subsidy로 재교정한다(LLM 프롬프트는 건드리지 않음).
    if subsidy_reclassify:
        from .subsidy_reclassify import (
            SUBSIDY_RECLASSIFY_VERSION,
            reclassify_subsidy_events,
        )

        events, reclassified_count = reclassify_subsidy_events(events)
        if reclassified_count:
            warnings.append(
                f"지원금 재분류 {SUBSIDY_RECLASSIFY_VERSION}: "
                f"{reclassified_count}건을 organization_change에서 subsidy로 교정."
            )
    if recovered_count:
        warnings.append(
            "일괄 신설·개정 구간에서 기존 분리기가 놓친 제목형 조문 "
            f"{recovered_count}건을 개정 본문에서 복구했습니다."
        )
    if annex_articles:
        warnings.append(
            f"본문 제N조 외에 변경 별표·별지 {len(annex_articles)}건을 "
            "비용사건 근거 단위로 포함했습니다."
        )
    prior_scope, prior_scope_warning = assess_prior_scope(
        events,
        target_bill_no=bill_no or "",
        target_bill_name=exclusion_name,
        cutoff_date=cutoff_date,
        refresh=refresh,
    )
    if prior_scope_warning:
        warnings.append(prior_scope_warning)

    organization_rows, organization_event_ids, organization_warnings = build_organization_rows(
        events,
        legal_text,
        bill_no=bill_no,
        cutoff_date=cutoff_date,
        years=years,
        net_staff_count=organization_net_staff_count,
        net_staff_counts=organization_net_staff_counts,
        staffing_scenario=organization_staffing_scenario,
        segment_text_by_id={
            segment_id: segment.text
            for segment_id, segment in segment_map.items()
        },
        refresh=refresh,
    )
    rows.extend(organization_rows)
    warnings.extend(organization_warnings)
    if include_non_attachment_search:
        # Search from the original organization event, before the organization
        # engine decomposes it into personnel/basic-expense/facility rows.
        # Searching from a decomposed "자산취득비" row retrieves generic
        # construction failures instead of counterevidence about the target
        # organization itself.
        source_organization_events = [
            event
            for event in events
            if event.id in organization_event_ids
            and event.event_type == "organization_change"
        ]
        for source_event in source_organization_events:
            negative_evidence, negative_available = (
                search_non_attachment_evidence(
                    source_event,
                    exclude_bill_nos=excluded,
                    cutoff_date=cutoff_date,
                    refresh=refresh,
                    k=5,
                )
            )
            source_segments = set(source_event.segment_ids)
            affected_rows = [
                row
                for row in organization_rows
                if source_segments.intersection(row.event.segment_ids)
            ]
            for row in affected_rows:
                required_roles = _organization_counterevidence_roles(row)
                row.non_attachment_evidence = (
                    compatible_scale_counterevidence(
                        negative_evidence,
                        required_roles=required_roles,
                    )
                    if required_roles
                    else []
                )
                blocker = (
                    strongest_scale_blocker(
                        source_event,
                        row.non_attachment_evidence,
                        required_roles=required_roles,
                    )
                    if required_roles
                    else None
                )
                if (
                    blocker
                    and row.status
                    in {
                        RowStatus.NEEDS_USER_INPUT,
                        RowStatus.NEEDS_EVIDENCE,
                    }
                ):
                    row.status = RowStatus.NEEDS_EVIDENCE
                    row.reason_codes.append(
                        "NON_ATTACHMENT_SCALE_COUNTEREVIDENCE"
                    )
                    matched_role_labels = ", ".join(
                        _COUNTEREVIDENCE_ROLE_LABELS.get(role, role)
                        for role in blocker["matched_missing_roles"]
                    )
                    row.reason = (
                        f"독립적인 과거 미첨부 선례 {blocker['bill_no']}도 "
                        "현재 행과 같은 종류의 근거가 없으면 합리적 추계가 "
                        "곤란하다고 판단했습니다. 비용이 없다는 뜻이 아니라, "
                        "부족한 변수·추가성 근거를 확인한 뒤 재계산해야 한다는 "
                        f"뜻입니다. 일치한 부족 근거: "
                        f"{matched_role_labels}. "
                        f"근거: {blocker['evidence_text']}"
                    )
                elif not negative_available:
                    row.reason_codes.append(
                        "NON_ATTACHMENT_CHANNEL_UNAVAILABLE"
                    )
    organization_operating_budget_rows = build_organization_operating_budget_rows(
        segments,
        bill_no=bill_no,
        cutoff_date=cutoff_date,
        years=years,
        annual_budgets_thousand=organization_annual_operating_budgets_thousand,
    )
    rows.extend(organization_operating_budget_rows)
    organization_operating_budget_segment_ids = {
        segment_id
        for row in organization_operating_budget_rows
        for segment_id in row.event.segment_ids
    }

    for event in events:
        if event.id in organization_event_ids:
            continue
        if any(
            segment_id in organization_operating_budget_segment_ids
            for segment_id in event.segment_ids
        ):
            # The deterministic legal-form channel owns this clause, avoiding
            # a second LLM-generated row for the same cost event.
            continue
        decision = assess_event(event)
        if research_plan_enactment_override:
            from .research_plan_override import override_research_additionality_gate

            decision = override_research_additionality_gate(
                event, decision, doc_type=doc_type
            )
        if subsidy_auto_scope:
            from .subsidy_auto_scope import override_subsidy_auto_scope_gate

            decision = override_subsidy_auto_scope_gate(event, decision)
        row = EstimateRow(
            event=event,
            status=decision.status,
            reason_codes=list(decision.reason_codes),
            reason=decision.reason,
            year_amounts_thousand=[0] * years,
        )
        if not decision.automatic:
            rows.append(row)
            continue
        scope_decision = prior_scope.get(event.id)
        if scope_decision and scope_decision.status == "unestimable":
            row.status = RowStatus.NEEDS_EVIDENCE
            row.reason_codes.append("PRIOR_SAME_LAW_SCOPE_UNESTIMABLE")
            row.reason = (
                f"대상보다 앞선 동일 법률 선례 {scope_decision.prior_bill_no}에서 "
                "실질적으로 같은 비용사건을 재정수반요인으로 다뤘지만 일부추계 "
                "범위 밖으로 남겼습니다. 먼 의안의 총액을 빌리지 않고 추가 근거를 "
                f"요청합니다. {scope_decision.reason}"
            )
            rows.append(row)
            continue

        formula_candidates, _ = search_cost_candidates(
            event,
            exclude_bill_nos=excluded,
            exclude_bill_name=exclusion_name,
            cutoff_date=cutoff_date,
            refresh=refresh,
            # Committee item embeddings often describe the institution while
            # the reusable formula appears lower in the semantic tail.  Pull
            # a wider recall set, then let the atomic-scope/formula gates and
            # evidence-rich reranker establish precision.
            k=(
                30
                if event.event_type == "committee_operation"
                else 12
                if event.event_type == "research_plan"
                else 10
            ),
            min_similarity=(
                0.40
                if event.event_type in {
                    "committee_operation",
                    "research_plan",
                }
                else 0.48
            ),
        )
        companion_candidates, _ = search_companion_formula_candidates(
            event,
            {candidate_event.event_type for candidate_event in events},
            " ".join(
                [
                    bill_name,
                    *[
                        f"{candidate_event.object} {candidate_event.action}"
                        f" {candidate_event.recurrence_text}"
                        for candidate_event in events
                        if candidate_event.event_type
                        in {"committee_operation", "research_plan"}
                    ],
                ]
            ),
            exclude_bill_nos=excluded,
            cutoff_date=cutoff_date,
            refresh=refresh,
        )
        by_item = {candidate.item_id: candidate for candidate in formula_candidates}
        for candidate in companion_candidates:
            current = by_item.get(candidate.item_id)
            if current is not None:
                current.context_families = candidate.context_families
                current.context_similarity = candidate.context_similarity
                current.context_items = candidate.context_items
                continue
            formula_candidates.append(candidate)
            by_item[candidate.item_id] = candidate
        row.selected_candidates = formula_candidates[:5]
        non_attachment_available = not include_non_attachment_search
        if include_non_attachment_search:
            (
                row.non_attachment_evidence,
                non_attachment_available,
            ) = search_non_attachment_evidence(
                event,
                exclude_bill_nos=excluded,
                cutoff_date=cutoff_date,
                refresh=refresh,
            )
        if not formula_candidates:
            row.status = RowStatus.NEEDS_USER_INPUT
            row.reason_codes.append("NO_SEMANTIC_PRECEDENT")
            row.reason = (
                "동일 비용구조에서 최소 유사도 기준을 넘는 TAG 선례가 없습니다. "
                "글자 겹침으로 대체하지 않고 사용자 근거를 요청합니다."
            )
            rows.append(row)
            continue

        if not non_attachment_available:
            row.status = RowStatus.NEEDS_EVIDENCE
            row.reason_codes.append("NON_ATTACHMENT_CHANNEL_UNAVAILABLE")
            row.reason = (
                "금액 선례는 찾았지만 반대 방향(미첨부) 근거 채널을 확인하지 "
                "못했습니다. 이를 '반대 근거 없음'으로 간주하지 않고 재확인을 "
                "요청합니다."
            )
            rows.append(row)
            continue

        source_text = _source_text(event, segment_map)
        selection_source_text = source_text
        if event.event_type == "committee_operation":
            companion_context = " ".join(
                f"{candidate_event.object} {candidate_event.action} "
                f"{candidate_event.recurrence_text}"
                for candidate_event in events
                if candidate_event.event_type
                in {"committee_operation", "research_plan"}
            )
            if companion_context:
                selection_source_text = (
                    f"{source_text}\n[동일 의안의 동반 비용사건] "
                    f"{companion_context}"
                )
        recurrence = resolve_recurrence(event, source_text, formula_candidates)
        row.recurrence = recurrence
        if recurrence.mode == "unknown":
            row.status = RowStatus.NEEDS_USER_INPUT
            row.reason_codes.append("RECURRENCE_UNRESOLVED")
            row.reason = "조문과 TAG 연도별 계열에서 반복 주기를 확정하지 못했습니다."
            rows.append(row)
            continue

        selected_from_prior_scope = False
        prior_candidates = (
            [
                candidate
                for candidate in formula_candidates
                if scope_decision
                and scope_decision.status == "priced"
                and candidate.bill_no == scope_decision.prior_bill_no
                and positive_amount(candidate) is not None
            ]
            if scope_decision
            else []
        )
        if len(prior_candidates) == 1:
            selected = prior_candidates[0]
            selection_reason = (
                f"대상보다 앞선 동일 법률의 공식 일부추계 "
                f"{scope_decision.prior_bill_no}에서 같은 비용사건을 실제 "
                "금액 항목으로 계산했으므로 이 완결 산식 묶음을 우선했습니다."
            )
            selection_confidence = 1.0
            selected_from_prior_scope = True
        elif prior_candidates:
            (
                selected,
                selection_reason,
                selection_confidence,
                _,
            ) = select_precedent(
                event,
                selection_source_text,
                prior_candidates,
                refresh=refresh,
            )
            selected_from_prior_scope = selected is not None
        else:
            (
                selected,
                selection_reason,
                selection_confidence,
                _,
            ) = select_precedent(
                event,
                selection_source_text,
                formula_candidates,
                refresh=refresh,
            )
        row.selection_method = (
            RESEARCH_SCORECARD_VERSION
            if event.event_type == "research_plan"
            else SELECTION_VERSION
        )
        row.selection_reason = selection_reason
        row.selection_confidence = selection_confidence
        if selected is None:
            row.status = RowStatus.NEEDS_USER_INPUT
            row.reason_codes.append("NO_TRANSFERABLE_PRECEDENT")
            row.reason = (
                "의미 후보 중 산식·규모·주기가 함께 양립하는 단일 선례를 고르지 못했습니다. "
                f"{selection_reason}"
            )
            rows.append(row)
            continue

        amount, formula, variable_evidence = estimate_selected_precedent(
            event.event_type,
            selected,
        )
        variable_reason = ""
        if (
            event.event_type == "committee_operation"
            and not selected_from_prior_scope
        ):
            variable_candidates, _ = search_cost_candidates(
                event,
                exclude_bill_nos=excluded,
                exclude_bill_name=exclusion_name,
                cutoff_date=cutoff_date,
                refresh=refresh,
                # Variable reranking applies hard role/unit/cap gates, so it
                # can safely inspect a wider semantic tail than formula
                # selection.  This is where values that exist in TAG but sit
                # below the formula threshold are recovered.
                k=30,
                min_similarity=0.0,
            )
            variable_candidates_by_role: dict[str, list[Any]] = {}
            for role in ("count", "unit_price", "frequency"):
                role_candidates, _ = search_variable_candidates(
                    event,
                    role,
                    exclude_bill_nos=excluded,
                    cutoff_date=cutoff_date,
                    refresh=refresh,
                )
                combined_role_candidates = [
                    *role_candidates,
                    *formula_candidates,
                    *variable_candidates,
                ]
                variable_candidates_by_role[role] = list(
                    {
                        candidate.item_id: candidate
                        for candidate in combined_role_candidates
                    }.values()
                )
            (
                formula_first_amount,
                formula_first_formula,
                formula_first_evidence,
                variable_reason,
            ) = estimate_committee_formula_first(
                event,
                source_text,
                selected,
                variable_candidates,
                candidates_by_role=variable_candidates_by_role,
                user_inputs=_committee_inputs_for_event(
                    event,
                    committee_variable_inputs,
                ),
                formula_selection_confidence=selection_confidence,
                refresh=refresh,
            )
            if formula_first_amount is not None:
                amount = formula_first_amount
                formula = formula_first_formula
                variable_evidence = formula_first_evidence
            elif committee_formula_roles(selected):
                # A structured atomic formula must succeed operand by operand.
                # Its TAG row total can contain independent sub-costs, so it
                # is not a safe fallback when variable resolution fails.
                amount = None
                formula = formula_first_formula or formula
                variable_evidence = formula_first_evidence
        if amount is None:
            row.status = RowStatus.NEEDS_USER_INPUT
            row.reason_codes.append("SELECTED_PRECEDENT_NOT_COMPUTABLE")
            row.reason = (
                "선택된 선례의 산식·변수·금액이 한 사례 안에서 완결되지 않았습니다. "
                "다른 기능의 선례 값을 억지로 섞지 않고 사용자 입력을 요청합니다."
                + (f" {variable_reason}" if variable_reason else "")
            )
            rows.append(row)
            continue

        # Positive and non-attachment similarities share the same embedding
        # model, but we still do not silently override a close conflict.
        positive_score = selected.similarity
        negative_score = max(
            (
                float(evidence.get("similarity") or 0)
                for evidence in row.non_attachment_evidence
            ),
            default=0.0,
        )
        if negative_score >= positive_score - 0.02 and negative_score >= 0.55:
            row.status = RowStatus.NEEDS_EVIDENCE
            row.reason_codes.append("CONFLICTING_PRECEDENT_CHANNELS")
            row.reason = (
                "금액 선례와 미첨부 선례가 비슷하게 강합니다. "
                "자동으로 한쪽을 고르지 않고 추가성·추계가능성을 확인합니다."
            )
            rows.append(row)
            continue

        row.formula = _formula_with_target_recurrence(
            formula,
            event.event_type,
            recurrence,
        )
        row.variable_evidence = variable_evidence
        row.selected_candidates = [selected]
        row.year_amounts_thousand = schedule_amount(amount, recurrence, years)
        row.reason = (
            f"{decision.reason} 조문/TAG 근거의 반복 주기({recurrence.mode})와 "
            "의미·구조가 가장 적합한 산식을 후보 수치를 숨긴 채 먼저 선택했습니다. "
            "구조 근거가 강한 완결 선례는 산식과 변수 묶음을 유지하고, "
            "빈 변수만 역할·단위·규모·기준시점을 별도로 비교했습니다. "
            f"산식 선택: {selection_reason}"
            + (f" 변수 선택: {variable_reason}" if variable_reason else "")
        )
        rows.append(row)

    if not detection_cache_hit:
        warnings.append(
            "최초 LLM 사건 추출 결과를 입력·모델·프롬프트 해시로 저장했습니다. "
            "동일 조건 재실행은 이 결과를 재사용합니다."
        )
    if not cutoff_date:
        warnings.append("대상 의안의 제안일을 찾지 못해 미래 선례 제외를 확인할 수 없습니다.")
    warnings.append(
        f"검색 정책 {RETRIEVAL_VERSION}: 임베딩 전용, 본인·미래 선례 제외, "
        "과거 동일 법률 선례 허용, "
        f"산식 선택 {SELECTION_VERSION}, 변수 선택 {VARIABLE_SELECTION_VERSION}: "
        "산식의 숫자를 숨기고 구조적으로 선택한 완결 선례는 "
        "하나의 산식·변수 묶음으로 유지, 빈 변수만 역할·단위·규모별 보강, "
        f"변수 검색 {VARIABLE_RETRIEVAL_VERSION}: 비용유형 경계를 넘는 역할 중심 검색."
    )
    if prior_scope:
        warnings.append(
            f"추계 범위 정책 {PRIOR_SCOPE_VERSION}: 대상보다 앞선 동일 법률의 "
            "일부추계 선례로 계상/추계곤란 경계를 먼저 검증했습니다."
        )
    result = EstimateResult(
        bill_no=bill_no,
        bill_name=bill_name,
        doc_type=doc_type,
        years=years,
        engine_version=ENGINE_VERSION,
        prompt_version=active_prompt_version,
        dataset_fingerprint=dataset_fingerprint(),
        input_hash=hashlib.sha256(pdf_bytes).hexdigest(),
        cache_hit=detection_cache_hit,
        rows=rows,
        warnings=warnings,
    )
    # 격리된 additive 후처리: 직급 구성(HITL)이 있을 때만 막힌 인건비 행을
    # 직급별 분해로 교체한다. 없으면 기존 lump 경로가 그대로 유지된다.
    if organization_grade_composition:
        from .grade_salary import GRADE_SALARY_VERSION, apply_grade_decomposition

        if apply_grade_decomposition(
            result, organization_grade_composition, years=years
        ):
            result.warnings.append(
                f"직급별 인건비 분해 적용 {GRADE_SALARY_VERSION}: 직급 구성(HITL)을 "
                "DB 직급별 단가 중앙값으로 분해. 1인당 평균×인원(lump) 대체."
            )
    # 격리된 opt-in 후처리: 변수 0개로 막힌 위원회 행을 조문·코호트 기반 저신뢰
    # 초안으로 채운다(0 대신 확인 가능한 초안). 기본 off, 켤 때만 작동.
    if committee_draft_fill:
        from .committee_fill import COMMITTEE_FILL_VERSION, apply_committee_fill

        filled = apply_committee_fill(result, years=years)
        if filled:
            result.warnings.append(
                f"위원회 저신뢰 초안 채우기 {COMMITTEE_FILL_VERSION}: 막힌 위원회 {filled}행을 "
                "조문 위원 수 + 코호트 회의·수당으로 채움(review 필요)."
            )
    # 격리된 opt-in 후처리: 위원회(committee_operation) 행은 v2가 뭘 계산했든
    # 상관없이 v5(정규식, 안전)의 산식으로 강제 대체한다. 실측상 v2는 위원회
    # 선례 선택에서 확신도와 무관하게 큰 오차·비결정성을 보였다. 위원회는
    # "산식까지만 자동, 숫자는 사람 확인"이 정책이므로 여기서 확정한다.
    if committee_formula_bridge:
        from .committee_bridge import COMMITTEE_BRIDGE_VERSION, apply_committee_v5_override

        bridge_stats = apply_committee_v5_override(
            result, pdf_bytes, filename=filename, years=years
        )
        if bridge_stats.get("overridden"):
            result.warnings.append(
                f"위원회 산식 v5 대체 {COMMITTEE_BRIDGE_VERSION}: "
                f"{bridge_stats['overridden']}건을 안전한 규칙기반 산식으로 교체."
            )
        if bridge_stats.get("v5_only") or bridge_stats.get("v2_only"):
            result.warnings.append(
                f"v2/v5 위원회 탐지 불일치: v5만 발견 {bridge_stats.get('v5_only', 0)}건, "
                f"v2만 발견 {bridge_stats.get('v2_only', 0)}건 (교차 확인 필요)."
            )
    # 격리된 opt-in 후처리: 위원회 선례 선택이 확정(computed_review)된 행만
    # 별도 LLM 반박 호출로 재검증한다. LLM 자기평가 confidence를 그대로 믿지
    # 않고, 반박이 성공하면 확정을 취소해 needs_user_input으로 되돌린다.
    if adversarial_verify_committees:
        from .adversarial_verify import (
            ADVERSARIAL_VERIFY_VERSION,
            apply_adversarial_verification,
        )

        stats = apply_adversarial_verification(result)
        if stats["checked"]:
            result.warnings.append(
                f"위원회 선례 반박검증 {ADVERSARIAL_VERIFY_VERSION}: "
                f"{stats['checked']}건 검증, {stats['refuted']}건 기각."
            )
    # 격리된 opt-in 표시 계층: 지원금 항목이 값 없어 막혀도, 이미 조회된
    # 최유사 후보의 산식·변수명은 보여준다(새 검색·LLM 호출 없음, 숫자는
    # 확정하지 않음).
    if subsidy_formula_presenter:
        from .subsidy_formula_presenter import (
            SUBSIDY_FORMULA_PRESENTER_VERSION,
            present_subsidy_formula,
        )

        presented = present_subsidy_formula(
            result, exclude_bill_nos=excluded, cutoff_date=cutoff_date
        )
        if presented:
            result.warnings.append(
                f"지원금 산식 표시 {SUBSIDY_FORMULA_PRESENTER_VERSION}: "
                f"{presented}건에 최유사 선례 산식을 표시(값은 확인 필요)."
            )
    return result
