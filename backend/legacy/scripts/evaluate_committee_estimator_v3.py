"""Formula-aware regression for the isolated committee estimator.

The official component totals below are evaluator-only labels reviewed from
the Assembly cost-estimate PDFs.  Runtime retrieval and calculation never
import this module or read these labels.  These cases guided development, so
the output is a regression certificate, not an unseen holdout score.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json

from backend.erce_web.committee_estimator_v3 import estimate_committee_from_pdf
from backend.legacy.scripts.run_estimator_v2 import _pdf


@dataclass(frozen=True)
class Case:
    bill_no: str
    committee_key: str
    official_component_million: float
    value_kind: str
    expected_status: str
    expected_precedent_bill: str | None = None
    user_inputs: dict[str, float | bool] = field(default_factory=dict)


CASES = (
    Case(
        bill_no="2214559",
        committee_key="친환경농어업발전위원회",
        official_component_million=120,
        value_kind="review_draft",
        expected_status="review_required",
        expected_precedent_bill="2214238",
    ),
    Case(
        bill_no="2126334",
        committee_key="국립대학병원발전위원회",
        official_component_million=55,
        value_kind="review_draft",
        expected_status="review_required",
        expected_precedent_bill="2125005",
    ),
    Case(
        bill_no="2125736",
        committee_key="공무원보수위원회",
        official_component_million=55,
        value_kind="confirmed",
        expected_status="computed",
        user_inputs={
            "incumbent_paid_members": 10,
            "unit_price_won": 350_000,
            "annual_meetings": 4,
        },
    ),
)

SAFETY_CASES = (
    ("2213320", "국가인공지능데이터센터진흥위원회", "PRECEDENT_DISAGREEMENT"),
    ("2216503", "위원후보추천위원회", "EVENT_DRIVEN_FORMULA_REQUIRED"),
)


def main() -> None:
    rows: list[dict[str, object]] = []
    for case in CASES:
        source = _pdf(case.bill_no, False)
        if source is None:
            raise SystemExit(f"원문 PDF 없음: {case.bill_no}")
        result = estimate_committee_from_pdf(
            source.read_bytes(),
            filename=source.name,
            user_inputs=(
                {case.committee_key: case.user_inputs}
                if case.user_inputs
                else None
            ),
        )
        repeated = estimate_committee_from_pdf(
            source.read_bytes(),
            filename=source.name,
            user_inputs=(
                {case.committee_key: case.user_inputs}
                if case.user_inputs
                else None
            ),
        )
        deterministic = asdict(result) == asdict(repeated)
        estimate = next(
            value
            for value in result.estimates
            if case.committee_key in value.committee_name
        )
        if case.value_kind == "review_draft":
            amount_thousand = (
                estimate.gross_draft_annual_thousand * result.years
                if estimate.gross_draft_annual_thousand is not None
                else None
            )
        else:
            amount_thousand = estimate.five_year_amount_thousand
        system_million = (
            amount_thousand / 1000 if amount_thousand is not None else None
        )
        error_pct = (
            round(
                (system_million - case.official_component_million)
                / case.official_component_million
                * 100,
                2,
            )
            if system_million is not None
            else None
        )
        selected_bill = (
            estimate.selected_candidate.bill_no
            if estimate.selected_candidate
            else None
        )
        variable_keys = {value.key for value in estimate.variables}
        formula_ok = variable_keys == {
            "paid_members",
            "incumbent_paid_members",
            "unit_price_won",
            "annual_meetings",
        }
        failures: list[str] = []
        if estimate.status != case.expected_status:
            failures.append(
                f"상태 {estimate.status} != {case.expected_status}"
            )
        if case.expected_precedent_bill != selected_bill:
            failures.append(
                f"선례 {selected_bill} != {case.expected_precedent_bill}"
            )
        if selected_bill == case.bill_no:
            failures.append("대상 의안 정답 누출")
        if not formula_ok:
            failures.append("산식 변수 역할 불완전")
        if error_pct is None or abs(error_pct) > 20:
            failures.append(f"절대오차 20% 초과: {error_pct}")
        if not deterministic:
            failures.append("동일 입력 반복 결과가 다름")
        rows.append(
            {
                "bill_no": case.bill_no,
                "committee": estimate.committee_name,
                "value_kind": case.value_kind,
                "official_component_million": case.official_component_million,
                "system_component_million": system_million,
                "error_pct": error_pct,
                "status": estimate.status,
                "selected_precedent_bill": selected_bill,
                "target_leak": selected_bill == case.bill_no,
                "formula_ok": formula_ok,
                "deterministic_repeat": deterministic,
                "passed": not failures,
                "failure_reasons": failures,
            }
        )
    safety_rows: list[dict[str, object]] = []
    for bill_no, committee_key, expected_reason in SAFETY_CASES:
        source = _pdf(bill_no, False)
        if source is None:
            raise SystemExit(f"원문 PDF 없음: {bill_no}")
        result = estimate_committee_from_pdf(
            source.read_bytes(),
            filename=source.name,
        )
        repeated = estimate_committee_from_pdf(
            source.read_bytes(),
            filename=source.name,
        )
        estimate = next(
            value
            for value in result.estimates
            if committee_key in value.committee_name
        )
        safe_abstention = (
            estimate.status == "review_required"
            and estimate.annual_amount_thousand is None
            and estimate.gross_draft_annual_thousand is None
            and expected_reason in estimate.reason_codes
            and asdict(result) == asdict(repeated)
        )
        safety_rows.append(
            {
                "bill_no": bill_no,
                "committee": estimate.committee_name,
                "expected_route": expected_reason,
                "status": estimate.status,
                "numeric_output": False
                if estimate.gross_draft_annual_thousand is None
                else estimate.gross_draft_annual_thousand / 1000,
                "passed": safe_abstention,
                "deterministic_repeat": asdict(result) == asdict(repeated),
            }
        )
    print(
        json.dumps(
            {
                "evaluation_type": "development_regression_not_unseen_holdout",
                "passed": (
                    all(bool(row["passed"]) for row in rows)
                    and all(bool(row["passed"]) for row in safety_rows)
                ),
                "rows": rows,
                "safety_rows": safety_rows,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
