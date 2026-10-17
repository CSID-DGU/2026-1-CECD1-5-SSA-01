"""지원금(subsidy)을 자동계산 범위에 opt-in으로 포함시킨다 (격리 모듈, additive).

실측: gates.py의 _AUTO_TYPES = {COMMITTEE, RESEARCH_PLAN}에는 SUBSIDY가
아예 없어서, family 태그를 아무리 정확히 고쳐도(오늘 81건 고침) 지원금
사건은 검색 시도 자체를 못 했다(OUTSIDE_AUTO_SCOPE 게이트에서 즉시 차단).

이 모듈은 gates.py 자체를 바꾸지 않고, SUBSIDY이면서 OUTSIDE_AUTO_SCOPE로
막힌 사건만 opt-in으로 우회한다. 부담 주체가 공공(state/local)인지는 그대로
유지한다(민간 부담 사건까지 열지 않음).
"""
from __future__ import annotations

from dataclasses import replace

from .gates import GateDecision, _PUBLIC_BEARERS
from .types import AtomicEvent, EventType, RowStatus

SUBSIDY_AUTO_SCOPE_VERSION = "subsidy-auto-scope-v1"


def override_subsidy_auto_scope_gate(
    event: AtomicEvent,
    decision: GateDecision,
) -> GateDecision:
    if decision.automatic:
        return decision
    if event.event_type != EventType.SUBSIDY.value:
        return decision
    if "OUTSIDE_AUTO_SCOPE" not in decision.reason_codes:
        return decision
    if event.bearer not in _PUBLIC_BEARERS:
        return decision
    return replace(
        decision,
        automatic=True,
        status=RowStatus.COMPUTED_REVIEW,
        reason=(
            f"{decision.reason} [지원금 자동계산 범위 opt-in 확장으로 검색을 "
            "시도합니다.]"
        ),
        reason_codes=[*decision.reason_codes, "SUBSIDY_AUTO_SCOPE_OVERRIDE"],
    )
