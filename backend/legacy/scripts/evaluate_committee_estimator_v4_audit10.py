"""Additional ten-bill audit for committee estimator v4.

The official labels below are evaluator-only annotations transcribed from the
calculation sections of the corresponding NABO cost-estimate PDFs.  Runtime
code never imports this module or reads the answer PDFs.

This is an audit set, not a clean research holdout: the bills already existed
in the local corpus, although target-bill evidence is excluded at retrieval
time.  The purpose is to expose structural failures before freezing a new
external holdout.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re

from backend.legacy.committee.committee_estimator_v4 import estimate_committee_from_pdf_v4
from backend.legacy.committee.committee_estimator_v4.pipeline import ENGINE_VERSION
from backend.legacy.scripts.run_estimator_v2 import _pdf


@dataclass(frozen=True)
class OfficialFormulaUnit:
    bill_no: str
    name: str
    family: str
    official_million: float
    horizon_years: int
    required_formula_terms: tuple[str, ...]
    official_formula: str


UNITS = (
    OfficialFormulaUnit(
        "2125736",
        "공무원보수위원회",
        "meeting_allowance",
        55,
        5,
        ("순증수당지급대상", "연간회의횟수", "1인1회당수당"),
        "(신설 위촉위원 18명-현행 위촉위원 10명)×35만원×연 4회",
    ),
    OfficialFormulaUnit(
        "2126635",
        "헌법개정자문위원회",
        "meeting_allowance",
        150,
        5,
        ("수당지급대상", "회의횟수", "수당"),
        "30명×25만원×연 4회",
    ),
    OfficialFormulaUnit(
        "2126635",
        "헌법개정국민참여회의",
        "committee_support_operation",
        6_307,
        5,
        ("본위원회회의비", "지원조직인건비", "기본경비", "사업비", "자산취득비"),
        "500명×25만원×연 1회+지원단 인건비·기관부담금·기본경비·사업비·자산취득비",
    ),
    OfficialFormulaUnit(
        "2126636",
        "헌법특별위원회",
        "staffed_committee_operation",
        8_847,
        5,
        ("인건비", "기본경비", "자산취득비", "사업비"),
        "유사 상임위원회 기반 15명 직급별 인건비·기관부담금·기본경비·자산취득비+사업비",
    ),
    OfficialFormulaUnit(
        "2126661",
        "10ㆍ29이태원참사진상규명과재발방지를위한특별조사위원회",
        "staffed_committee_operation",
        5_882,
        2,
        ("인건비", "기본경비", "자산취득비", "회의비", "사업비", "보고서"),
        "상임위원 인건비·비상임위원 수당+사무처 인건비+자문수당+종합보고서 발간비",
    ),
    OfficialFormulaUnit(
        "2212433",
        "위원후보추천위원회",
        "event_driven_committee",
        200,
        5,
        ("구성건수", "순증유급위원", "회의횟수", "1인1회당수당"),
        "연간 선임 건수×10명×건당 2회×40만원",
    ),
    OfficialFormulaUnit(
        "2213320",
        "국가인공지능데이터센터진흥위원회",
        "meeting_allowance",
        18,
        5,
        ("수당지급대상", "회의횟수", "1인1회당수당"),
        "민간위원 6명×20만원×연 3회",
    ),
    OfficialFormulaUnit(
        "2213937",
        "광주전남특별지방자치단체지원협의회",
        "analog_flat_operating_budget",
        265,
        5,
        ("유사기관", "연간운영예산"),
        "4개 특별자치시·도 지원위원회 2025년 평균 운영비 4,900만원+물가",
    ),
    OfficialFormulaUnit(
        "2214559",
        "친환경농어업발전위원회",
        "meeting_allowance",
        120,
        5,
        ("수당지급대상", "회의횟수", "1인1회당수당"),
        "민간위원 20명×30만원×연 4회",
    ),
    OfficialFormulaUnit(
        "2216417",
        "위원후보추천위원회",
        "event_driven_committee",
        125,
        5,
        ("구성건수", "순증유급위원", "회의횟수", "1인1회당수당"),
        "연도별 구성 건수×7명×건당 3회×40만원",
    ),
    OfficialFormulaUnit(
        "2216503",
        "인권위원후보추천위원회",
        "event_driven_committee",
        155,
        5,
        ("구성건수", "순증유급위원", "회의횟수", "1인1회당수당"),
        "지명주체별 구성 건수×순증 위원 수×건당 3회×40만원",
    ),
)


# These are not merely unpriced official factors.  They are bodies that v4
# incorrectly promoted to independent cost events.
FORBIDDEN_STANDALONE = {
    "2125736": ("심의ㆍ의결하는소위원회",),
    "2126661": ("징계위원회",),
    "2213937": ("분야별전문위원회",),
}


def _key(value: str) -> str:
    return re.sub(r"[ㆍ·・\s]+", "", value or "")


def _matches(expected: str, actual: str) -> bool:
    left = _key(expected)
    right = _key(actual)
    return bool(left and right and (left in right or right in left))


def main() -> None:
    results = {}
    failures: list[dict[str, str]] = []
    for bill_no in dict.fromkeys(unit.bill_no for unit in UNITS):
        source = _pdf(bill_no, False)
        if source is None:
            failures.append({"bill_no": bill_no, "failure": "source_pdf_missing"})
            continue
        try:
            results[bill_no] = estimate_committee_from_pdf_v4(
                source.read_bytes(),
                filename=source.name,
            )
        except Exception as exc:  # evaluation must report, not hide, failures
            failures.append({
                "bill_no": bill_no,
                "failure": f"{type(exc).__name__}: {exc}",
            })

    rows: list[dict[str, object]] = []
    matched_actual_ids: set[tuple[str, int]] = set()
    for unit in UNITS:
        result = results.get(unit.bill_no)
        matched = None
        matched_index = None
        if result is not None:
            for index, estimate in enumerate(result.estimates):
                if _matches(unit.name, estimate.committee_name):
                    matched = estimate
                    matched_index = index
                    break
        if matched is None:
            rows.append({
                **asdict(unit),
                "detected": False,
                "family_match": False,
                "strict_formula_match": False,
                "numeric_draft_million": None,
                "error_pct": None,
            })
            continue

        matched_actual_ids.add((unit.bill_no, int(matched_index)))
        formula_compact = _key(matched.formula_plan.formula)
        family_match = matched.formula_plan.family == unit.family
        strict_formula_match = family_match and all(
            _key(term) in formula_compact
            for term in unit.required_formula_terms
        )
        numeric_million = (
            matched.five_year_amount_thousand / 1000
            if matched.five_year_amount_thousand is not None
            and unit.horizon_years == 5
            else None
        )
        error_pct = (
            round(
                (numeric_million - unit.official_million)
                / unit.official_million
                * 100,
                2,
            )
            if numeric_million is not None and unit.official_million
            else None
        )
        selected = matched.selected_candidate
        rows.append({
            **asdict(unit),
            "detected": True,
            "detected_name": matched.committee_name,
            "detected_family": matched.formula_plan.family,
            "detected_formula": matched.formula_plan.formula,
            "family_match": family_match,
            "strict_formula_match": strict_formula_match,
            "decision": matched.decision,
            "numeric_draft_million": numeric_million,
            "error_pct": error_pct,
            "selected_precedent_bill": selected.bill_no if selected else None,
            "target_leak": bool(selected and selected.bill_no == unit.bill_no),
        })

    false_standalone: list[dict[str, str]] = []
    for bill_no, patterns in FORBIDDEN_STANDALONE.items():
        result = results.get(bill_no)
        if result is None:
            continue
        for estimate in result.estimates:
            if any(_key(pattern) in _key(estimate.committee_name) for pattern in patterns):
                false_standalone.append({
                    "bill_no": bill_no,
                    "detected_name": estimate.committee_name,
                    "family": estimate.formula_plan.family,
                })

    detected = [row for row in rows if row["detected"]]
    numeric = [row for row in rows if row["numeric_draft_million"] is not None]
    payload = {
        "evaluation_type": "v4_additional_ten_bill_formula_audit",
        "engine_version": ENGINE_VERSION,
        "audit_bill_count": len(results),
        "official_formula_unit_count": len(UNITS),
        "detected_count": len(detected),
        "detection_rate": round(len(detected) / len(UNITS), 3),
        "formula_family_match_count": sum(bool(row["family_match"]) for row in rows),
        "formula_family_accuracy": round(
            sum(bool(row["family_match"]) for row in rows) / len(UNITS), 3
        ),
        "strict_formula_match_count": sum(
            bool(row["strict_formula_match"]) for row in rows
        ),
        "strict_formula_accuracy": round(
            sum(bool(row["strict_formula_match"]) for row in rows) / len(UNITS), 3
        ),
        "numeric_draft_count": len(numeric),
        "numeric_coverage": round(len(numeric) / len(UNITS), 3),
        "numeric_within_20pct_count": sum(
            abs(float(row["error_pct"])) <= 20
            for row in numeric
            if row["error_pct"] is not None
        ),
        "false_standalone_event_count": len(false_standalone),
        "target_leak_count": sum(bool(row.get("target_leak")) for row in rows),
        "failures": failures,
        "false_standalone_events": false_standalone,
        "rows": rows,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
