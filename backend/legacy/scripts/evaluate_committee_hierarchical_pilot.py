"""Committee pilot for evidence-gated committee estimation.

The runtime estimator never imports this module.  Official values below are
evaluation labels only: draft eligibility is decided first from provenance,
identity, and independent-cohort evidence, then compared with the labels.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import statistics

from backend.erce_web.committee_estimator_v3 import estimate_committee_from_pdf
from backend.legacy.scripts.run_estimator_v2 import _pdf


@dataclass(frozen=True)
class PilotCase:
    bill_no: str
    committee_key: str
    official_component_million: float


CASES = (
    PilotCase("2124966", "글로벌생명경제도시종합계획심의회", 50.0),
    PilotCase("2126659", "가족돌봄아동ㆍ청소년ㆍ청년정책심의위원회", 40.0),
    PilotCase("2216473", "갯벌관리위원회", 32.0),
    PilotCase("2126679", "돌봄근로자처우개선위원회", 60.0),
    PilotCase("2216065", "보호심의위원회", 25.0),
    PilotCase("2217718", "국가인공지능데이터센터진흥전문위원회", 15.6),
)


def _eligible_draft(estimate) -> tuple[bool, str]:
    """Admit a numeric draft only when every borrowed premise is auditable.

    A single merely similar committee is not enough.  We admit either a
    direct institutional precedent or an independently supported paid-member
    cohort paired with a complete, direct formula precedent.
    """
    required = {
        value.key: value
        for value in estimate.variables
        if value.key in {"paid_members", "annual_meetings", "unit_price_won"}
    }
    if set(required) != {"paid_members", "annual_meetings", "unit_price_won"}:
        return False, "계산 변수가 완결되지 않음"
    if any(value.value is None for value in required.values()):
        return False, "계산 변수에 결측값이 있음"
    if all(
        value.provenance in {"law_text", "user_confirmed"}
        for value in required.values()
    ):
        return True, "대상 조문또는 사용자 확인값으로 변수를 확정"

    selected = estimate.selected_candidate
    if selected is None:
        return False, "완결된 산식 선례가 없음"
    scores = selected.scores
    complete_direct_formula = (
        scores.get("formula_completeness", 0) == 3
        and scores.get("direct_provenance", 0) >= 2
    )
    if not complete_direct_formula:
        return False, "산식이 완결된 직접 선례가 아님"

    if scores.get("institutional_identity", 0) >= 2:
        return True, "같은 제도ㆍ기관의 직접 선례"

    paid = required["paid_members"]
    cohort_supported = str(paid.source_id or "").startswith("COHORT:")
    structurally_strong = (
        scores.get("committee_function", 0) >= 2
        and scores.get("profile_evidence", 0) == 3
    )
    if cohort_supported and structurally_strong:
        return True, "독립 선례군이 인원을 뒷받침하고 완결된 직접 산식 선례를 사용"

    # A single precedent can still be usable when the operating mechanism is
    # an exact match and the selected row has complete profile evidence,
    # direct operands, and a solid semantic-recall score.  This admits a
    # genuinely distinctive functional analogue (for example wage/working-
    # condition bargaining) without admitting a merely broad policy body.
    dominant_functional_match = (
        scores.get("committee_function", 0) == 3
        and scores.get("profile_evidence", 0) == 3
        and scores.get("direct_provenance", 0) == 3
        and scores.get("semantic_recall", 0) >= 2
    )
    if dominant_functional_match:
        return True, "작동 방식이 정확히 같고 완결성ㆍ출처가 검증된 우세 선례"

    return False, "유사 비용항목 1건만으로는 대상 의안의 숨은 전제를 확정할 수 없음"


def main() -> None:
    rows: list[dict[str, object]] = []
    for case in CASES:
        source = _pdf(case.bill_no, False)
        if source is None:
            raise SystemExit(f"의안원문 PDF 없음: {case.bill_no}")
        result = estimate_committee_from_pdf(
            source.read_bytes(),
            filename=source.name,
        )
        estimate = next(
            value
            for value in result.estimates
            if case.committee_key.replace("ㆍ", "")
            in value.committee_name.replace("ㆍ", "").replace("·", "")
        )
        eligible, basis = _eligible_draft(estimate)
        draft_million = (
            estimate.gross_draft_annual_thousand * result.years / 1000
            if eligible and estimate.gross_draft_annual_thousand is not None
            else None
        )
        error_pct = (
            round(
                (draft_million - case.official_component_million)
                / case.official_component_million
                * 100,
                2,
            )
            if draft_million is not None
            else None
        )
        rows.append({
            "bill_no": case.bill_no,
            "committee": estimate.committee_name,
            "selection_basis": basis,
            "official_component_million": case.official_component_million,
            "system_component_million": draft_million,
            "error_pct": error_pct,
            "within_20pct": error_pct is not None and abs(error_pct) <= 20,
            "decision": "numeric_draft" if eligible else "human_input_required",
            "selected_precedent_bill": (
                estimate.selected_candidate.bill_no
                if estimate.selected_candidate else None
            ),
            "target_leak": bool(
                estimate.selected_candidate
                and estimate.selected_candidate.bill_no == case.bill_no
            ),
        })

    numeric = [row for row in rows if row["error_pct"] is not None]
    errors = [abs(float(row["error_pct"])) for row in numeric]
    print(json.dumps({
        "evaluation_type": "hierarchical_evidence_gate_pilot",
        "case_count": len(rows),
        "numeric_coverage": round(len(numeric) / len(rows), 3),
        "within_20pct_rate_numeric": round(
            sum(bool(row["within_20pct"]) for row in numeric) / len(numeric),
            3,
        ) if numeric else None,
        "numeric_mape_pct": round(statistics.mean(errors), 2) if errors else None,
        "target_leak_count": sum(bool(row["target_leak"]) for row in rows),
        "rows": rows,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
