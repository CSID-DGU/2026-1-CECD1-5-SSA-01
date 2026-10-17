"""선례 선택 사후 검증 (격리 모듈, additive).

v2는 위원회류 사건에서 선례를 하나 골라 확정(computed_review)하지만, 그 확신도
(confidence)는 LLM이 스스로 매긴 값이라 실제 정확도와 무관하게 항상 높게
나온다(2026년 confidence calibration 연구가 공통으로 지적하는 문제). 이 모듈은
그 선택을 LLM 바깥에서 다시 검증한다:

 1. 반박(adversarial) LLM 호출 — "이 선례가 왜 부적합한지 근거를 대라"고
    요청한다. 구체적 결격 사유(정책 도메인 불일치, 소관부처 불일치, 비용
    메커니즘 불일치 등)를 찾으면 반박 성공.
 2. 반박이 성공하면 → 확정을 취소하고 needs_user_input으로 되돌린다
    (금액은 0, 근거에 반박 사유를 남긴다).
 3. 반박이 실패하면 → 확정을 유지하되, confidence는 LLM 자기평가가 아니라
    "검증 통과"라는 사실 자체로 재설정한다.

**대상 한정**: event_type이 committee_operation인, 이미 selected_candidates가
있는 computed_review 행에만 적용한다. 다른 행은 손대지 않는다.
"""
from __future__ import annotations

from .types import RowStatus

ADVERSARIAL_VERIFY_VERSION = "adversarial-verify-v1"


def _build_prompt(row) -> str:
    event = row.event
    candidate = row.selected_candidates[0] if row.selected_candidates else None
    candidate_desc = (
        f"선례 의안: {candidate.bill_name} / 항목: {candidate.item_name}"
        if candidate
        else "(선례 정보 없음)"
    )
    return (
        "다음은 비용추계 시스템이 자동으로 선택한 '선례'다. 너는 이 선택을 "
        "반박하는 역할이다. 대상 사건과 선례가 정말 같은 성격의 비용인지 "
        "의심하고, 아래 기준으로 구체적 결격 사유를 찾아라:\n"
        "- 정책 도메인/소관부처가 실질적으로 다른가(예: 인권위 vs 환경정책)\n"
        "- 위원회의 설치 목적·기능이 근본적으로 다른가\n"
        "- 비용 발생 메커니즘(회의비 vs 인건비 vs 사업비)이 다른가\n"
        "막연한 의심이 아니라, 위 기준 중 하나라도 명백히 해당해야만 반박 성공이다.\n\n"
        f"[대상 사건] 주체: {event.actor} / 행위: {event.action} / "
        f"객체: {event.object}\n"
        f"[선택된 선례] {candidate_desc}\n\n"
        '다음 JSON으로만 답하라: {"refuted": true 또는 false, '
        '"reason": "한국어로 구체적 사유, 반박 실패시 왜 적합한지"}'
    )


def verify_precedent_selection(row) -> dict:
    from ..analyzer_v2 import _call_llm_raw_json

    prompt = _build_prompt(row)
    try:
        result = _call_llm_raw_json(prompt, temperature=0.0, timeout=60)
    except Exception as exc:  # noqa: BLE001
        return {"refuted": False, "reason": f"검증 호출 실패({exc}), 원 판단 유지"}
    if not isinstance(result, dict):
        return {"refuted": False, "reason": "검증 응답 파싱 실패, 원 판단 유지"}
    return {
        "refuted": bool(result.get("refuted")),
        "reason": str(result.get("reason") or ""),
    }


def _is_verifiable_committee_row(row) -> bool:
    return (
        row.status == RowStatus.COMPUTED_REVIEW
        and row.event is not None
        and row.event.event_type == "committee_operation"
        and bool(row.selected_candidates)
    )


def apply_adversarial_verification(result) -> dict:
    """검증 대상 행을 반박 시도하고, 반박 성공 시 확정을 취소한다.

    반환: {"checked": int, "refuted": int}
    """
    checked = 0
    refuted = 0
    for row in result.rows:
        if not _is_verifiable_committee_row(row):
            continue
        checked += 1
        verdict = verify_precedent_selection(row)
        if not verdict["refuted"]:
            row.reason_codes = [*row.reason_codes, "ADVERSARIAL_VERIFY_PASSED"]
            row.reason = f"{row.reason} [반박검증 통과: {verdict['reason']}]"
            continue
        refuted += 1
        original_candidate = (
            row.selected_candidates[0].bill_no if row.selected_candidates else "?"
        )
        row.status = RowStatus.NEEDS_USER_INPUT
        row.reason_codes = [*row.reason_codes, "ADVERSARIAL_VERIFY_REFUTED"]
        row.reason = (
            f"자동 선택된 선례({original_candidate})가 검증에서 기각되었습니다: "
            f"{verdict['reason']} 사람 확인이 필요합니다."
        )
        row.year_amounts_thousand = [0] * len(row.year_amounts_thousand)
        row.selection_confidence = 0.0
    return {"checked": checked, "refuted": refuted}
