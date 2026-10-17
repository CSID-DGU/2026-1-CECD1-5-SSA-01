"""Post-freeze generalization check for committee estimator v3.3.

These cases were selected before running the estimator because both the bill
PDF and official cost-estimate PDF exist and the official committee component
is independently identifiable. They were not used in the original v3.0-v3.3
development regression. Runtime code never imports the evaluator labels.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
import statistics

from backend.committee_estimator_v3 import estimate_committee_from_pdf
from backend.committee_estimator_v3.pipeline import ENGINE_VERSION
from backend.scripts.run_estimator_v2 import _pdf


@dataclass(frozen=True)
class HoldoutCase:
    bill_no: str
    committee_key: str
    official_component_million: float


CASES = (
    HoldoutCase("2124118", "공익법인위원회", 60.0),
    HoldoutCase("2124970", "대전특별자치시 지원위원회", 75.0),
    HoldoutCase("2126679", "돌봄근로자처우개선위원회", 60.0),
    HoldoutCase("2216065", "보호심의위원회", 25.0),
    HoldoutCase("2217718", "국가인공지능데이터센터진흥전문위원회", 15.6),
)


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def main() -> None:
    rows: list[dict[str, object]] = []
    for case in CASES:
        source = _pdf(case.bill_no, False)
        if source is None:
            rows.append({
                "bill_no": case.bill_no,
                "committee": case.committee_key,
                "detected": False,
                "failure": "source_pdf_missing",
            })
            continue
        first = estimate_committee_from_pdf(source.read_bytes(), filename=source.name)
        second = estimate_committee_from_pdf(source.read_bytes(), filename=source.name)
        matches = [
            estimate for estimate in first.estimates
            if _compact(case.committee_key) in _compact(estimate.committee_name)
        ]
        if not matches:
            rows.append({
                "bill_no": case.bill_no,
                "committee": case.committee_key,
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
                (system_million - case.official_component_million)
                / case.official_component_million
                * 100,
                2,
            )
            if system_million is not None else None
        )
        selected_bill = (
            estimate.selected_candidate.bill_no
            if estimate.selected_candidate else None
        )
        rows.append({
            "bill_no": case.bill_no,
            "committee": estimate.committee_name,
            "detected": True,
            "official_component_million": case.official_component_million,
            "system_component_million": system_million,
            "error_pct": error_pct,
            "within_20pct": error_pct is not None and abs(error_pct) <= 20,
            "status": estimate.status,
            "reason_codes": estimate.reason_codes,
            "selected_precedent_bill": selected_bill,
            "target_leak": selected_bill == case.bill_no,
            "deterministic_repeat": asdict(first) == asdict(second),
        })

    detected = [row for row in rows if row.get("detected")]
    numeric = [row for row in detected if row.get("error_pct") is not None]
    errors = [abs(float(row["error_pct"])) for row in numeric]
    summary = {
        "evaluation_type": "post_freeze_additional_holdout",
        "engine_version": ENGINE_VERSION,
        "case_count": len(CASES),
        "detection_rate": round(len(detected) / len(CASES), 3),
        "numeric_coverage": round(len(numeric) / len(CASES), 3),
        "within_20pct_rate_all": round(
            sum(bool(row.get("within_20pct")) for row in rows) / len(CASES), 3
        ),
        "within_20pct_rate_numeric": (
            round(sum(bool(row.get("within_20pct")) for row in numeric) / len(numeric), 3)
            if numeric else None
        ),
        "numeric_mape_pct": round(statistics.mean(errors), 2) if errors else None,
        "numeric_median_ape_pct": round(statistics.median(errors), 2) if errors else None,
        "target_leak_count": sum(bool(row.get("target_leak")) for row in rows),
        "deterministic_repeat_rate": round(
            sum(bool(row.get("deterministic_repeat")) for row in rows) / len(CASES), 3
        ),
        "rows": rows,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
