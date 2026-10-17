"""Evaluator-only audit of the covered committee estimator.

Target TAG amounts are used only after inference as gold labels.  They are
never passed to the resolver or estimator.
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any

from backend.erce_web.committee_covered_estimator import (
    _full_year_amount,
    _is_committee_item,
    _year_values,
    estimate,
)
from backend.erce_web.committee_precedent_resolver import _bill_items


ROOT = Path(__file__).resolve().parents[3]
PILOT = ROOT / "backend/generated/committee_precedent_pilot"


def _case_sets() -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    for label_value in glob.glob(str(PILOT / "*labels.json")):
        labels = Path(label_value)
        stem = labels.name.removesuffix("_labels.json")
        candidates = [PILOT / f"{stem}_cases.json"]
        if labels.name == "manual_best_evidence_labels.json":
            candidates.insert(0, PILOT / "pilot_cases.json")
        case_path = next((path for path in candidates if path.exists()), None)
        if case_path is not None:
            pairs.append((case_path, labels))
    return pairs


def _exact_cases() -> list[dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for cases_path, labels_path in _case_sets():
        cases = {
            str(row["bill_no"]): row
            for row in json.loads(cases_path.read_text(encoding="utf-8"))
        }
        labels = json.loads(labels_path.read_text(encoding="utf-8"))
        for label in labels:
            if label.get("evidence_status") != "exact_document":
                continue
            bill_no = str(label["bill_no"])
            if bill_no in cases:
                output.setdefault(bill_no, cases[bill_no])
    return list(output.values())


def _gold(case: dict[str, Any]) -> dict[str, Any]:
    items = [item for item in _bill_items(str(case["bill_no"])) if _is_committee_item(item)]
    bases = [_full_year_amount(item) for item in items]
    full_year = sum(value for value in bases if value is not None) if all(
        value is not None for value in bases
    ) else None
    series_rows = [_year_values(item.item_id) for item in items]
    timeline = None
    if series_rows and all(rows for rows in series_rows):
        length = max(len(rows) for rows in series_rows)
        timeline = tuple(
            sum(rows[index] if index < len(rows) else 0 for rows in series_rows)
            for index in range(length)
        )
    return {
        "item_ids": [item.item_id for item in items],
        "full_year_thousand": full_year,
        "yearly_thousand": timeline,
        "total_thousand": sum(timeline) if timeline is not None else None,
    }


def evaluate() -> dict[str, Any]:
    rows = []
    for case in _exact_cases():
        result = estimate(case)
        gold = _gold(case)
        full_year_error = None
        if result.full_year_thousand is not None and gold["full_year_thousand"]:
            full_year_error = (
                result.full_year_thousand - gold["full_year_thousand"]
            ) / gold["full_year_thousand"]
        total_error = None
        if result.total_thousand is not None and gold["total_thousand"]:
            total_error = (
                result.total_thousand - gold["total_thousand"]
            ) / gold["total_thousand"]
        rows.append(
            {
                "bill_no": str(case["bill_no"]),
                "decision": result.decision,
                "ready_for_auto_publish": result.ready_for_auto_publish,
                "precedent": result.selected_bill_no,
                "blockers": list(result.blockers),
                "warnings": list(result.warnings),
                "prediction_full_year_thousand": result.full_year_thousand,
                "gold_full_year_thousand": gold["full_year_thousand"],
                "full_year_error": full_year_error,
                "prediction_total_thousand": result.total_thousand,
                "gold_total_thousand": gold["total_thousand"],
                "total_error": total_error,
            }
        )

    calculated = [row for row in rows if row["decision"] == "calculated"]
    comparable_full = [row for row in calculated if row["full_year_error"] is not None]
    comparable_total = [row for row in calculated if row["total_error"] is not None]
    return {
        "evaluation_role": "development_regression_not_blind_holdout",
        "case_count": len(rows),
        "calculated_count": len(calculated),
        "blocked_count": len(rows) - len(calculated),
        "ready_for_auto_publish_count": sum(
            bool(row["ready_for_auto_publish"]) for row in rows
        ),
        "full_year_within_20pct": sum(
            abs(row["full_year_error"]) <= 0.20 for row in comparable_full
        ),
        "full_year_comparable_count": len(comparable_full),
        "timeline_total_within_20pct": sum(
            abs(row["total_error"]) <= 0.20 for row in comparable_total
        ),
        "timeline_total_comparable_count": len(comparable_total),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = evaluate()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(
        f"cases={payload['case_count']} calculated={payload['calculated_count']} "
        f"blocked={payload['blocked_count']} "
        f"full_year<=20%={payload['full_year_within_20pct']}/"
        f"{payload['full_year_comparable_count']} "
        f"timeline<=20%={payload['timeline_total_within_20pct']}/"
        f"{payload['timeline_total_comparable_count']}"
    )
    for row in payload["rows"]:
        full = (
            "n/a" if row["full_year_error"] is None else f"{row['full_year_error']:+.1%}"
        )
        total = "n/a" if row["total_error"] is None else f"{row['total_error']:+.1%}"
        print(
            f"{row['bill_no']} {row['decision']} precedent={row['precedent'] or '-'} "
            f"full_year={full} total={total} "
            f"blockers={','.join(row['blockers']) or '-'}"
        )


if __name__ == "__main__":
    main()
