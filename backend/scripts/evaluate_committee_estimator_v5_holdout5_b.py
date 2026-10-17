"""Evaluate the frozen second five-bill v5 holdout.

The prediction file was written before the official estimate PDFs in the
answer directory were inspected.  Keep this evaluator independent from the
runtime engine so later changes cannot rewrite the baseline score.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import argparse
import json
from pathlib import Path
import re


PREDICTIONS = Path(
    "backend/generated/committee_v5_holdout5_b/results/"
    "v5_0_frozen_predictions.json"
)


@dataclass(frozen=True)
class ExpectedEvent:
    bill_no: str
    name: str
    family: str
    component_kinds: tuple[str, ...]
    official_five_year_million: int
    note: str = ""


EXPECTED = (
    ExpectedEvent(
        "2212092", "시민사회위원회", "analog_flat_operating_budget",
        ("whole_operating_baseline",), 600,
    ),
    ExpectedEvent(
        "2212092", "시ㆍ도시민사회위원회", "multi_instance_meeting_allowance",
        ("main_meeting_allowance",), 600,
    ),
    ExpectedEvent(
        "2213873", "과학기술국제협력전략위원회", "compound_committee_allowance",
        ("main_meeting_allowance", "subordinate_meeting_allowance"), 40,
        "실무위원회 30백만원은 부처의 회의 예상치를 활용함",
    ),
    ExpectedEvent(
        "2213873", "연구안보특별위원회", "meeting_allowance",
        ("main_meeting_allowance",), 20,
    ),
    ExpectedEvent(
        "2215199", "미래전략특별위원회", "staffed_committee_operation",
        (
            "staff_compensation",
            "basic_operating_expense",
            "asset_acquisition",
            "business_expense",
        ),
        4_880,
    ),
    ExpectedEvent(
        "2216353", "국가회계위원회", "staffed_committee_support_bundle",
        (
            "standing_member_compensation",
            "main_meeting_allowance",
            "subordinate_meeting_allowance",
            "support_staff_compensation",
            "support_operating_expense",
        ),
        15_139,
    ),
    ExpectedEvent(
        "2211745", "항공ㆍ철도사고조사위원회", "standing_member_replacement",
        (
            "standing_member_compensation",
            "workspace_operating_expense",
            "facility_setup",
            "asset_acquisition",
        ),
        1_815,
    ),
)


def _key(value: str) -> str:
    return re.sub(r"[ㆍ·・\s]+", "", value or "")


def _match(expected: str, actual: str) -> bool:
    expected_key = _key(expected)
    actual_key = _key(actual)
    return bool(
        expected_key and actual_key
        and (expected_key in actual_key or actual_key in expected_key)
    )


def _find_estimate(expected: str, estimates: list[dict]) -> dict | None:
    expected_key = _key(expected)
    matches = [
        value for value in estimates
        if _match(expected, value["committee_name"])
    ]
    if not matches:
        return None
    # Prefer the exact legal-body name.  This prevents a central `X위원회`
    # from swallowing the more specific `시ㆍ도 X위원회` event.
    return max(
        matches,
        key=lambda value: (
            _key(value["committee_name"]) == expected_key,
            len(_key(value["committee_name"])),
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("predictions", nargs="?", type=Path, default=PREDICTIONS)
    args = parser.parse_args()
    predictions_path = args.predictions
    predictions = json.loads(predictions_path.read_text(encoding="utf-8"))
    rows = []
    for expected in EXPECTED:
        estimates = predictions[expected.bill_no]["estimates"]
        estimate = _find_estimate(expected.name, estimates)
        if estimate is None:
            rows.append({
                **asdict(expected),
                "detected": False,
                "family_match": False,
                "component_match": False,
                "safe_abstention": False,
            })
            continue
        plan = estimate["formula_plan"]
        actual_components = tuple(value["kind"] for value in plan["components"])
        required_components = tuple(
            value["kind"] for value in plan["components"]
            if value.get("required", True)
        )
        component_coverage = all(
            kind in actual_components for kind in expected.component_kinds
        )
        rows.append({
            **asdict(expected),
            "detected": True,
            "detected_name": estimate["committee_name"],
            "detected_family": plan["family"],
            "detected_components": actual_components,
            "detected_required_components": required_components,
            "family_match": plan["family"] == expected.family,
            "component_match": actual_components == expected.component_kinds,
            "component_coverage": component_coverage,
            "compatible_formula_path": (
                plan["family"] == expected.family or component_coverage
            ),
            "decision": estimate["decision"],
            "safe_abstention": (
                estimate["decision"] == "human_input_required"
                and estimate["five_year_amount_thousand"] is None
            ),
            "numeric_draft_million": (
                estimate["five_year_amount_thousand"] / 1000
                if estimate["five_year_amount_thousand"] is not None
                else None
            ),
            "target_leak": estimate.get("selected_precedent_bill") == expected.bill_no,
        })

    payload = {
        "evaluation_type": "v5_second_five_bill_frozen_holdout",
        "bill_count": len(predictions),
        "official_event_count": len(EXPECTED),
        "detected_count": sum(bool(row["detected"]) for row in rows),
        "family_match_count": sum(bool(row["family_match"]) for row in rows),
        "component_match_count": sum(bool(row["component_match"]) for row in rows),
        "component_coverage_count": sum(
            bool(row.get("component_coverage")) for row in rows
        ),
        "compatible_formula_path_count": sum(
            bool(row.get("compatible_formula_path")) for row in rows
        ),
        "safe_abstention_count": sum(bool(row["safe_abstention"]) for row in rows),
        "numeric_draft_count": sum(
            row.get("numeric_draft_million") is not None for row in rows
        ),
        "target_leak_count": sum(bool(row.get("target_leak")) for row in rows),
        "rows": rows,
    }
    output = predictions_path.with_name(
        predictions_path.stem.replace("predictions", "evaluation") + ".json"
    )
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
