from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

from .retrieval import MIN_PRICED_CASES
from .types import EventType, TagCandidate


def _robust_median(values: list[int]) -> int:
    if len(values) < 4:
        return int(statistics.median(values))
    ordered = sorted(values)
    q1 = ordered[len(ordered) // 4]
    q3 = ordered[(len(ordered) * 3) // 4]
    iqr = q3 - q1
    kept = [value for value in ordered if q1 - 1.5 * iqr <= value <= q3 + 1.5 * iqr]
    return int(statistics.median(kept or ordered))


def positive_amount(candidate: TagCandidate) -> int | None:
    values = [
        int(row["amount_thousand"])
        for row in candidate.amounts
        if row.get("amount_thousand") is not None and int(row["amount_thousand"]) > 0
    ]
    return int(statistics.median(values)) if values else None


def coherent_committee_case(candidate: TagCandidate) -> dict[str, Any] | None:
    values: dict[str, list[float]] = defaultdict(list)
    for variable in candidate.variables:
        variable_type = str(variable.get("type") or "")
        if variable_type not in {"target_count", "unit_cost", "frequency"}:
            continue
        try:
            value = float(variable.get("value"))
        except (TypeError, ValueError):
            continue
        if value > 0:
            values[variable_type].append(value)
    if not all(values.get(key) for key in ("target_count", "unit_cost", "frequency")):
        return None
    count = statistics.median(values["target_count"])
    unit_cost = statistics.median(values["unit_cost"])
    frequency = statistics.median(values["frequency"])
    calculated = int(round(count * unit_cost * frequency / 1000))
    observed = positive_amount(candidate)
    if not observed or not (0.5 <= calculated / observed <= 2.0):
        return None
    return {
        "amount_thousand": calculated,
        "count": count,
        "unit_cost_won": unit_cost,
        "frequency": frequency,
        "observed_thousand": observed,
    }


def estimate_selected_precedent(
    event_type: str,
    candidate: TagCandidate,
) -> tuple[int | None, str, list[dict[str, Any]]]:
    """Reuse one precedent as a coherent formula/value package."""
    if event_type == EventType.COMMITTEE.value:
        case = coherent_committee_case(candidate)
        if case:
            return (
                int(case["amount_thousand"]),
                candidate.formula or "민간위원 수 × 회의수당 × 연간 회의횟수",
                [
                    {
                        "name": "민간위원 수",
                        "value": case["count"],
                        "unit": "명",
                        "source": candidate.item_id,
                    },
                    {
                        "name": "회의 수당",
                        "value": case["unit_cost_won"],
                        "unit": "원/명·회",
                        "source": candidate.item_id,
                    },
                    {
                        "name": "연간 회의 횟수",
                        "value": case["frequency"],
                        "unit": "회/년",
                        "source": candidate.item_id,
                    },
                ],
            )
        amount = positive_amount(candidate)
        if amount is not None:
            return (
                amount,
                candidate.formula or "같은 기능의 위원회 연간 운영비 준용",
                [
                    {
                        "name": "선택 선례 연간 운영비",
                        "value": amount,
                        "unit": "천원",
                        "source": candidate.item_id,
                    }
                ],
            )
        return None, "", []
    if event_type == EventType.RESEARCH_PLAN.value:
        amount = positive_amount(candidate)
        if amount is None:
            return None, "", []
        return (
            amount,
            candidate.formula or "선택한 연구·계획수립 선례의 1회 용역비",
            [
                {
                    "name": "선택 선례 1회 용역비",
                    "value": amount,
                    "unit": "천원",
                    "source": candidate.item_id,
                }
            ],
        )
    return None, "", []


def estimate_event_amount(
    event_type: str,
    candidates: list[TagCandidate],
) -> tuple[int | None, str, list[dict[str, Any]], list[TagCandidate]]:
    """Estimate from coherent precedents; never mix variables across cases."""
    if event_type == EventType.COMMITTEE.value:
        cases: list[tuple[TagCandidate, dict[str, Any]]] = []
        for candidate in candidates:
            case = coherent_committee_case(candidate)
            if case:
                cases.append((candidate, case))
        if len(cases) < MIN_PRICED_CASES:
            return None, "", [], []
        representative = _robust_median([case["amount_thousand"] for _, case in cases])
        anchor, anchor_case = min(
            cases,
            key=lambda value: abs(value[1]["amount_thousand"] - representative),
        )
        evidence = [
            {
                "name": "민간위원 수",
                "value": anchor_case["count"],
                "unit": "명",
                "source": anchor.item_id,
            },
            {
                "name": "회의 수당",
                "value": anchor_case["unit_cost_won"],
                "unit": "원/명·회",
                "source": anchor.item_id,
            },
            {
                "name": "연간 회의 횟수",
                "value": anchor_case["frequency"],
                "unit": "회/년",
                "source": anchor.item_id,
            },
        ]
        return (
            representative,
            "완결된 선례별 (민간위원 수 × 회의수당 × 연간 회의횟수)의 강건 중앙값",
            evidence,
            [candidate for candidate, _ in cases],
        )

    if event_type == EventType.RESEARCH_PLAN.value:
        priced = [
            (candidate, amount)
            for candidate in candidates
            if (amount := positive_amount(candidate)) is not None
        ]
        if len(priced) < MIN_PRICED_CASES:
            return None, "", [], []
        representative = _robust_median([amount for _, amount in priced])
        anchor, amount = min(priced, key=lambda value: abs(value[1] - representative))
        return (
            representative,
            "동일 비용구조 연구·계획수립 선례의 1회 용역비 강건 중앙값",
            [
                {
                    "name": "대표 1회 용역비",
                    "value": amount,
                    "unit": "천원",
                    "source": anchor.item_id,
                }
            ],
            [candidate for candidate, _ in priced],
        )
    return None, "", [], []
