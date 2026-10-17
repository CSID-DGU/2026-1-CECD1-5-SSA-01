"""제정안의 신규 연구용역 의무가 "현행유지 가능성"으로 오판되는 걸 교정.

실측(2213320): 제정안(브랜드뉴 법률)이 "기본계획을 수립한다"는 신규 조문을
만드는데도, detect.py가 additionality를 possibly_incremental로 판단해
RESEARCH_ADDITIONALITY_UNPROVEN 게이트에 막혔다. 이 항목은 이 사건이
차지하는 총액의 94%였는데, 산식 시도조차 못 했다.

제정안(대상 법률이 이번에 처음 만들어짐)에서 신설되는 계획 수립 의무는,
정의상 기존 예산으로 이미 수행 중일 수가 없다(그 법 자체가 존재하지
않았으므로). 이 게이트는 이 좁은 조건에서만 게이트를 우회해 정상적으로
search_cost_candidates 이후 선택 로직으로 흘러가게 한다. DB에는 이미
"기본계획 수립 유사 연구용역 준용" 선례가 다수 있다(실측 확인됨).

**"시행계획"은 제외한다**: 2213320·2217718 두 공식 문서 모두 "기본계획"만
계상하고 "시행계획"(기본계획에 따라 매년 수립하는 파생 계획)은 별도 비용을
계상하지 않았다. 첫 구현에서 시행계획까지 우회시켰다가 없어야 할 큰 금액을
만들어낸 부작용을 실측으로 확인했다.

LLM 프롬프트는 건드리지 않는다. doc_type이 "제정안"이 아니면 전혀 작동하지
않는다.
"""
from __future__ import annotations

import re
from dataclasses import replace

from .gates import GateDecision
from .types import AtomicEvent, EventType, RowStatus

RESEARCH_PLAN_OVERRIDE_VERSION = "research-plan-enactment-override-v2"

_DERIVED_IMPLEMENTATION_PLAN = re.compile(r"시행계획|추진계획|연차별계획")


def override_research_additionality_gate(
    event: AtomicEvent,
    decision: GateDecision,
    *,
    doc_type: str,
) -> GateDecision:
    if decision.automatic:
        return decision
    if event.event_type != EventType.RESEARCH_PLAN.value:
        return decision
    if "RESEARCH_ADDITIONALITY_UNPROVEN" not in decision.reason_codes:
        return decision
    if doc_type != "제정안":
        return decision
    compact_object = re.sub(r"\s+", "", event.object or "")
    if _DERIVED_IMPLEMENTATION_PLAN.search(compact_object):
        return decision
    return replace(
        decision,
        automatic=True,
        status=RowStatus.COMPUTED_REVIEW,
        reason=(
            f"{decision.reason} [제정안 신규 계획 수립 의무이므로 기존 예산 "
            "수행 가능성이 논리적으로 배제되어 자동 검색으로 전환합니다.]"
        ),
        reason_codes=[*decision.reason_codes, "ENACTMENT_RESEARCH_PLAN_OVERRIDE"],
    )
