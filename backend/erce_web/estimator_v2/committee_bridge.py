"""위원회 항목을 v5(정규식, 안전) 산식으로 강제 대체 (격리 모듈, additive).

오늘 실측한 결론: v2(LLM)는 위원회류 사건에서 확신도(0.90)와 무관하게 틀린
선례를 골라 큰 오차(+227%)를 내거나, 같은 의안을 다시 불러도 사건 자체를
놓치는 비결정성을 보인다. 반면 committee_estimator_v5(정규식 기반)는 숫자를
절대 확정하지 않고 산식 구조·근거 딸린 초안·명시적 확인 항목만 제시해
안전하다.

이 모듈은 v2 파이프라인 결과에서 event_type == committee_operation인 행을
찾아, **v2가 뭘 계산했든 상관없이** v5의 산식 계획으로 강제 교체한다:
 - status는 항상 NEEDS_USER_INPUT (숫자를 확정하지 않음)
 - formula는 v5의 formula_plan.formula
 - reason에는 v5의 review_fields(무엇을 확인해야 하는지)를 요약

위원회가 아닌 행(인건비 등 organization_change)은 손대지 않는다.
"""
from __future__ import annotations

import re

from .types import RowStatus

COMMITTEE_BRIDGE_VERSION = "committee-bridge-v5-override-v1"


def _key(value: str) -> str:
    return re.sub(r"[ㆍ·・\s]+", "", value or "")


def _match_v5(event_object: str, v5_estimates: list) -> object | None:
    target = _key(event_object)
    matches = [
        estimate
        for estimate in v5_estimates
        if target
        and _key(estimate.committee_name)
        and (
            target in _key(estimate.committee_name)
            or _key(estimate.committee_name) in target
        )
    ]
    if not matches:
        return None
    return max(matches, key=lambda estimate: len(_key(estimate.committee_name)))


def apply_committee_v5_override(
    result,
    pdf_bytes: bytes,
    *,
    filename: str = "uploaded.pdf",
    years: int = 5,
) -> dict:
    """반환: {"overridden": int, "v5_only": int, "v2_only": int}"""
    from ..committee_estimator_v5 import estimate_committee_from_pdf_v5

    try:
        v5_result = estimate_committee_from_pdf_v5(
            pdf_bytes, filename=filename, years=years
        )
    except Exception as exc:  # noqa: BLE001
        return {"overridden": 0, "v5_only": 0, "v2_only": 0, "error": str(exc)}

    matched_v5_names: set[str] = set()
    overridden = 0
    for row in result.rows:
        if row.event is None or row.event.event_type != "committee_operation":
            continue
        estimate = _match_v5(row.event.object, v5_result.estimates)
        if estimate is None:
            continue
        matched_v5_names.add(estimate.committee_name)
        overridden += 1
        plan = estimate.formula_plan
        review_summary = "; ".join(
            f"{field['label']}({field['reason']})" for field in estimate.review_fields
        ) or "확인 필요 변수 없음"
        row.status = RowStatus.NEEDS_USER_INPUT
        row.reason_codes = [*row.reason_codes, "COMMITTEE_V5_OVERRIDE"]
        row.reason = (
            f"위원회 항목은 안전한 규칙기반 산식(v5)으로 대체했습니다. "
            f"산식: {plan.formula}. 확인 필요: {review_summary}"
        )
        row.formula = plan.formula
        row.year_amounts_thousand = [0] * len(row.year_amounts_thousand)
        row.selection_confidence = 0.0
        row.selection_method = COMMITTEE_BRIDGE_VERSION

    v2_committee_objects = {
        row.event.object
        for row in result.rows
        if row.event is not None and row.event.event_type == "committee_operation"
    }
    v5_only = sum(
        1
        for estimate in v5_result.estimates
        if estimate.committee_name not in matched_v5_names
    )
    v2_only = sum(
        1
        for obj in v2_committee_objects
        if _match_v5(obj, v5_result.estimates) is None
    )
    return {"overridden": overridden, "v5_only": v5_only, "v2_only": v2_only}
