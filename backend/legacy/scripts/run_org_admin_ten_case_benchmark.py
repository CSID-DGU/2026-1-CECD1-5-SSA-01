"""Run a reproducible 10-case organization/administration benchmark.

The target bill is excluded from retrieval by the v2 pipeline.  The last two
cases deliberately use prior-corpus summary values as diagnostic HITL inputs;
they are not presented as production-safe automatic estimates.

The official answer PDFs are read only after all predictions are produced.
They are evaluation oracles and never enter runtime selection/calculation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from backend.erce_web.estimator_v2 import (
    CanonicalInput,
    OrgAdminPlanRequest,
    estimate_from_pdf,
    resolve_org_admin_plan,
)
from backend.erce_web.estimator_v2.harness import audit_missed_evidence
from backend.erce_web.estimator_v2.regression import REGRESSION_CASES
from backend.legacy.scripts.evaluate_assembly_batch import _parse_first_cost_table
from backend.legacy.scripts.run_estimator_v2 import _pdf


# Two answer PDFs are narrative-only in the local seed, so retain the reviewed
# totals from the regression manifest for evaluation parsing.
OFFICIAL_FALLBACK_MILLION = {
    case.bill_no: case.official_million for case in REGRESSION_CASES
}


def _official_total_million(bill_no: str) -> int:
    answer = _pdf(bill_no, True)
    if answer:
        import fitz

        text = "\n".join(page.get_text() for page in fitz.open(answer))
        parsed = _parse_first_cost_table(text)
        if parsed.get("total") is not None:
            return int(parsed["total"])
    if bill_no in OFFICIAL_FALLBACK_MILLION:
        return int(OFFICIAL_FALLBACK_MILLION[bill_no])
    raise FileNotFoundError(f"official total unavailable: {bill_no}")


def _pipeline_prediction(case: Any) -> dict[str, Any]:
    source = _pdf(case.bill_no, False)
    if source is None:
        raise FileNotFoundError(f"source PDF unavailable: {case.bill_no}")
    result = estimate_from_pdf(
        source.read_bytes(),
        filename=source.name,
        include_non_attachment_search=False,
        organization_net_staff_count=(
            case.organization_net_staff_count
            if not case.organization_net_staff_key
            else None
        ),
        organization_net_staff_counts=(
            {
                case.organization_net_staff_key: case.organization_net_staff_count
            }
            if case.organization_net_staff_key
            and case.organization_net_staff_count is not None
            else None
        ),
        organization_staffing_scenario=case.organization_staffing_scenario,
        organization_annual_operating_budgets_thousand=(
            case.organization_annual_operating_budgets_thousand or None
        ),
        committee_variable_inputs=(case.committee_variable_inputs or None),
    )
    audit = audit_missed_evidence(case.bill_no, result)
    return {
        "bill_no": case.bill_no,
        "label": case.label,
        "total_million": round(result.total_thousand() / 1000, 3),
        "target_leak": bool(audit["target_leak"]),
        "prediction_mode": "v2_pipeline_target_excluded",
        "assumption_note": case.rationale or "회귀 케이스에 등록된 명시적 입력",
        "engine_version": result.engine_version,
        "audit_summary": audit["summary"],
    }


def _research_override_prediction() -> dict[str, Any]:
    bill_no = "2213320"
    source = _pdf(bill_no, False)
    if source is None:
        raise FileNotFoundError(bill_no)
    result = estimate_from_pdf(
        source.read_bytes(),
        filename=source.name,
        include_non_attachment_search=False,
        research_plan_enactment_override=True,
    )
    audit = audit_missed_evidence(bill_no, result)
    return {
        "bill_no": bill_no,
        "label": "인공지능데이터센터 기본계획·위원회",
        "total_million": round(result.total_thousand() / 1000, 3),
        "target_leak": bool(audit["target_leak"]),
        "prediction_mode": "v2_pipeline_target_excluded_with_research_override",
        "assumption_note": (
            "제정안 기본계획의 연구용역 추가성을 연구용 override로 허용; "
            "시행계획 행은 여전히 근거 부족으로 제외"
        ),
        "engine_version": result.engine_version,
        "audit_summary": audit["summary"],
    }


def _prior_input(value: float, unit: str, source_ref: str) -> CanonicalInput:
    return CanonicalInput(
        value=value,
        unit=unit,
        source="prior_excluded_corpus_summary",
        source_ref=source_ref,
    )


def _prior_median_prediction_2124970() -> dict[str, Any]:
    """Diagnostic only: use pre-target medians/mode, not target values."""
    bill_no = "2124970"
    ref = "sidecar-summary:before-2023-09-27"
    meeting = resolve_org_admin_plan(
        OrgAdminPlanRequest(
            route="committee",
            components=("committee_meeting",),
            years=5,
            target_bill_no=bill_no,
            cutoff_date="2023-09-27",
            inputs={
                "paid_member_count": _prior_input(12, "person", ref),
                "annual_meetings": _prior_input(4, "meeting/year", ref),
                "meeting_unit_price": _prior_input(
                    250_000, "KRW/person/meeting", ref
                ),
            },
        )
    )
    operation = resolve_org_admin_plan(
        OrgAdminPlanRequest(
            route="committee",
            components=("committee_operation",),
            years=5,
            target_bill_no=bill_no,
            cutoff_date="2023-09-27",
            inputs={
                "committee_operating_amount": _prior_input(
                    14_000_000, "KRW/year", ref
                )
            },
        )
    )
    # The bill has two named committees.  The same pre-target median is applied
    # to each operation row; this is a reviewable assumption, not a precedent
    # profile transfer.
    years = [
        m + (2 * o)
        for m, o in zip(meeting.year_totals_thousand, operation.year_totals_thousand)
    ]
    return {
        "bill_no": bill_no,
        "label": "대전특별자치시 지원위원회·연구개발위원회",
        "total_million": round(sum(years) / 1000, 3),
        "target_leak": False,
        "prediction_mode": "resolver_prior_median_diagnostic",
        "assumption_note": (
            "대상 의안 제외 선례 요약: 지급위원 12명(중앙값), 연 4회(중앙값), "
            "회당 25만원(최빈값), 위원회 운영비 연 1,400만원(중앙값)을 "
            "두 위원회에 적용"
        ),
        "engine_version": meeting.resolver_version,
        "resolver_status": meeting.status,
    }


def _prior_median_prediction_2216503() -> dict[str, Any]:
    bill_no = "2216503"
    ref = "sidecar-summary:before-2026-02-02"
    resolution = resolve_org_admin_plan(
        OrgAdminPlanRequest(
            route="committee",
            components=("committee_meeting",),
            years=5,
            target_bill_no=bill_no,
            cutoff_date="2026-02-02",
            inputs={
                "paid_member_count": _prior_input(10, "person", ref),
                "annual_meetings": _prior_input(4, "meeting/year", ref),
                "meeting_unit_price": _prior_input(
                    250_000, "KRW/person/meeting", ref
                ),
            },
        )
    )
    return {
        "bill_no": bill_no,
        "label": "위원후보추천위원회",
        "total_million": round(sum(resolution.year_totals_thousand) / 1000, 3),
        "target_leak": False,
        "prediction_mode": "resolver_prior_median_diagnostic",
        "assumption_note": (
            "대상 의안 제외 선례 요약의 지급위원 10명·연 4회·회당 25만원을 "
            "매년 정적 위원회 1개로 적용; 실제 후보추천 이벤트 일정은 미반영"
        ),
        "engine_version": resolution.resolver_version,
        "resolver_status": resolution.status,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="/private/tmp/org_admin_ten_case_benchmark.json")
    args = parser.parse_args()
    # Deterministic local-cache replay; no target answer is read in this phase.
    os.environ["ESTIMATOR_V2_OFFLINE"] = "1"

    predictions: list[dict[str, Any]] = []
    for case in REGRESSION_CASES:
        predictions.append(_pipeline_prediction(case))
    predictions.append(_research_override_prediction())
    predictions.append(_prior_median_prediction_2124970())
    predictions.append(_prior_median_prediction_2216503())

    # Evaluation oracle access happens only after every prediction above exists.
    for row in predictions:
        row["official_million"] = _official_total_million(row["bill_no"])
        official = float(row["official_million"])
        predicted = float(row["total_million"])
        row["error_pct"] = round((predicted - official) / official * 100, 2)
        row["abs_error_pct"] = round(abs(row["error_pct"]), 2)

    mape = round(
        sum(float(row["abs_error_pct"]) for row in predictions) / len(predictions),
        2,
    )
    payload = {
        "benchmark": "org-admin-ten-case-v1",
        "target_excluded": True,
        "prediction_count": len(predictions),
        "mape_pct": mape,
        "within_20_pct": sum(row["abs_error_pct"] <= 20 for row in predictions),
        "rows": predictions,
    }
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in predictions:
        print(
            f"{row['bill_no']} | {row['total_million']:.3f} | "
            f"{row['official_million']} | {row['error_pct']:+.2f}% | "
            f"leak={row['target_leak']}"
        )
    print(f"MAPE={mape:.2f}% | <=20%={payload['within_20_pct']}/{len(predictions)}")
    print(f"report={output}")


if __name__ == "__main__":
    main()
