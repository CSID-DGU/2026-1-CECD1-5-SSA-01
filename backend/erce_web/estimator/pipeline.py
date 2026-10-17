"""범용 비용추계 파이프라인 — 감지 → 스펙 → 변수해결 → 계산 → 테이블.

채널·표준산식 없음. LLM 의미 기반 감지/판정, DB/원문/외부에서 변수값,
결정적 계산. 이 버전은 원문 명시값만 채우고 선례/외부는 pending으로 두어
"어느 단계·어느 항목에서 막히는지"를 그대로 드러낸다(환각 방지).
"""
from __future__ import annotations

from typing import Any

from ..analyzer_v2 import (
    _extract_bill_name,
    _extract_current_bill_no,
    _extract_pdf_text_from_bytes,
    split_articles,
    strip_appendices,
)
from . import tag_db
from .detect import detect_cost_items
from .resolve import replication_factor, resolve_by_db_key
from .spec import build_item_spec
from .types import (
    CostItem,
    EstimateTable,
    Operation,
    ResolvedVariable,
    RowStatus,
    VariableStatus,
)

_OP_MAP = {
    "product": Operation.PRODUCT,
    "sum": Operation.SUM,
    "sum_of_products": Operation.SUM_OF_PRODUCTS,
}
_SRC_MAP = {
    "document": VariableStatus.DOCUMENT,
    "precedent": VariableStatus.PRECEDENT,
    "external": VariableStatus.EXTERNAL_PENDING,
}


def _articles_for(item: dict[str, Any], articles: list[dict[str, Any]]) -> str:
    refs = set(item.get("article_refs") or [])
    picked = [
        f"{a.get('no','')} {a.get('text','')}"
        for a in articles
        if any(r in str(a.get("no") or "") for r in refs)
    ]
    if not picked:  # 참조 매칭 실패 시 전체 일부
        picked = [f"{a.get('no','')} {a.get('text','')}" for a in articles[:6]]
    return "\n".join(picked)


_VALID_ROLES = {"count", "unit_price", "amount", "rate"}
# family별 추계 방법(일반 원칙):
#  - 분해형: 변수 구조(개수×단가)로 계산
#  - 준용금지: 대상 모집단이 사업마다 달라 총액준용이 무의미 → 외부데이터/HITL
#  - 나머지(research·facility·other): 총액 준용(용역·시설 총액은 비교 가능)
_DECOMPOSE_FAMILIES = {"committee", "personnel"}
_NO_ANALOGY_FAMILIES = {"subsidy"}
# recurrence를 LLM(변동) 대신 family로 결정적 판단: 용역·계획·구축은 일회성, 나머지 연간.
_ONE_TIME_FAMILIES = {"research", "facility"}


def _resolve_variable(v: dict[str, Any], item_query: str, exclude_bill_nos: set[str]) -> ResolvedVariable:
    status = _SRC_MAP.get(str(v.get("source")), VariableStatus.EXTERNAL_PENDING)
    name = str(v.get("name"))
    unit = str(v.get("unit") or "")
    role = str(v.get("role") or "count")
    if role not in _VALID_ROLES:
        role = "count"
    rv: ResolvedVariable | None = None
    # 1) 원문 명시값 우선
    if status == VariableStatus.DOCUMENT and v.get("document_value") is not None:
        try:
            rv = ResolvedVariable(name, float(v["document_value"]), unit,
                                  VariableStatus.DOCUMENT, basis="조문 명시값")
        except (TypeError, ValueError):
            rv = None
    # 2) 선례값: 원본 TAG를 1차로 사용(항목 이름으로 유사 선례 검색 → 대표값)
    if rv is None and status == VariableStatus.PRECEDENT:
        if role == "amount":
            got = tag_db.representative_annual_amount(item_query)
            if got:
                # 연간 금액(천원) → 원 단위 value로 저장(계산부가 /1000 하므로 *1000)
                rv = ResolvedVariable(name, float(got[0]) * 1000, unit or "천원",
                                      VariableStatus.PRECEDENT,
                                      basis=f"원본 TAG 유사 {got[1]}건 연간금액 중앙값 준용", source_ref="tag_amount")
        else:
            got = tag_db.representative_variable(item_query, role)
            if got:
                rv = ResolvedVariable(name, float(got[0]), unit, VariableStatus.PRECEDENT,
                                      basis=f"원본 TAG 유사 {got[1]}건 {role} 중앙값", source_ref=f"tag_{role}")
        # 2-b) 원본에서 못 찾으면 12키 파생 풀 fallback
        if rv is None:
            db_key = str(v.get("db_key") or "").strip()
            if db_key:
                rv = resolve_by_db_key(name, unit, db_key, exclude_bill_nos=exclude_bill_nos)
    # 3) 외부데이터/HITL
    if rv is None:
        rv = ResolvedVariable(name, None, unit, VariableStatus.EXTERNAL_PENDING,
                              basis="외부데이터 또는 사용자 확인 필요")
    rv.role = role
    return rv


def _compute_row(item: CostItem, years: int) -> None:
    """역할 기반 정합 계산: (개수들의 곱) × (단가 또는 총액 1개) × (비율 인자들).

    단가/총액 성격 변수가 2개 이상이면 산식이 불명확한 것 → 임의로 고르지 않고
    review로 표시. 이렇게 하면 단위 폭발이 '구조적으로' 불가능하다
    (임의 상한·pick-smallest 같은 끼워맞추기 불필요).
    """
    if not item.variables or not all(v.is_filled for v in item.variables):
        item.status = (RowStatus.NEEDS_EXTERNAL
                       if any(v.status == VariableStatus.EXTERNAL_PENDING for v in item.variables)
                       else RowStatus.BLOCKED)
        item.year_amounts_thousand = [None] * years
        return

    counts = [v for v in item.variables if v.role == "count"]
    prices = [v for v in item.variables if v.role in ("unit_price", "amount")]
    rates = [v for v in item.variables if v.role == "rate"]

    # 단가/총액이 2개 이상 → 정합성 불명확. 임의 선택 대신 검토로 넘긴다.
    if len(prices) >= 2:
        item.status = RowStatus.REVIEW_REQUIRED
        item.year_amounts_thousand = [None] * years
        item.evidence.append({
            "formula_ambiguous": f"단가/총액 성격 변수 {len(prices)}개({[p.name for p in prices]}) — 산식 정합성 확인 필요"
        })
        return

    base = 1.0
    for v in counts:
        base *= float(v.value)
    if prices:
        base *= float(prices[0].value)
    elif not counts:
        base = 0.0  # 개수도 단가도 없으면 계산 불가
    # 비율: 백분율(>2)로 들어오면 소수로 환산 후 곱
    for v in rates:
        r = float(v.value)
        if r > 2:
            r /= 100.0
        base *= r

    annual_thousand = int(round(base / 1000)) * item.replication.factor
    item.year_amounts_thousand = (
        [annual_thousand] + [0] * (years - 1) if item.recurrence == "one_time"
        else [annual_thousand] * years
    )
    item.status = (RowStatus.REVIEW_REQUIRED
                   if (item.replication.factor > 1
                       or any(v.status == VariableStatus.PRECEDENT for v in item.variables))
                   else RowStatus.COMPUTED)


def estimate_from_pdf(pdf_bytes: bytes, filename: str = "", years: int = 5) -> EstimateTable:
    raw = _extract_pdf_text_from_bytes(pdf_bytes)
    text = strip_appendices(raw) if raw else ""
    articles, doc_type = split_articles(text)
    bill_name = _extract_bill_name(text, filename)
    bill_no = _extract_current_bill_no(raw, filename)

    table = EstimateTable(bill_no=bill_no, bill_name=bill_name, doc_type=doc_type, years=years,
                          holdout_excluded={bill_no} if bill_no else set())

    detected = detect_cost_items(articles)
    for d in detected:
        art_text = _articles_for(d, articles)
        spec = build_item_spec(d, art_text)
        item = CostItem(
            name=d["name"],
            article_refs=d.get("article_refs") or [],
            cost_understanding=d.get("cost_understanding") or "",
            operation=_OP_MAP.get(spec.get("operation"), Operation.PRODUCT),
            recurrence=spec.get("recurrence") or "annual",
            evidence=[{"cost_kind": d.get("cost_kind"), "spec_reason": spec.get("reason")}],
        )
        if not spec.get("estimable"):
            item.status = RowStatus.BLOCKED
            item.year_amounts_thousand = [None] * years
            item.evidence.append({"non_estimable": spec.get("reason")})
            table.items.append(item)
            continue

        # 산식·금액은 TAG에서 결정적으로 가져온다(LLM이 매번 새로 구성하지 않음 → 안정).
        item.replication = replication_factor(art_text, d["name"])
        item_query = f"{d['name']} {d.get('cost_kind') or ''}"
        family = tag_db._family(item_query)
        # recurrence는 family로 결정적 판단(LLM 변동 제거)
        item.recurrence = "one_time" if family in _ONE_TIME_FAMILIES else "annual"
        hold = dict(family=family, exclude_bill_nos=table.holdout_excluded, exclude_bill_name=table.bill_name)

        # 지원금 등은 대상 모집단이 사업마다 달라 준용 불가 → 외부데이터로.
        if family in _NO_ANALOGY_FAMILIES:
            item.status = RowStatus.NEEDS_EXTERNAL
            item.year_amounts_thousand = [None] * years
            item.evidence.append({"needs_population": "지원 대상 규모·단가는 사업별 외부데이터 필요(총액준용 불가)"})
            table.items.append(item)
            continue

        # 분해형 유형(회의수당·인건비)은 변수 구조로, 총액형(용역·시설)은 총액 준용으로.
        # (family→방법은 "어떤 비용이 분해되나"라는 일반 프레임 설정; 유형별 값 하드코딩 아님)
        result, method = None, ""
        if family in _DECOMPOSE_FAMILIES:
            result = tag_db.estimate_structural(item_query, **hold)
            method = "구조계산"
        if result is None:
            result = tag_db.estimate_by_analogy(item_query, **hold)
            method = "총액준용"
        if result is None:
            item.status = RowStatus.NEEDS_EXTERNAL
            item.year_amounts_thousand = [None] * years
            item.evidence.append({"no_tag_analogy": "유사 TAG 선례 없음 → 외부데이터/사용자 확인 필요"})
            table.items.append(item)
            continue

        annual = result["annual_thousand"] * item.replication.factor
        item.formula = result.get("formula") or result.get("anchor_formula") or ""
        item.year_amounts_thousand = (
            [annual] + [0] * (years - 1) if item.recurrence == "one_time"
            else [annual] * years
        )
        item.status = RowStatus.REVIEW_REQUIRED
        item.evidence.append({
            "tag_method": f"{family}/{method}, 유사 {result['n']}건 준용",
            "tag_formula": item.formula[:60],
        })
        table.items.append(item)
    return table
