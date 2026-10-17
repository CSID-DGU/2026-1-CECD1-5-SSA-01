"""Evaluate v5 on the five-bill development batch.

The predictions were generated after the v4.1 holdout exposed the failures,
so this is a regression/development result, not an unseen generalization score.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re


PREDICTIONS = Path(
    "backend/generated/committee_v4_holdout5/results/v5_0_dev_predictions.json"
)


@dataclass(frozen=True)
class ExpectedUnit:
    bill_no: str
    name: str
    family: str
    component_kinds: tuple[str, ...]


UNITS = (
    ExpectedUnit(
        "2216367", "중소기업기술분쟁조정ㆍ중재위원회",
        "committee_support_operation",
        ("main_meeting_allowance", "support_staff_compensation", "support_operating_expense"),
    ),
    ExpectedUnit(
        "2212322", "지역별사업재편지원협의회",
        "multi_instance_meeting_allowance", ("main_meeting_allowance",),
    ),
    ExpectedUnit(
        "2215078", "중앙화재조사심의위원회",
        "meeting_allowance", ("main_meeting_allowance",),
    ),
    ExpectedUnit(
        "2215078", "시ㆍ도화재조사심의위원회",
        "multi_instance_meeting_allowance", ("main_meeting_allowance",),
    ),
    ExpectedUnit(
        "2215198", "국가미래위원회",
        "compound_committee_allowance",
        ("main_meeting_allowance", "subordinate_meeting_allowance"),
    ),
    ExpectedUnit(
        "2211944", "규제합리화위원회",
        "multi_activity_meeting_allowance", ("activity_allowance_bundle",),
    ),
)


def _key(value: str) -> str:
    return re.sub(r"[ㆍ·・\s]+", "", value or "")


def _match(expected: str, actual: str) -> bool:
    expected = _key(expected)
    actual = _key(actual)
    return bool(expected and actual and (expected in actual or actual in expected))


def main() -> None:
    predictions = json.loads(PREDICTIONS.read_text(encoding="utf-8"))
    rows = []
    for unit in UNITS:
        estimate = next(
            (
                value
                for value in predictions[unit.bill_no]["estimates"]
                if _match(unit.name, value["committee_name"])
            ),
            None,
        )
        if estimate is None:
            rows.append({
                **asdict(unit),
                "detected": False,
                "family_match": False,
                "component_match": False,
            })
            continue
        plan = estimate["formula_plan"]
        actual_components = tuple(value["kind"] for value in plan["components"])
        rows.append({
            **asdict(unit),
            "detected": True,
            "detected_name": estimate["committee_name"],
            "detected_family": plan["family"],
            "detected_components": actual_components,
            "family_match": plan["family"] == unit.family,
            "component_match": actual_components == unit.component_kinds,
            "decision": estimate["decision"],
            "numeric_draft_million": (
                estimate["five_year_amount_thousand"] / 1000
                if estimate["five_year_amount_thousand"] is not None
                else None
            ),
            "target_leak": estimate.get("selected_precedent_bill") == unit.bill_no,
        })
    payload = {
        "evaluation_type": "v5_five_bill_development_regression",
        "bill_count": len(predictions),
        "official_formula_unit_count": len(UNITS),
        "detected_count": sum(bool(value["detected"]) for value in rows),
        "family_match_count": sum(bool(value["family_match"]) for value in rows),
        "component_match_count": sum(bool(value["component_match"]) for value in rows),
        "numeric_draft_count": sum(
            value.get("numeric_draft_million") is not None for value in rows
        ),
        "target_leak_count": sum(bool(value.get("target_leak")) for value in rows),
        "rows": rows,
    }
    output = PREDICTIONS.with_name("v5_0_dev_evaluation.json")
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
