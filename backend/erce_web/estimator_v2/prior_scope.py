"""Use earlier same-law estimates as an estimability boundary.

Item-level TAG retrieval answers "how much did a similar cost item cost?".
It does not answer the prior question "did NABO consider this statutory event
estimable at all?".  A near-identical earlier bill is the strongest available
evidence for that boundary.

This module only uses documents proposed before the target bill.  It never
reads the target bill's official answer.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from ..analyzer_v2 import GEMINI_MODEL, gemini_json
from ..estimator import tag_db
from .cache import get_or_create_json
from .organization import _cost_estimate_contexts
from .retrieval import _normalise_law_name
from .types import AtomicEvent


PRIOR_SCOPE_VERSION = "same-law-prior-scope-v1"
_PARTIAL_PATTERN = re.compile(r"일부\s*추계|추계가\s*곤란|추계\s*곤란")
_LIMITATION_PATTERN = re.compile(
    r"일부\s*추계|추계가\s*곤란|추계\s*곤란|추계\s*대상에서\s*제외|"
    r"기존\s*예산|기본경비|흡수\s*가능|"
    r"추가\s*재정\s*소요.{0,40}(?:발생하지|없)|"
    r"별도.{0,30}(?:비용|재정\s*소요).{0,30}(?:발생하지|없)",
    re.DOTALL,
)
_EVENT_FAMILY = {
    "committee_operation": "committee",
    "research_plan": "research",
    "personnel": "personnel",
    "subsidy": "subsidy",
    "facility_system": "facility",
    "tax_revenue": "tax",
}


@dataclass(frozen=True)
class PriorScopeDecision:
    event_id: str
    status: str
    prior_bill_no: str
    prior_bill_name: str
    matched_quote: str
    limitation_quote: str
    reason: str


_PROMPT = """당신은 비용추계의 '추계 가능 범위'를 판정하는 검증자다.
대상 법안보다 먼저 제안된 같은 법률의 공식 비용추계서와 대상 비용사건을 비교한다.

각 대상 사건을 다음 중 하나로 분류한다.
- priced: 과거 공식 추계서가 실질적으로 같은 비용사건을 금액 항목으로 계산했다.
- unestimable: 과거 공식 추계서가 실질적으로 같은 비용사건을 재정수반요인으로
  다뤘지만 추계 곤란/일부추계 범위 밖으로 남겼다.
- unknown: 위 두 가지를 근거 문장으로 입증할 수 없다.

엄격한 기준:
- 법률명이 같다는 사실만으로 unestimable이라 하지 마라.
- unestimable은 과거 문서 안에서 같은 행위·대상을 확인할 matched_quote와,
  일부추계 또는 추계 곤란을 확인할 limitation_quote가 모두 있어야 한다.
- priced는 priced_items에 같은 비용사건이 실제로 있어야 한다.
- 문서에 없는 문장을 만들지 말고 두 quote는 원문 그대로 복사한다.
- 애매하면 unknown이다.

JSON만 반환:
{"decisions":[{"event_id":"E001","status":"priced|unestimable|unknown",
"matched_quote":"과거 문서의 같은 사건 문장 또는 빈 문자열",
"limitation_quote":"추계 범위 제한 문장 또는 빈 문자열",
"reason":"판정 이유"}]}

입력:
"""


def _compact(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value or "")


def _metadata_by_bill() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for item in tag_db._load()["items"].values():
        bill_no = str(item.get("bill_no") or "")
        if not bill_no:
            continue
        row = result.setdefault(
            bill_no,
            {
                "bill_no": bill_no,
                "bill_name": str(item.get("bill_name") or ""),
                "propose_date": str(item.get("propose_date") or ""),
                "priced_items": [],
            },
        )
        if not row["bill_name"] and item.get("bill_name"):
            row["bill_name"] = str(item["bill_name"])
        if not row["propose_date"] and item.get("propose_date"):
            row["propose_date"] = str(item["propose_date"])
        row["priced_items"].append(
            {
                "name": str(item.get("name") or ""),
                "family": str(item.get("family") or ""),
            }
        )
    return result


def _latest_same_law_prior(
    *,
    target_bill_no: str,
    target_bill_name: str,
    cutoff_date: str | None,
) -> tuple[dict[str, object], str] | None:
    if not cutoff_date:
        return None
    law = _normalise_law_name(target_bill_name)
    if not law:
        return None
    contexts = _cost_estimate_contexts()
    candidates: list[tuple[str, str, dict[str, object], str]] = []
    for bill_no, meta in _metadata_by_bill().items():
        propose_date = str(meta.get("propose_date") or "")
        bill_name = str(meta.get("bill_name") or "")
        context = contexts.get(bill_no, "")
        if (
            bill_no == target_bill_no
            or not propose_date
            or propose_date >= cutoff_date
            or _normalise_law_name(bill_name) != law
            or not context
            or not _PARTIAL_PATTERN.search(context)
        ):
            continue
        candidates.append((propose_date, bill_no, meta, context))
    if not candidates:
        return None
    _, _, meta, context = max(candidates, key=lambda value: (value[0], value[1]))
    return meta, context


def assess_prior_scope(
    events: list[AtomicEvent],
    *,
    target_bill_no: str,
    target_bill_name: str,
    cutoff_date: str | None,
    refresh: bool = False,
) -> tuple[dict[str, PriorScopeDecision], str | None]:
    """Return evidence-grounded scope decisions from the latest prior twin."""
    prior = _latest_same_law_prior(
        target_bill_no=target_bill_no,
        target_bill_name=target_bill_name,
        cutoff_date=cutoff_date,
    )
    relevant_events = [
        event for event in events if event.event_type in _EVENT_FAMILY
    ]
    if prior is None or not relevant_events:
        return {}, None
    meta, context = prior
    payload = {
        "version": PRIOR_SCOPE_VERSION,
        "model": GEMINI_MODEL,
        "target_bill_no": target_bill_no,
        "target_bill_name": target_bill_name,
        "cutoff_date": cutoff_date,
        "events": [asdict(event) for event in relevant_events],
        "prior_bill": meta,
        "prior_context": context,
    }
    response, _ = get_or_create_json(
        "prior_scope",
        payload,
        lambda: gemini_json(_PROMPT + str(payload), temperature=0.0),
        refresh=refresh,
    )
    response = response if isinstance(response, dict) else {}
    rows = response.get("decisions")
    if not isinstance(rows, list):
        return {}, f"과거 동일 법률 선례 {meta['bill_no']}의 추계 범위 판정에 실패했습니다."

    event_by_id = {event.id: event for event in relevant_events}
    priced_families = {
        str(item.get("family") or "")
        for item in meta.get("priced_items") or []
        if isinstance(item, dict)
    }
    compact_context = _compact(context)
    decisions: dict[str, PriorScopeDecision] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        event_id = str(row.get("event_id") or "")
        event = event_by_id.get(event_id)
        if event is None:
            continue
        status = str(row.get("status") or "unknown")
        if status not in {"priced", "unestimable", "unknown"}:
            status = "unknown"
        matched_quote = str(row.get("matched_quote") or "").strip()
        limitation_quote = str(row.get("limitation_quote") or "").strip()
        matched_grounded = bool(matched_quote) and _compact(matched_quote) in compact_context
        limitation_grounded = (
            bool(limitation_quote)
            and _compact(limitation_quote) in compact_context
            and bool(_LIMITATION_PATTERN.search(limitation_quote))
        )
        family = _EVENT_FAMILY[event.event_type]
        if status == "priced" and family not in priced_families:
            status = "unknown"
        if status == "unestimable" and (
            family in priced_families
            or not matched_grounded
            or not limitation_grounded
        ):
            status = "unknown"
        decisions[event_id] = PriorScopeDecision(
            event_id=event_id,
            status=status,
            prior_bill_no=str(meta.get("bill_no") or ""),
            prior_bill_name=str(meta.get("bill_name") or ""),
            matched_quote=matched_quote if matched_grounded else "",
            limitation_quote=limitation_quote if limitation_grounded else "",
            reason=str(row.get("reason") or ""),
        )
    return decisions, None
