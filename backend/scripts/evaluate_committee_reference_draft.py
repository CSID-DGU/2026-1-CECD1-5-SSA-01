"""Compare strict evidence gating with review-only precedent drafts.

Official component totals are evaluator-only labels.  Candidate selection and
draft calculation finish before each label is used to compute an error.
This is a development regression, not a blind generalization benchmark.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import statistics

from backend.committee_estimator_v3 import estimate_committee_from_pdf
from backend.scripts.evaluate_committee_hierarchical_pilot import (
    CASES,
    _eligible_draft,
)
from backend.scripts.run_estimator_v2 import _pdf


def _key(value: str) -> str:
    return re.sub(r"[ㆍ·・\s]+", "", value or "")


def evaluate() -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for case in CASES:
        source = _pdf(case.bill_no, False)
        if source is None:
            raise FileNotFoundError(f"의안원문 PDF 없음: {case.bill_no}")
        result = estimate_committee_from_pdf(source.read_bytes(), filename=source.name)
        estimate = next(
            value
            for value in result.estimates
            if _key(case.committee_key) in _key(value.committee_name)
        )
        strict_eligible, strict_basis = _eligible_draft(estimate)
        reference_million = (
            estimate.gross_draft_annual_thousand * result.years / 1000
            if estimate.gross_draft_annual_thousand is not None
            else None
        )
        # Gold enters only here, after inference is complete.
        error_pct = (
            (reference_million - case.official_component_million)
            / case.official_component_million
            * 100
            if reference_million is not None
            else None
        )
        rows.append(
            {
                "bill_no": case.bill_no,
                "committee": estimate.committee_name,
                "selected_precedent_bill": (
                    estimate.selected_candidate.bill_no
                    if estimate.selected_candidate
                    else None
                ),
                "strict_decision": (
                    "numeric_draft" if strict_eligible else "human_input_required"
                ),
                "strict_basis": strict_basis,
                "reference_draft_million": reference_million,
                "official_component_million": case.official_component_million,
                "reference_error_pct": error_pct,
                "reference_within_20pct": (
                    error_pct is not None and abs(error_pct) <= 20
                ),
                "target_leak": bool(
                    estimate.selected_candidate
                    and estimate.selected_candidate.bill_no == case.bill_no
                ),
            }
        )

    reference_rows = [row for row in rows if row["reference_error_pct"] is not None]
    strict_rows = [row for row in rows if row["strict_decision"] == "numeric_draft"]
    return {
        "evaluation_type": "development_regression_not_blind_holdout",
        "answer_usage": "post_inference_metrics_only",
        "case_count": len(rows),
        "strict_numeric_count": len(strict_rows),
        "strict_within_20pct": sum(
            bool(row["reference_within_20pct"]) for row in strict_rows
        ),
        "reference_numeric_count": len(reference_rows),
        "reference_within_20pct": sum(
            bool(row["reference_within_20pct"]) for row in reference_rows
        ),
        "reference_mape_pct": statistics.mean(
            abs(float(row["reference_error_pct"])) for row in reference_rows
        ),
        "target_leak_count": sum(bool(row["target_leak"]) for row in rows),
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
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
