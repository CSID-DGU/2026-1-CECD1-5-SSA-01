"""Run the isolated covered estimator over the local committee 50 set.

The target amount lookup is evaluator-only and happens after each prediction.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.committee_covered_estimator import estimate
from backend.legacy.scripts.build_committee50_hierarchical_cases import build_cases
from backend.legacy.scripts.evaluate_committee_covered_estimator import _gold


def evaluate() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in build_cases():
        result = estimate(case)
        gold = _gold(case)
        package = result.package
        if result.decision == "calculated":
            evidence_status = (
                "auto_publish_ready"
                if result.ready_for_auto_publish
                else "calculated_review_required"
            )
        elif package.decision == "exact_package" and package.matched_item_ids:
            # The lineage and existing cost items are useful, but at least one
            # target-only component prevents whole-package execution.
            evidence_status = "incomplete_exact_package"
        elif package.decision == "component_only" and package.matched_item_ids:
            evidence_status = "component_candidate_available"
        elif package.decision == "component_only" and package.selected_bill_no:
            evidence_status = "related_document_only"
        else:
            # This does not mean that no reference exists in the world or in
            # the raw corpus.  It means that the resolver did not verify a
            # transferable relation from the currently structured evidence.
            evidence_status = "no_verified_evidence_route"
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
                "evidence_status": evidence_status,
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
    evidence_status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row["evidence_status"])
        evidence_status_counts[status] = evidence_status_counts.get(status, 0) + 1
    comparable_full = [row for row in calculated if row["full_year_error"] is not None]
    comparable_total = [row for row in calculated if row["total_error"] is not None]
    return {
        "evaluation_role": "development_regression_not_blind_holdout",
        "answer_usage": "post_inference_metrics_only",
        "case_count": len(rows),
        "calculated_count": len(calculated),
        "ready_for_auto_publish_count": sum(
            bool(row["ready_for_auto_publish"]) for row in calculated
        ),
        "review_required_count": sum(
            not bool(row["ready_for_auto_publish"]) for row in calculated
        ),
        "blocked_count": len(rows) - len(calculated),
        "evidence_status_counts": evidence_status_counts,
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
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"cases={payload['case_count']} calculated={payload['calculated_count']} "
        f"ready={payload['ready_for_auto_publish_count']} "
        f"review={payload['review_required_count']} blocked={payload['blocked_count']} "
        f"full_year<=20%={payload['full_year_within_20pct']}/"
        f"{payload['full_year_comparable_count']} "
        f"timeline<=20%={payload['timeline_total_within_20pct']}/"
        f"{payload['timeline_total_comparable_count']}"
    )
    print("evidence=" + json.dumps(payload["evidence_status_counts"], ensure_ascii=False))
    for row in payload["rows"]:
        if row["decision"] != "calculated" and not row["blockers"]:
            continue
        if row["decision"] == "calculated":
            full = f"{row['full_year_error']:+.2%}" if row["full_year_error"] is not None else "n/a"
            total = f"{row['total_error']:+.2%}" if row["total_error"] is not None else "n/a"
            print(
                row["bill_no"], row["decision"], f"precedent={row['precedent']}",
                f"ready={row['ready_for_auto_publish']}", f"full={full}", f"total={total}",
            )


if __name__ == "__main__":
    main()
