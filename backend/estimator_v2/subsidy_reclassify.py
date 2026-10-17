"""개인 대상 급여성 지급이 조직변경으로 오분류되는 걸 사후 교정 (격리 모듈, additive).

실측(2126660 양육비 선지급): detect.py가 "제도를 신설한다"는 표현에 이끌려
개인에게 지급되는 급여성 사건(양육비 선지급)을 event_type=organization_change로
잘못 분류했다. 그 결과 검색이 조직/인력 DB만 뒤지고, DB에 실제로 존재하는
지원금 선례(아동수당 등, 유사도 0.49~0.55)는 아예 보지 못했다.

이 게이트는 LLM 프롬프트를 건드리지 않고, ORGANIZATION으로 분류된 사건 중
"개인에게 지급"을 가리키는 신호가 강하고 "조직 규모"를 가리키는 신호가 전혀
없는 경우에만 SUBSIDY로 재분류한다. 두 신호가 섞여 있으면(예: 조직을 만들며
그 조직이 급여도 지급) 건드리지 않아 오탐을 줄인다.
"""
from __future__ import annotations

import re
from dataclasses import replace

from .types import AtomicEvent, EventType

SUBSIDY_RECLASSIFY_VERSION = "subsidy-reclassify-v1"

_PAYMENT_TO_INDIVIDUAL = re.compile(
    r"채권자|수급자|신청인|피해자.{0,10}지급|대상자.{0,10}지급|"
    r"선지급|지급하여줄것을신청|지급할수있다|지급받을수있다|"
    r"수당을지급|급여를지급|지원금을지급|지원비를지급|생계비를지급"
)
_ORGANIZATION_SCALE = re.compile(
    r"정원|증원|인력.{0,10}(배치|채용|충원)|직원.{0,10}(채용|임명|배치)|"
    r"공무원.{0,10}(채용|임명|배치)|위원회를둔다|위원회를설치|"
    r"사무처|사무국|조직을(신설|설치)|기구를설치"
)


def _normalise(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def reclassify_subsidy_events(
    events: list[AtomicEvent],
) -> tuple[list[AtomicEvent], int]:
    """개인 대상 급여 지급 사건을 organization_change에서 subsidy로 재분류.

    반환: (교정된 사건 목록, 교정 건수)
    """
    reclassified = 0
    result: list[AtomicEvent] = []
    for event in events:
        if event.event_type != EventType.ORGANIZATION.value:
            result.append(event)
            continue
        text = _normalise(
            " ".join([event.object, event.action, event.explanation, *event.quotes])
        )
        if _PAYMENT_TO_INDIVIDUAL.search(text) and not _ORGANIZATION_SCALE.search(
            text
        ):
            event = replace(event, event_type=EventType.SUBSIDY.value)
            reclassified += 1
        result.append(event)
    return result, reclassified
