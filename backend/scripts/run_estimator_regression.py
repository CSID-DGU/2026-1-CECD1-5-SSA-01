"""Run all previously validated v2 scenarios as an acceptance gate."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from backend.estimator_v2 import estimate_from_pdf
from backend.estimator_v2.harness import audit_missed_evidence
from backend.estimator_v2.regression import (
    REGRESSION_CASES,
    REGRESSION_MANIFEST_VERSION,
    audit_formula_expectations,
    evaluate_regression_case,
)
from backend.scripts.run_estimator_v2 import _pdf


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bill",
        action="append",
        dest="bills",
        help="특정 회귀 의안만 실행(여러 번 지정 가능)",
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument(
        "--live",
        action="store_true",
        help="캐시 누락 시 외부 LLM/임베딩 API 호출 허용",
    )
    parser.add_argument(
        "--out",
        default="/private/tmp/estimator_v2_regression.json",
    )
    args = parser.parse_args()
    if args.refresh and not args.live:
        raise SystemExit("--refresh는 --live와 함께만 사용할 수 있습니다.")
    if not args.live:
        os.environ["ESTIMATOR_V2_OFFLINE"] = "1"

    requested = set(args.bills or [])
    cases = [
        case
        for case in REGRESSION_CASES
        if not requested or case.bill_no in requested
    ]
    unknown = requested - {case.bill_no for case in REGRESSION_CASES}
    if unknown:
        raise SystemExit(f"등록되지 않은 회귀 의안: {sorted(unknown)}")

    rows: list[dict[str, object]] = []
    for case in cases:
        source = _pdf(case.bill_no, False)
        if not source:
            rows.append(
                {
                    "bill_no": case.bill_no,
                    "passed": False,
                    "failure_reasons": ["의안원문 PDF 없음"],
                }
            )
            continue
        result = estimate_from_pdf(
            source.read_bytes(),
            filename=source.name,
            refresh=args.refresh,
            # The amount gate replays a fixed local evidence snapshot.  The
            # external non-attachment channel is checked separately because an
            # offline cache miss is "unavailable", not negative evidence.
            include_non_attachment_search=False,
            organization_net_staff_count=(
                case.organization_net_staff_count
                if not case.organization_net_staff_key
                else None
            ),
            organization_net_staff_counts=(
                {
                    case.organization_net_staff_key:
                    case.organization_net_staff_count
                }
                if case.organization_net_staff_key
                and case.organization_net_staff_count is not None
                else None
            ),
            organization_staffing_scenario=case.organization_staffing_scenario,
            organization_annual_operating_budgets_thousand=(
                case.organization_annual_operating_budgets_thousand or None
            ),
            committee_variable_inputs=(
                case.committee_variable_inputs or None
            ),
        )
        audit = audit_missed_evidence(case.bill_no, result)
        formula_audit = audit_formula_expectations(case, result)
        row = evaluate_regression_case(
            case,
            system_million=result.total_thousand() / 1000,
            target_leak=bool(audit["target_leak"]),
            formula_failure_reasons=list(
                formula_audit["failure_reasons"]
            ),
        )
        row["engine_version"] = result.engine_version
        row["prompt_version"] = result.prompt_version
        row["dataset_fingerprint"] = result.dataset_fingerprint
        row["input_hash"] = result.input_hash
        row["evidence_audit_summary"] = audit["summary"]
        row["formula_audit"] = formula_audit
        rows.append(row)
        status = "PASS" if row["passed"] else "FAIL"
        print(
            f"[{status}] {case.bill_no} {case.label}: "
            f"{row['system_million']} / {case.official_million}백만원 "
            f"({row['error_pct']}%)"
        )

    payload = {
        "manifest_version": REGRESSION_MANIFEST_VERSION,
        "mode": "live" if args.live else "offline_cache_replay",
        "non_attachment_channel": "separate_from_amount_regression",
        "passed": bool(rows) and all(bool(row.get("passed")) for row in rows),
        "rows": rows,
    }
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"report={output}")
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
