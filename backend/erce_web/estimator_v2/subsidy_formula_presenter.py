"""지원금 항목이 값 없어 막혀도 산식만큼은 보여준다 (격리 모듈, additive).

실측(2126650): DB에 이름·구조까지 정답지와 일치하는 선례(2216470, 유사도
0.606)가 있었지만, 그 선례의 변수 값이 추출 단계에서 비어있어(None)
선택이 "완결 선례 없음"으로 실패했다. 이때 시스템은 그 정확한 산식조차
보여주지 않고 그냥 막혔다.

추가 실측: row.selected_candidates(재랭킹을 거친 후보)만 보면 원본 검색의
최상위 후보(2216470)가 이미 빠져있었다 — 재랭킹 단계가 값이 빈 후보를
더 세게 걸러낸 것으로 보인다. 그래서 이 모듈은 표시 직전에 원본
search_cost_candidates를 다시 호출해(임베딩 캐시 재사용, 추가 LLM 호출
없음) raw 유사도 최상위 중 산식이 있는 후보를 우선한다.

status는 바꾸지 않는다(여전히 사람 확인 필요, 숫자를 확정하지 않음 —
오늘의 원칙 그대로).
"""
from __future__ import annotations

from .retrieval import search_cost_candidates
from .types import EventType, RowStatus

SUBSIDY_FORMULA_PRESENTER_VERSION = "subsidy-formula-presenter-v2"


def _is_blocked_subsidy_row_with_candidates(row) -> bool:
    return (
        row.status == RowStatus.NEEDS_USER_INPUT
        and row.event is not None
        and row.event.event_type == EventType.SUBSIDY.value
        and not row.formula
        and bool(row.selected_candidates)
    )


def _best_candidate_with_formula(row, *, exclude_bill_nos, cutoff_date):
    raw_candidates, _ = search_cost_candidates(
        row.event,
        exclude_bill_nos=exclude_bill_nos,
        exclude_bill_name="",
        cutoff_date=cutoff_date,
        k=15,
    )
    pool = {c.item_id: c for c in [*raw_candidates, *row.selected_candidates]}
    with_formula = [c for c in pool.values() if c.formula]
    if not with_formula:
        return None
    return max(with_formula, key=lambda c: c.similarity)


def present_subsidy_formula(
    result, *, exclude_bill_nos: set[str] | None = None, cutoff_date: str | None = None
) -> int:
    """산식은 있으나 값이 빈 최유사 선례를 찾아 산식·확인필요 값을 표시.

    반환: 표시를 채운 행 수.
    """
    presented = 0
    for row in result.rows:
        if not _is_blocked_subsidy_row_with_candidates(row):
            continue
        top = _best_candidate_with_formula(
            row, exclude_bill_nos=exclude_bill_nos or set(), cutoff_date=cutoff_date
        )
        if top is None:
            continue
        missing = [
            v for v in top.variables if v.get("value") is None and v.get("name")
        ]
        if not missing:
            continue
        missing_desc = "; ".join(
            f"{v['name']}({v.get('source_text', '')[:60]})" for v in missing
        )
        row.formula = top.formula
        row.reason_codes = [*row.reason_codes, "SUBSIDY_FORMULA_PRESENTED"]
        row.reason = (
            f"{row.reason} [최유사 선례({top.bill_no} {top.item_name}, "
            f"유사도 {top.similarity:.2f})의 산식은 확인됐으나 값이 비어있습니다. "
            f"확인 필요: {missing_desc}]"
        )
        presented += 1
    return presented
