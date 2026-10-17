"""Evaluate the fifth five-bill committee regression batch.

Predictions are frozen before the official estimates are copied into the
batch directory.  This is a regression batch (the formula labels were used in
earlier structure tests), not a clean holdout.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import argparse
import json
from pathlib import Path
import re


DEFAULT_PREDICTIONS = Path(
    "backend/generated/committee_v5_regression5_e/results/"
    "v5_3_frozen_predictions.json"
)


@dataclass(frozen=True)
class ExpectedEvent:
    bill_no: str
    name: str
    family: str
    official_five_year_million: float


EXPECTED = (
    ExpectedEvent("2124970", "대전특별자치시지원위원회", "committee_support_bundle", 375),
    ExpectedEvent("2124970", "연구개발위원회", "analog_flat_operating_budget", 530),
    ExpectedEvent("2215935", "시민고충처리위원회", "multi_instance_operating_baseline", 5_530),
    ExpectedEvent("2216468", "대구경북특별시지원위원회", "committee_support_bundle", 641),
    ExpectedEvent("2216468", "대구경북특별시종합계획심의회", "meeting_allowance", 15),
    ExpectedEvent("2216517", "전남광주통합특별시지원위원회", "committee_support_bundle", 641),
    ExpectedEvent("2216517", "기본계획심의회", "meeting_allowance", 15),
    ExpectedEvent("2216517", "갯벌관리위원회", "meeting_allowance", 27),
    ExpectedEvent("2216520", "충남대전통합특별시지원위원회", "committee_support_bundle", 641),
    ExpectedEvent("2216520", "기본계획심의회", "meeting_allowance", 15),
    ExpectedEvent("2216520", "산림복지심의위원회", "meeting_allowance", 45),
    ExpectedEvent("2216520", "섬발전심의위원회", "meeting_allowance", 18),
    ExpectedEvent("2216520", "갯벌관리위원회", "meeting_allowance", 27),
)


def _key(value: str) -> str:
    return re.sub(r"[ㆍ·・\s]+", "", value or "")


def _matches(expected: str, actual: str) -> bool:
    left, right = _key(expected), _key(actual)
    return bool(left and right and (left in right or right in left))


def _find(expected: str, estimates: list[dict]) -> dict | None:
    target = _key(expected)
    matches = [row for row in estimates if _matches(expected, row["committee_name"])]
    if not matches:
        return None
    return max(
        matches,
        key=lambda row: (
            _key(row["committee_name"]) == target,
            len(_key(row["committee_name"])),
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("predictions", nargs="?", type=Path, default=DEFAULT_PREDICTIONS)
    args = parser.parse_args()
    predictions = json.loads(args.predictions.read_text(encoding="utf-8"))
    rows = []
    matched_actual: dict[str, set[str]] = {}
    for expected in EXPECTED:
        estimate = _find(expected.name, predictions[expected.bill_no]["estimates"])
        if estimate is None:
            rows.append({
                **asdict(expected), "detected": False, "family_match": False,
                "compatible_formula_path": False, "numeric_within_20_percent": False,
            })
            continue
        matched_actual.setdefault(expected.bill_no, set()).add(estimate["committee_name"])
        family = estimate["formula_plan"]["family"]
        alternatives = estimate["formula_plan"].get("evidence_alternatives") or []
        exact = family == expected.family
        compatible = exact or bool(
            expected.family == "analog_flat_operating_budget"
            and "structurally_identical_whole_budget_precedent" in alternatives
        )
        amount = (
            estimate["five_year_amount_thousand"] / 1000
            if estimate["five_year_amount_thousand"] is not None else None
        )
        error = (
            (amount - expected.official_five_year_million)
            / expected.official_five_year_million
            if amount is not None else None
        )
        rows.append({
            **asdict(expected),
            "detected": True,
            "detected_name": estimate["committee_name"],
            "detected_family": family,
            "family_match": exact,
            "compatible_formula_path": compatible,
            "decision": estimate["decision"],
            "numeric_draft_million": amount,
            "relative_error": error,
            "numeric_within_20_percent": error is not None and abs(error) <= 0.2,
            "safe_abstention": estimate["decision"] == "human_input_required" and amount is None,
            "target_leak": estimate.get("selected_precedent_bill") == expected.bill_no,
        })

    extras = []
    for bill_no, result in predictions.items():
        expected_names = [row.name for row in EXPECTED if row.bill_no == bill_no]
        for estimate in result["estimates"]:
            if not any(_matches(name, estimate["committee_name"]) for name in expected_names):
                extras.append({
                    "bill_no": bill_no,
                    "name": estimate["committee_name"],
                    "decision": estimate["decision"],
                })

    payload = {
        "evaluation_type": "v5_fifth_five_bill_regression",
        "bill_count": len(predictions),
        "official_event_count": len(EXPECTED),
        "detected_count": sum(bool(row["detected"]) for row in rows),
        "exact_family_match_count": sum(bool(row["family_match"]) for row in rows),
        "compatible_formula_path_count": sum(bool(row["compatible_formula_path"]) for row in rows),
        "numeric_draft_count": sum(row.get("numeric_draft_million") is not None for row in rows),
        "numeric_within_20_percent_count": sum(bool(row.get("numeric_within_20_percent")) for row in rows),
        "safe_abstention_count": sum(bool(row.get("safe_abstention")) for row in rows),
        "target_leak_count": sum(bool(row.get("target_leak")) for row in rows),
        "extra_candidate_count": len(extras),
        "extra_candidates": extras,
        "rows": rows,
    }
    output = args.predictions.with_name(
        args.predictions.stem.replace("predictions", "evaluation") + ".json"
    )
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
