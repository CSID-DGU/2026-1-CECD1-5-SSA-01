from __future__ import annotations

import re
from statistics import median
from typing import Any

from .assembly_formula_templates import infer_template_key


EXTERNAL_DATA_TERMS = (
    "대상자",
    "대상 수",
    "인구",
    "수급자",
    "이용자",
    "신청자",
    "시설 수",
    "개소 수",
    "사업량",
    "수요",
    "감면액",
    "과세표준",
    "세수",
    "면적",
    "공사비",
    "건축비",
    "기존 실적",
    "집행률",
    "신청률",
)

POLICY_INPUT_TERMS = (
    "지원 단가",
    "지원금액",
    "지원 규모",
    "운영 규모",
    "배치 인원",
    "소요인력",
    "회의횟수",
    "참석인원",
    "수당 단가",
)


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _title(article: dict[str, Any]) -> str:
    no = str(article.get("no") or "")
    match = re.search(r"\(([^)\n]+)\)", no)
    return match.group(1).strip() if match else no.strip()


def _ref(article: dict[str, Any]) -> str:
    return str(article.get("no") or "").replace("\n", " ").strip()


def _assumption(
    name: str,
    unit: str,
    basis: str,
    source_type: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "value": None,
        "unit": unit,
        "basis": basis,
        "source_type": source_type,
        "needs_user_confirm": True,
    }


def _item(
    *,
    name: str,
    category: str,
    family: str,
    formula: str,
    trigger_ref: str,
    variables: list[str],
    recurrence: str,
    assumptions: list[dict[str, Any]],
    allow_tag_estimate: bool = False,
) -> dict[str, Any]:
    return {
        "name": name,
        "category": category,
        "formula_family": family,
        "formula": formula,
        "trigger_ref": trigger_ref,
        "variables_needed": variables,
        "assumptions": assumptions,
        "calculation": {
            "base_amount_thousand": None,
            "recurrence": recurrence,
            "start_year": 1,
            "end_year": 5,
            "growth_variable": None,
            "source_note": "범용 비용유형 분류에서 생성된 산식 후보",
        },
        "allow_tag_estimate": allow_tag_estimate,
        "requires_review": True,
    }


def _is_institution_bill(articles: list[dict[str, Any]]) -> bool:
    text = _compact(" ".join(str(a.get("text") or "") for a in articles))
    has_establishment = bool(
        re.search(r"(설립|설치하여야|설치한다|법인으로한다)", text)
    )
    has_finance = bool(
        re.search(r"(설립에드는비용|매년인건비|경상적경비|시설확충비|출연또는보조|재정지원)", text)
    )
    return has_establishment and has_finance


def _institution_items(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    finance_article = next(
        (
            article
            for article in articles
            if re.search(
                r"(설립에\s*드는\s*비용|매년\s*인건비|시설확충비|재정\s*지원)",
                str(article.get("text") or ""),
            )
        ),
        articles[0],
    )
    ref = _ref(finance_article)
    title = _title(finance_article)
    subject = re.sub(r"(국가의)?재정지원", "", title).strip() or "신설 기관"
    return [
        _item(
            name=f"{subject} 설립·시설 조성비",
            category="사업비",
            family="institution_establishment",
            formula="부지비 + 설계비 + 공사비 + 장비·비품비",
            trigger_ref=ref,
            variables=["시설 규모", "단위면적당 공사비", "장비·비품비"],
            recurrence="one_time",
            assumptions=[
                _assumption("시설 규모", "㎡", "설립계획 또는 유사기관 규모 자료 필요", "external_data"),
                _assumption("단위면적당 공사비", "천원/㎡", "공공건축 공사비 또는 유사기관 건립비 자료 필요", "external_data"),
                _assumption("장비·비품비", "천원", "설립계획 또는 유사기관 자산취득 자료 필요", "external_data"),
            ],
        ),
        _item(
            name=f"{subject} 인건비",
            category="인건비",
            family="personnel_compensation",
            formula="직급별 인원 × 직급별 1인당 보수 + 기관부담금",
            trigger_ref=ref,
            variables=["직급별 인원", "직급별 1인당 보수", "기관부담요율"],
            recurrence="annual",
            assumptions=[
                _assumption("직급별 인원", "명", "조직·정원 계획 또는 유사기관 인력현황 필요", "external_data"),
                _assumption("직급별 1인당 보수", "천원/명", "보수표 또는 유사기관 인건비 자료 필요", "external_data"),
                _assumption("기관부담요율", "%", "연금·보험 등 기관부담 기준 확인 필요", "external_data"),
            ],
        ),
        _item(
            name=f"{subject} 연간 운영비",
            category="운영비",
            family="institution_operation",
            formula="인건비 연동 기본경비 + 교육·연구·사업 운영비",
            trigger_ref=ref,
            variables=["기본경비 기준액", "연간 사업 운영비"],
            recurrence="annual",
            assumptions=[
                _assumption("기본경비 기준액", "천원/년", "유사기관 결산 또는 운영계획 자료 필요", "external_data"),
                _assumption("연간 사업 운영비", "천원/년", "사업계획 또는 유사기관 운영비 자료 필요", "external_data"),
            ],
        ),
    ]


def build_generalized_estimate(
    articles: list[dict[str, Any]],
    *,
    years: int = 5,
) -> dict[str, Any] | None:
    cost_articles = [
        article
        for article in articles
        if article.get("cost_trigger")
        and str(article.get("cost_candidate_strength") or "medium") != "weak"
    ]
    if not cost_articles:
        return None

    if _is_institution_bill(cost_articles):
        items = _institution_items(cost_articles)
        for item in items:
            item["calculation"]["end_year"] = years
        return {"items": items, "source": "general_formula_engine"}

    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for article in cost_articles:
        text = str(article.get("text") or "")
        compact = _compact(text)
        rule_name = str((article.get("rule_cost_trigger") or {}).get("rule") or "")
        trigger_type = str(article.get("trigger_type") or "")
        title = _title(article)
        ref = _ref(article)

        candidate: dict[str, Any] | None = None
        if rule_name == "survey_or_plan_service" or re.search(r"(실태조사|연구용역)", compact):
            frequency = "1" if re.search(r"연1회|매년", compact) else None
            assumptions = [
                _assumption("용역 단가", "천원/회", "동일·유사 조사 연구용역 계약금액 필요", "external_data"),
                {
                    "name": "수행 횟수",
                    "value": int(frequency) if frequency else None,
                    "unit": "회/년",
                    "basis": "조문에 명시된 수행주기" if frequency else "조문 또는 시행계획의 수행주기 확인 필요",
                    "source_type": "document" if frequency else "policy_input",
                    "needs_user_confirm": not bool(frequency),
                },
            ]
            candidate = _item(
                name=f"{title} 연구용역비",
                category="위탁비",
                family="research_service",
                formula="용역 단가 × 연간 수행 횟수",
                trigger_ref=ref,
                variables=["용역 단가", "수행 횟수"],
                recurrence="annual",
                assumptions=assumptions,
                allow_tag_estimate=True,
            )
        elif rule_name in {"payment_or_subsidy", "new_support_project"} or trigger_type in {"직접지원", "대상확대"}:
            candidate = _item(
                name=f"{title} 지원 소요",
                category="지원금",
                family="transfer_payment",
                formula="지원 대상자 수 × 1인당 지급액 × 지급 횟수 × 집행률",
                trigger_ref=ref,
                variables=["지원 대상자 수", "1인당 지급액", "지급 횟수", "집행률"],
                recurrence="annual",
                assumptions=[
                    _assumption("지원 대상자 수", "명", "행정통계 또는 장래인구·수급자 전망 필요", "external_data"),
                    _assumption("1인당 지급액", "천원/명", "법정 단가 또는 현행 대비 증액분 확인 필요", "external_data"),
                    _assumption("지급 횟수", "회/년", "지급주기 또는 시행기간 확인 필요", "policy_input"),
                    _assumption("집행률", "%", "현행 사업 집행실적 필요", "external_data"),
                ],
            )
        elif (
            rule_name == "facility_or_system" or trigger_type == "시설구축"
        ) and re.search(r"(구축|설치|개발|도입|운영하여야|관리시스템을)", compact):
            candidate = _item(
                name=f"{title} 구축·운영비",
                category="사업비",
                family="facility_system",
                formula="초기 구축비 + 연간 유지관리비",
                trigger_ref=ref,
                variables=["초기 구축비", "연간 유지관리비"],
                recurrence="annual",
                assumptions=[
                    _assumption("초기 구축비", "천원", "정보화·시설 구축계획 또는 유사사업 계약금액 필요", "external_data"),
                    _assumption("연간 유지관리비", "천원/년", "유지관리 요율 또는 유사사업 운영비 필요", "external_data"),
                ],
            )
        elif rule_name == "committee_or_body_operation" or trigger_type == "조직설치":
            candidate = _item(
                name=f"{title} 운영비",
                category="운영비",
                family="committee_operation",
                formula="회의수당 단가 × 회의횟수 × 수당지급대상 인원",
                trigger_ref=ref,
                variables=["회의수당 단가", "회의횟수", "수당지급대상 인원"],
                recurrence="annual",
                assumptions=[
                    _assumption("회의수당 단가", "천원/명", "위원회 수당 기준 또는 유사사례 필요", "external_data"),
                    _assumption("회의횟수", "회/년", "조문 또는 운영계획 확인 필요", "policy_input"),
                    _assumption("수당지급대상 인원", "명", "민간·위촉위원 구성 확인 필요", "policy_input"),
                ],
                allow_tag_estimate=True,
            )

        if not candidate:
            continue
        candidate["calculation"]["end_year"] = years
        key = (candidate["formula_family"], candidate["trigger_ref"])
        if key in seen:
            continue
        seen.add(key)
        items.append(candidate)

    return {"items": items, "source": "general_formula_engine"} if items else None


def merge_generalized_estimate(
    current: dict[str, Any] | None,
    generated: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not generated or not generated.get("items"):
        return current
    if not current or not current.get("items"):
        return generated

    generated_families = {
        str(item.get("formula_family") or "") for item in generated.get("items") or []
    }
    current_families = {
        str(item.get("formula_family") or infer_template_key(item) or "")
        for item in current.get("items") or []
    }
    # Institution establishment is a composite cost model. A lone committee
    # operating item is not an adequate substitute for it.
    if "institution_establishment" in generated_families and "institution_establishment" not in current_families:
        return generated

    merged = dict(current)
    merged_items = list(current.get("items") or [])
    existing_by_key = {
        (
            str(item.get("formula_family") or infer_template_key(item) or ""),
            _compact(item.get("trigger_ref")),
        ): item
        for item in merged_items
    }
    for item in generated.get("items") or []:
        key = (str(item.get("formula_family") or ""), _compact(item.get("trigger_ref")))
        existing = existing_by_key.get(key)
        if existing:
            existing.setdefault("formula_family", item.get("formula_family"))
            existing.setdefault("allow_tag_estimate", item.get("allow_tag_estimate", False))
            if not existing.get("assumptions"):
                existing["assumptions"] = item.get("assumptions") or []
            if not existing.get("variables_needed"):
                existing["variables_needed"] = item.get("variables_needed") or []
            continue
        merged_items.append(item)
        existing_by_key[key] = item
    merged["items"] = merged_items
    merged["source"] = "llm_plus_general_formula_engine"
    return merged


def _token_overlap(a: str, b: str) -> float:
    ca, cb = _compact(a), _compact(b)
    if len(ca) < 2 or len(cb) < 2:
        return 0.0
    ta = {ca[i:i + 2] for i in range(len(ca) - 1)}
    tb = {cb[i:i + 2] for i in range(len(cb) - 1)}
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def _research_subtype(text: Any) -> str | None:
    compact = _compact(text)
    for subtype, terms in (
        ("survey", ("실태조사", "현황조사")),
        ("master_plan", ("기본계획", "종합계획")),
        ("research", ("연구용역", "정책연구")),
    ):
        if any(term in compact for term in terms):
            return subtype
    return None


def apply_tag_formula_evidence(
    estimate: dict[str, Any],
    tag_patterns: list[dict[str, Any]],
) -> int:
    """High-confidence analogous TAG rows become reviewable base amounts.

    Transfer payments, facility construction, and institution creation are
    deliberately excluded because their scale is policy- and population-specific.
    """
    applied = 0
    for item in estimate.get("items") or []:
        if not item.get("allow_tag_estimate"):
            continue
        template_key = str(item.get("formula_family") or infer_template_key(item) or "")
        candidates: list[dict[str, Any]] = []
        for pattern in tag_patterns:
            for tagged in pattern.get("items") or []:
                tagged_probe = {
                    "name": tagged.get("name"),
                    "category": tagged.get("category"),
                    "formula": " ".join(
                        str(row.get("formula") or "") for row in tagged.get("amounts") or []
                    ),
                    "variables_needed": [v.get("name") for v in tagged.get("variables") or []],
                }
                tagged_key = infer_template_key(tagged_probe)
                if template_key and tagged_key and tagged_key != template_key:
                    continue
                annual = [
                    float(row["amount_thousand"])
                    for row in tagged.get("amounts") or []
                    if not row.get("is_total")
                    and row.get("amount_thousand") is not None
                    and float(row["amount_thousand"]) > 0
                ]
                if not annual:
                    continue
                item_name = str(item.get("name") or "")
                tagged_name = str(tagged.get("name") or "")
                name_overlap = _token_overlap(item_name, tagged_name)
                if template_key == "research_service":
                    item_subtype = _research_subtype(item_name)
                    tagged_subtype = _research_subtype(tagged_name)
                    if item_subtype and tagged_subtype and item_subtype != tagged_subtype:
                        continue
                if name_overlap < 0.12:
                    continue
                score = name_overlap
                if item.get("category") == tagged.get("category"):
                    score += 0.25
                if tagged_key == template_key:
                    score += 0.4
                candidates.append({
                    "score": score,
                    "base_amount_thousand": int(round(median(annual))),
                    "bill_no": pattern.get("bill_no"),
                    "bill_name": pattern.get("bill_name"),
                    "item_name": tagged.get("name"),
                    "formula": next(
                        (row.get("formula") for row in tagged.get("amounts") or [] if row.get("formula")),
                        None,
                    ),
                })
        if not candidates:
            continue
        candidates.sort(key=lambda row: float(row["score"]), reverse=True)
        best = candidates[0]
        if float(best["score"]) < 0.45:
            continue
        calc = item.setdefault("calculation", {})
        if calc.get("base_amount_thousand") is None:
            calc["base_amount_thousand"] = best["base_amount_thousand"]
            calc["source_note"] = "유사 비용추계 TAG의 연간 금액 중앙값"
            item["tag_amount_evidence"] = best
            item["requires_review"] = True
            item["review_reason"] = "동일 계산유형의 유사사례 금액을 사용했으므로 적용 적합성 확인 필요"
            applied += 1
    return applied


def classify_estimation_status(
    estimate: dict[str, Any] | None,
    *,
    technical_reason: str | None = None,
) -> dict[str, Any]:
    if technical_reason and not estimate:
        return {
            "code": "technically_infeasible",
            "label": "기술적 추계 곤란",
            "blocking": True,
            "reason": technical_reason,
            "missing": {},
        }
    if not estimate or not estimate.get("items"):
        return {
            "code": "no_cost_formula",
            "label": "산식 후보 없음",
            "blocking": True,
            "reason": "비용항목 또는 산식 후보를 구성하지 못했습니다.",
            "missing": {},
        }

    computed = 0
    estimated = 0
    external: dict[str, list[str]] = {}
    policy: dict[str, list[str]] = {}
    for item in estimate.get("items") or []:
        calc = item.get("calculation") or {}
        yearly_series = calc.get("yearly_amounts_thousand")
        has_series = (
            calc.get("mode") == "yearly_series"
            and isinstance(yearly_series, list)
            and bool(yearly_series)
            and all(value is not None for value in yearly_series)
        )
        if calc.get("base_amount_thousand") is not None or has_series:
            computed += 1
            if item.get("tag_amount_evidence") or item.get("analogy_evidence") or item.get("requires_review"):
                estimated += 1
            continue
        item_name = str(item.get("name") or "비용항목")
        for assumption in item.get("assumptions") or []:
            if assumption.get("value") is not None:
                continue
            name = str(assumption.get("name") or "")
            source_type = str(assumption.get("source_type") or "")
            compact = _compact(name)
            if source_type == "external_data" or any(_compact(term) in compact for term in EXTERNAL_DATA_TERMS):
                external.setdefault(item_name, []).append(name)
            elif source_type == "policy_input" or any(_compact(term) in compact for term in POLICY_INPUT_TERMS):
                policy.setdefault(item_name, []).append(name)
            else:
                external.setdefault(item_name, []).append(name)

    item_count = len(estimate.get("items") or [])
    if computed == item_count:
        code = "computed_with_estimates" if estimated else "computed"
        return {
            "code": code,
            "label": "유사사례 기반 계산 완료" if estimated else "계산 완료",
            "blocking": False,
            "reason": "모든 비용항목의 계산 기준값이 구성되었습니다.",
            "missing": {},
        }
    if computed:
        return {
            "code": "partially_computed",
            "label": "일부 계산",
            "blocking": False,
            "reason": "일부 비용항목은 계산되었으나 추가 자료가 필요한 항목이 남아 있습니다.",
            "missing": {"external_data": external, "policy_input": policy},
        }
    if external:
        return {
            "code": "needs_external_data",
            "label": "외부 통계·기준자료 필요",
            "blocking": True,
            "reason": "산식은 구성되었지만 대상 규모·단가·실적 등 외부 자료가 필요합니다.",
            "missing": {"external_data": external, "policy_input": policy},
        }
    return {
        "code": "needs_policy_input",
        "label": "정책 전제 입력 필요",
        "blocking": True,
        "reason": "산식은 구성되었지만 사업 규모나 운영방식에 대한 정책 전제가 필요합니다.",
        "missing": {"policy_input": policy},
    }
