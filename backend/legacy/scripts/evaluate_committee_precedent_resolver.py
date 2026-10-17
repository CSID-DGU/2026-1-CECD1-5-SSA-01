"""Evaluate the isolated item-level precedent resolver."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.erce_web.committee_precedent_resolver import resolve


def evaluate(cases_path: Path) -> dict[str, Any]:
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    for case in cases:
        resolution = resolve(case)
        expected_exact = str(case.get("expected_decision") or "") == "retrieve"
        predicted_exact = resolution.decision == "exact_package"
        gold = {str(value) for value in case.get("gold_bill_nos") or []}
        selected_correct = not predicted_exact or resolution.selected_bill_no in gold
        correct = predicted_exact == expected_exact and selected_correct
        results.append(
            {
                **resolution.to_dict(),
                "expected_exact": expected_exact,
                "correct": correct,
                "db_status": case.get("db_status"),
                "failure_type": case.get("failure_type"),
            }
        )

    positives = [row for row in results if row["expected_exact"]]
    negatives = [row for row in results if not row["expected_exact"]]
    predicted = [row for row in results if row["decision"] == "exact_package"]
    true_positive = sum(bool(row["correct"]) for row in positives)
    false_positive = sum(not bool(row["expected_exact"]) for row in predicted)
    return {
        "case_count": len(results),
        "correct_count": sum(bool(row["correct"]) for row in results),
        "exact_recall": true_positive / len(positives) if positives else None,
        "exact_precision": (
            (len(predicted) - false_positive) / len(predicted) if predicted else None
        ),
        "positive_count": len(positives),
        "positive_correct": true_positive,
        "negative_count": len(negatives),
        "negative_correct": sum(bool(row["correct"]) for row in negatives),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = evaluate(args.cases)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(
        f"resolver correct={payload['correct_count']}/{payload['case_count']} "
        f"exact={payload['positive_correct']}/{payload['positive_count']} "
        f"safe={payload['negative_correct']}/{payload['negative_count']} "
        f"precision={payload['exact_precision']} recall={payload['exact_recall']}"
    )
    for row in payload["results"]:
        print(
            row["bill_no"],
            f"expected_exact={row['expected_exact']}",
            f"decision={row['decision']}",
            f"selected={row['selected_bill_no'] or '-'}",
            f"correct={row['correct']}",
            f"missing={','.join(row['missing_components']) or '-'}",
            f"conflicts={','.join(row['conflicts']) or '-'}",
        )


if __name__ == "__main__":
    main()
