"""Frozen post-v3.4 committee generalization check.

Cases were fixed before running v3.4 on them. Selection used only document
availability and official-estimate structure:

* two ordinary standing committee allowance cases with independently readable
  official component totals;
* one multi-instance committee, one compound incremental main/subcommittee,
  and one staffed committee boundary case.

Runtime retrieval excludes each target bill. Evaluator labels are never
imported by the estimator.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
import statistics

from backend.erce_web.committee_estimator_v3 import estimate_committee_from_pdf
from backend.erce_web.committee_estimator_v3.pipeline import ENGINE_VERSION
from backend.legacy.scripts.run_estimator_v2 import _pdf


@dataclass(frozen=True)
class GeneralizationCase:
    bill_no: str
    committee_key: str
    expected_mode: str
    official_component_million: float | None = None


CASES = (
    GeneralizationCase(
        "2126659",
        "가족돌봄아동·청소년·청년정책심의위원회",
        "single_committee_numeric",
        40.0,
    ),
    GeneralizationCase(
        "2216473",
        "갯벌관리위원회",
        "single_committee_numeric",
        32.0,
    ),
    GeneralizationCase(
        "2126145",
        "지역금융위원회",
        "multi_instance_boundary",
        1_190.0,
    ),
    GeneralizationCase(
        "2212282",
        "공무원임금위원회",
        "compound_incremental_boundary",
        25.0,
    ),
    GeneralizationCase(
        "2126685",
        "공공기관운영위원회",
        "staffed_committee_boundary",
        1_911.0,
    ),
)


def _compact(value: str) -> str:
    return re.sub(r"[\u318D\u00B7\s]+", "", value or "")


def main() -> None:
    rows: list[dict[str, object]] = []
    for case in CASES:
        source = _pdf(case.bill_no, False)
        if source is None:
            rows.append({
                "bill_no": case.bill_no,
                "committee": case.committee_key,
                "expected_mode": case.expected_mode,
                "detected": False,
                "failure": "source_pdf_missing",
            })
            continue
        first = estimate_committee_from_pdf(source.read_bytes(), filename=source.name)
        second = estimate_committee_from_pdf(source.read_bytes(), filename=source.name)
        matches = [
            estimate for estimate in first.estimates
            if _compact(case.committee_key) in _compact(estimate.committee_name)
            or _compact(estimate.committee_name) in _compact(case.committee_key)
        ]
        if not matches:
            rows.append({
                "bill_no": case.bill_no,
                "committee": case.committee_key,
                "expected_mode": case.expected_mode,
                "detected": False,
                "deterministic_repeat": asdict(first) == asdict(second),
                "failure": "committee_not_detected",
            })
            continue
        estimate = matches[0]
        amount_thousand = (
            estimate.gross_draft_annual_thousand * first.years
            if estimate.gross_draft_annual_thousand is not None
            else None
        )
        system_million = amount_thousand / 1000 if amount_thousand is not None else None
        error_pct = (
            round(
                (system_million - float(case.official_component_million))
                / float(case.official_component_million)
                * 100,
                2,
            )
            if system_million is not None and case.official_component_million
            else None
        )
        selected_bill = (
            estimate.selected_candidate.bill_no
            if estimate.selected_candidate else None
        )
        if case.expected_mode == "single_committee_numeric":
            mode_pass = error_pct is not None and abs(error_pct) <= 20
        elif case.expected_mode == "staffed_committee_boundary":
            mode_pass = (
                estimate.status == "out_of_scope"
                and system_million is None
            )
        else:
            mode_pass = (
                estimate.status == "review_required"
                and system_million is None
            )
        rows.append({
            "bill_no": case.bill_no,
            "committee": estimate.committee_name,
            "expected_mode": case.expected_mode,
            "detected": True,
            "official_component_million": case.official_component_million,
            "system_component_million": system_million,
            "error_pct": error_pct,
            "mode_pass": mode_pass,
            "status": estimate.status,
            "reason_codes": estimate.reason_codes,
            "selected_precedent_bill": selected_bill,
            "target_leak": selected_bill == case.bill_no,
            "deterministic_repeat": asdict(first) == asdict(second),
        })

    detected = [row for row in rows if row.get("detected")]
    numeric = [
        row for row in rows
        if row.get("expected_mode") == "single_committee_numeric"
        and row.get("error_pct") is not None
    ]
    numeric_errors = [abs(float(row["error_pct"])) for row in numeric]
    boundaries = [
        row for row in rows
        if row.get("expected_mode") != "single_committee_numeric"
    ]
    print(json.dumps({
        "evaluation_type": "frozen_post_v34_generalization",
        "engine_version": ENGINE_VERSION,
        "case_count": len(CASES),
        "detection_rate": round(len(detected) / len(CASES), 3),
        "numeric_coverage": round(len(numeric) / 2, 3),
        "numeric_within_20pct_rate": round(
            sum(bool(row.get("mode_pass")) for row in numeric) / 2,
            3,
        ),
        "numeric_mape_pct": (
            round(statistics.mean(numeric_errors), 2)
            if numeric_errors else None
        ),
        "boundary_safety_rate": round(
            sum(bool(row.get("mode_pass")) for row in boundaries) / len(boundaries),
            3,
        ),
        "overall_mode_pass_rate": round(
            sum(bool(row.get("mode_pass")) for row in rows) / len(CASES),
            3,
        ),
        "target_leak_count": sum(bool(row.get("target_leak")) for row in rows),
        "deterministic_repeat_rate": round(
            sum(bool(row.get("deterministic_repeat")) for row in rows) / len(CASES),
            3,
        ),
        "rows": rows,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
