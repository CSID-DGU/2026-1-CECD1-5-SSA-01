"""Evaluate frozen v4.1 predictions on five additional committee bills.

Protocol:
1. Predictions were generated from bill PDFs and frozen separately.
2. This evaluator only reads that frozen JSON; it never runs the estimator.
3. Official labels below were transcribed after the prediction file was frozen.

The bills were not part of the v4 development/audit sets.  They did already
exist in the local retrieval corpus, so this is an internal holdout with target
bill exclusion, not a fully external prospective holdout.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re


ROOT = Path("backend/generated/committee_v4_holdout5")
PREDICTIONS = ROOT / "results" / "v4_1_frozen_predictions.json"


@dataclass(frozen=True)
class OfficialFormulaUnit:
    bill_no: str
    name: str
    family: str
    official_million: float
    required_formula_terms: tuple[str, ...]
    official_formula: str
    external_evidence_required: bool


UNITS = (
    OfficialFormulaUnit(
        "2216367",
        "중소기업기술분쟁조정ㆍ중재위원회",
        "committee_support_operation",
        1_400,
        ("순증", "회의 횟수", "수당", "지원조직 인건비", "운영비"),
        "민간위원 순증×회의횟수×수당+전문위원 2인 인건비+사무국 운영비",
        True,
    ),
    OfficialFormulaUnit(
        "2212322",
        "지역별 사업재편지원협의회",
        "multi_instance_meeting_allowance",
        3_468,
        ("설치기관 수", "유급위원", "회의 횟수", "수당"),
        "17개 시도×위촉직 17명×연 6회×40만원",
        True,
    ),
    OfficialFormulaUnit(
        "2215078",
        "중앙화재조사심의위원회",
        "meeting_allowance",
        25,
        ("유급위원", "회의 횟수", "수당"),
        "민간위원 10명×연 2회×25만원",
        True,
    ),
    OfficialFormulaUnit(
        "2215078",
        "시ㆍ도화재조사심의위원회",
        "multi_instance_meeting_allowance",
        475,
        ("설치기관 수", "유급위원", "회의 횟수", "수당"),
        "19개 시도소방본부×민간위원 10명×연 2회×25만원",
        True,
    ),
    OfficialFormulaUnit(
        "2215198",
        "국가미래위원회",
        "compound_committee_allowance",
        1_440,
        ("본위원회", "하위기구", "회의 횟수", "수당"),
        "전체회의 20명×연 24회×30만원+4개 분과×5명×연 24회×30만원",
        True,
    ),
    OfficialFormulaUnit(
        "2211944",
        "규제합리화위원회",
        "multi_activity_meeting_allowance",
        1_940,
        ("순증", "전체회의", "분과위원회", "예비심사", "수당"),
        "민간위원 순증 16명×(전체 20회×33만원+분과 33회×33만원+예비심사 52회×13만원)",
        True,
    ),
)


def _key(value: str) -> str:
    return re.sub(r"[ㆍ·・\s]+", "", value or "")


def _matches(expected: str, actual: str) -> bool:
    left = _key(expected)
    right = _key(actual)
    return bool(left and right and (left in right or right in left))


def main() -> None:
    predictions = json.loads(PREDICTIONS.read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    matched_actual: set[tuple[str, int]] = set()

    for unit in UNITS:
        result = predictions.get(unit.bill_no, {})
        matched = None
        matched_index = None
        for index, estimate in enumerate(result.get("estimates", [])):
            if _matches(unit.name, estimate.get("committee_name", "")):
                matched = estimate
                matched_index = index
                break
        if matched is None:
            rows.append({
                **asdict(unit),
                "detected": False,
                "family_match": False,
                "strict_formula_match": False,
                "decision": None,
                "numeric_draft_million": None,
                "target_leak": False,
            })
            continue

        matched_actual.add((unit.bill_no, int(matched_index)))
        plan = matched["formula_plan"]
        formula = _key(plan["formula"])
        family_match = plan["family"] == unit.family
        strict = family_match and all(
            _key(term) in formula for term in unit.required_formula_terms
        )
        selected = matched.get("selected_candidate") or {}
        five_year = matched.get("five_year_amount_thousand")
        rows.append({
            **asdict(unit),
            "detected": True,
            "detected_name": matched["committee_name"],
            "detected_family": plan["family"],
            "detected_formula": plan["formula"],
            "family_match": family_match,
            "strict_formula_match": strict,
            "decision": matched["decision"],
            "numeric_draft_million": (
                five_year / 1_000 if five_year is not None else None
            ),
            "selected_precedent_bill": selected.get("bill_no"),
            "target_leak": selected.get("bill_no") == unit.bill_no,
        })

    false_events = []
    for bill_no, result in predictions.items():
        for index, estimate in enumerate(result.get("estimates", [])):
            if (bill_no, index) not in matched_actual:
                false_events.append({
                    "bill_no": bill_no,
                    "name": estimate["committee_name"],
                    "family": estimate["formula_plan"]["family"],
                })

    detected = [row for row in rows if row["detected"]]
    numeric = [row for row in rows if row["numeric_draft_million"] is not None]
    payload = {
        "evaluation_type": "v4_1_additional_five_bill_internal_holdout",
        "prediction_file": str(PREDICTIONS),
        "bill_count": len(predictions),
        "official_formula_unit_count": len(UNITS),
        "detected_count": len(detected),
        "detection_rate": round(len(detected) / len(UNITS), 3),
        "formula_family_match_count": sum(bool(row["family_match"]) for row in rows),
        "formula_family_accuracy": round(
            sum(bool(row["family_match"]) for row in rows) / len(UNITS), 3
        ),
        "strict_formula_match_count": sum(
            bool(row["strict_formula_match"]) for row in rows
        ),
        "strict_formula_accuracy": round(
            sum(bool(row["strict_formula_match"]) for row in rows) / len(UNITS), 3
        ),
        "numeric_draft_count": len(numeric),
        "numeric_coverage": round(len(numeric) / len(UNITS), 3),
        "detected_external_input_cases_routed_to_hitl": sum(
            bool(row["detected"])
            and bool(row["external_evidence_required"])
            and row["decision"] == "human_input_required"
            for row in rows
        ),
        "false_event_count": len(false_events),
        "target_leak_count": sum(bool(row["target_leak"]) for row in rows),
        "false_events": false_events,
        "rows": rows,
    }
    output = ROOT / "results" / "v4_1_holdout5_evaluation.json"
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
