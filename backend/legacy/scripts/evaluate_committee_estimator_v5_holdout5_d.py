"""Evaluate the frozen fourth five-bill v5 holdout."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import argparse
import json
from pathlib import Path
import re


DEFAULT_PREDICTIONS = Path(
    "backend/generated/committee_v5_holdout5_d/results/"
    "v5_2_frozen_predictions.json"
)


@dataclass(frozen=True)
class ExpectedEvent:
    bill_no: str
    name: str
    family: str
    component_kinds: tuple[str, ...]
    official_five_year_million: float


EXPECTED = (
    ExpectedEvent(
        "2124966", "글로벌생명경제도시종합계획심의회", "meeting_allowance",
        ("main_meeting_allowance",), 50,
    ),
    ExpectedEvent(
        "2126659", "가족돌봄아동ㆍ청소년ㆍ청년정책심의위원회", "meeting_allowance",
        ("main_meeting_allowance",), 40,
    ),
    ExpectedEvent(
        "2126679", "돌봄근로자처우개선위원회", "compound_committee_allowance",
        ("main_meeting_allowance", "subordinate_meeting_allowance"), 78,
    ),
    ExpectedEvent(
        "2126679", "시ㆍ군ㆍ구돌봄근로자처우개선위원회", "multi_instance_meeting_allowance",
        ("main_meeting_allowance",), 14_700,
    ),
    ExpectedEvent(
        "2126685", "공공기관운영위원회", "reorganized_committee_support_bundle",
        ("subordinate_operating_baseline", "support_operating_baseline"), 4_929,
    ),
    ExpectedEvent(
        "2216473", "전북자치도갯벌관리위원회", "meeting_allowance",
        ("main_meeting_allowance",), 32,
    ),
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
                "component_match": False, "numeric_within_20_percent": False,
            })
            continue
        matched_actual.setdefault(expected.bill_no, set()).add(estimate["committee_name"])
        plan = estimate["formula_plan"]
        components = tuple(row["kind"] for row in plan["components"])
        amount = (
            estimate["five_year_amount_thousand"] / 1000
            if estimate["five_year_amount_thousand"] is not None else None
        )
        error = (
            (amount - expected.official_five_year_million)
            / expected.official_five_year_million
            if amount is not None and expected.official_five_year_million else None
        )
        rows.append({
            **asdict(expected),
            "detected": True,
            "detected_name": estimate["committee_name"],
            "detected_family": plan["family"],
            "detected_components": components,
            "family_match": plan["family"] == expected.family,
            "component_match": components == expected.component_kinds,
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
                extras.append({"bill_no": bill_no, "name": estimate["committee_name"]})

    payload = {
        "evaluation_type": "v5_fourth_five_bill_holdout",
        "bill_count": len(predictions),
        "official_event_count": len(EXPECTED),
        "detected_count": sum(bool(row["detected"]) for row in rows),
        "family_match_count": sum(bool(row["family_match"]) for row in rows),
        "component_match_count": sum(bool(row["component_match"]) for row in rows),
        "numeric_draft_count": sum(row.get("numeric_draft_million") is not None for row in rows),
        "numeric_within_20_percent_count": sum(bool(row.get("numeric_within_20_percent")) for row in rows),
        "safe_abstention_count": sum(bool(row.get("safe_abstention")) for row in rows),
        "target_leak_count": sum(bool(row.get("target_leak")) for row in rows),
        "extra_event_count": len(extras),
        "extra_events": extras,
        "rows": rows,
    }
    output = args.predictions.with_name(
        args.predictions.stem.replace("predictions", "evaluation") + ".json"
    )
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
