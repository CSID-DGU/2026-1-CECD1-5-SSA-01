"""Run the isolated committee estimator against a stored Assembly bill."""
from __future__ import annotations

import argparse
import json

from backend.committee_estimator_v3 import estimate_committee_from_pdf
from backend.legacy.scripts.run_estimator_v2 import _pdf


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bill")
    parser.add_argument("--committee-key")
    parser.add_argument("--paid-members", type=float)
    parser.add_argument("--incumbent-paid-members", type=float)
    parser.add_argument("--annual-meetings", type=float)
    parser.add_argument("--unit-price-won", type=float)
    parser.add_argument("--confirm-no-existing-baseline", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    source = _pdf(args.bill, False)
    if not source:
        raise SystemExit(f"의안원문 PDF 없음: {args.bill}")
    values = {
        key: value
        for key, value in {
            "paid_members": args.paid_members,
            "incumbent_paid_members": args.incumbent_paid_members,
            "annual_meetings": args.annual_meetings,
            "unit_price_won": args.unit_price_won,
        }.items()
        if value is not None
    }
    if args.confirm_no_existing_baseline:
        values["confirm_no_existing_baseline"] = True
    user_inputs = (
        {args.committee_key: values}
        if args.committee_key and values
        else None
    )
    result = estimate_committee_from_pdf(
        source.read_bytes(),
        filename=source.name,
        user_inputs=user_inputs,
        refresh=args.refresh,
    )
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return
    print(f"[{result.engine_version}] {result.bill_no} {result.bill_name}")
    for estimate in result.estimates:
        draft = (
            f"{estimate.gross_draft_annual_thousand / 1000:.1f}백만원/년"
            if estimate.gross_draft_annual_thousand is not None
            else "-"
        )
        final = (
            f"{estimate.five_year_amount_thousand / 1000:.1f}백만원/5년"
            if estimate.five_year_amount_thousand is not None
            else "미확정"
        )
        print(f"- {estimate.committee_name}: {estimate.status} / 초안 {draft} / 확정 {final}")
        print(f"  {estimate.reason}")
        if estimate.selected_candidate:
            candidate = estimate.selected_candidate
            print(
                f"  선례 {candidate.bill_no}:{candidate.item_name} "
                f"구조점수={candidate.total_score}/21"
            )
        for field in estimate.review_fields:
            print(f"  입력 필요: {field['label']} — {field['reason']}")


if __name__ == "__main__":
    main()
