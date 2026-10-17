"""Stable regression scenarios for evidence-first estimator changes.

These are not training targets and their official totals never enter runtime
selection.  They are acceptance gates executed *after* a general change to
detect damage to previously validated behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .types import EstimateResult, RowStatus


REGRESSION_MANIFEST_VERSION = "estimator-v2-regression-v5"


@dataclass(frozen=True)
class FormulaExpectation:
    event_type: str
    object_contains: str
    formula_contains: tuple[str, ...] = ()
    variable_values: tuple[tuple[str, float], ...] = ()
    same_source_roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class RegressionCase:
    bill_no: str
    label: str
    official_million: int
    max_abs_error_pct: float
    organization_net_staff_count: int | None = None
    organization_net_staff_key: str | None = None
    organization_staffing_scenario: str | None = None
    organization_annual_operating_budgets_thousand: dict[str, int] = field(
        default_factory=dict
    )
    committee_variable_inputs: dict[str, dict[str, float]] = field(
        default_factory=dict
    )
    rationale: str = ""
    formula_expectations: tuple[FormulaExpectation, ...] = ()


# Only cases whose current v2 results and required target-specific inputs were
# explicitly verified are pinned here.  Add a case only after its evidence
# chain—not merely its final amount—has been reviewed.
REGRESSION_CASES: tuple[RegressionCase, ...] = (
    RegressionCase(
        bill_no="2214559",
        label="친환경농어업발전위원회 설치·운영",
        official_million=120,
        max_abs_error_pct=20.0,
        rationale=(
            "산식 숫자 앵커링 없이 위원 수·수당·회의횟수를 독립 근거로 "
            "선택하고 복합 TAG 항목의 다른 비용 변수를 배제하는지 확인"
        ),
    ),
    RegressionCase(
        bill_no="2126334",
        label="국립대학병원 발전위원회·주기적 계획",
        official_million=161,
        max_abs_error_pct=20.0,
        rationale="위원회와 5년 주기 계획이 중복 없이 유지되는지 확인",
        formula_expectations=(
            FormulaExpectation(
                event_type="committee_operation",
                object_contains="국립대학병원발전위원회",
                formula_contains=("수당 지급대상 인원", "1인 1회당 수당", "연간 회의 횟수"),
                variable_values=(
                    ("count", 11.0),
                    ("unit_price", 250_000.0),
                    ("frequency", 4.0),
                ),
                same_source_roles=("count", "unit_price", "frequency"),
            ),
            FormulaExpectation(
                event_type="research_plan",
                object_contains="종합계획",
                formula_contains=("대상 조문 5년 주기",),
            ),
        ),
    ),
    RegressionCase(
        bill_no="2213937",
        label="특별지방자치단체 조직 신설",
        official_million=49_811,
        max_abs_error_pct=5.0,
        organization_net_staff_count=60,
        organization_net_staff_key="제4조",
        organization_annual_operating_budgets_thousand={
            "연간 조직 운영경비": 4_000_000,
        },
        rationale="조직 구조값과 대상별 순증인원·운영예산 입력의 분리 확인",
    ),
    RegressionCase(
        bill_no="2213969",
        label="법원 조직 승격·증원",
        official_million=12_094,
        max_abs_error_pct=5.0,
        organization_net_staff_count=28,
        rationale="동일 사법 인사체계의 완결 비용 묶음이 유지되는지 확인",
    ),
    RegressionCase(
        bill_no="2126636",
        label="헌법특별위원회 조직 신설(HITL 순증인원)",
        official_million=8_847,
        max_abs_error_pct=5.0,
        organization_net_staff_count=15,
        rationale=(
            "국회 입법위원회를 일반 자문위원회와 분리하고, 같은 법형식 선례의 "
            "인력비 계열과 인원 독립적인 상임위원회 평균 운영경비를 분리 "
            "이전하는지 확인. 15명은 자동 추정값이 아닌 명시적 HITL 입력"
        ),
    ),
    RegressionCase(
        bill_no="2126655",
        label="공공기관 전담 담당관 지정(HITL 순증인원)",
        official_million=4_356,
        max_abs_error_pct=5.0,
        organization_net_staff_count=8,
        organization_staffing_scenario="new_hires",
        rationale=(
            "기존 직원 중 담당관 지정 조항에서 신규채용을 자동 가정하지 않고, "
            "같은 농수산 공공기관의 완결 인력비 계열을 조건부로 선택하는지 확인. "
            "신규채용 시나리오와 8명은 자동 추정값이 아닌 명시적 HITL 입력"
        ),
    ),
    RegressionCase(
        bill_no="2125736",
        label="공무원보수위원회 조문상 수당대상 계산",
        official_million=55,
        max_abs_error_pct=20.0,
        rationale=(
            "선례의 민간위원 수를 복사하지 않고 조문의 27명 구성에서 "
            "소관업무 관련 공무원 9명을 제외해 지급 가능 18명을 계산한 뒤, "
            "과거 DB에 없던 기존 민관심의위원 10명·실제 수당 35만원·연 4회를 "
            "명시적 HITL 근거로 적용하는지 확인"
        ),
        committee_variable_inputs={
            "공무원보수위원회": {
                "incumbent_paid_members": 10,
                "unit_price_won": 350_000,
                "annual_meetings": 4,
            }
        },
    ),
)


def regression_error_pct(system_million: float, official_million: int) -> float:
    if official_million == 0:
        return 0.0 if system_million == 0 else float("inf")
    return round(
        (float(system_million) - official_million) / official_million * 100,
        2,
    )


def evaluate_regression_case(
    case: RegressionCase,
    *,
    system_million: float,
    target_leak: bool,
    formula_failure_reasons: list[str] | None = None,
) -> dict[str, object]:
    error_pct = regression_error_pct(system_million, case.official_million)
    reasons: list[str] = []
    if target_leak:
        reasons.append("대상 의안 근거 누출")
    if abs(error_pct) > case.max_abs_error_pct:
        reasons.append(
            f"절대오차 {abs(error_pct):.2f}% > 허용 {case.max_abs_error_pct:.2f}%"
        )
    reasons.extend(formula_failure_reasons or [])
    return {
        "bill_no": case.bill_no,
        "label": case.label,
        "official_million": case.official_million,
        "system_million": round(float(system_million), 3),
        "error_pct": error_pct,
        "max_abs_error_pct": case.max_abs_error_pct,
        "target_leak": target_leak,
        "passed": not reasons,
        "failure_reasons": reasons,
        "rationale": case.rationale,
    }


def audit_formula_expectations(
    case: RegressionCase,
    result: EstimateResult,
) -> dict[str, object]:
    """Validate formula structure separately from the aggregate amount."""
    failures: list[str] = []
    checks: list[dict[str, object]] = []
    for expectation in case.formula_expectations:
        matches = [
            row
            for row in result.rows
            if row.event.event_type == expectation.event_type
            and expectation.object_contains in row.event.object
        ]
        check: dict[str, object] = {
            "event_type": expectation.event_type,
            "object_contains": expectation.object_contains,
            "passed": True,
            "reasons": [],
        }
        check_reasons: list[str] = check["reasons"]  # type: ignore[assignment]
        if len(matches) != 1:
            check_reasons.append(
                f"대상 비용행 {len(matches)}건(기대 1건)"
            )
        else:
            row = matches[0]
            if row.status != RowStatus.COMPUTED_REVIEW:
                check_reasons.append(f"계산 상태 {row.status.value}")
            for token in expectation.formula_contains:
                if token not in row.formula:
                    check_reasons.append(f"산식에 '{token}' 없음")
            evidence_by_role = {
                str(evidence.get("role") or ""): evidence
                for evidence in row.variable_evidence
                if evidence.get("role")
            }
            for role, expected_value in expectation.variable_values:
                evidence = evidence_by_role.get(role)
                if evidence is None:
                    check_reasons.append(f"변수 {role} 근거 없음")
                    continue
                try:
                    actual_value = float(evidence.get("value"))
                except (TypeError, ValueError):
                    actual_value = float("nan")
                if actual_value != expected_value:
                    check_reasons.append(
                        f"변수 {role}={actual_value:g}(기대 {expected_value:g})"
                    )
            if expectation.same_source_roles:
                sources = {
                    str(
                        evidence_by_role.get(role, {}).get("source_bill_no")
                        or evidence_by_role.get(role, {}).get("source")
                        or ""
                    )
                    for role in expectation.same_source_roles
                }
                if len(sources) != 1 or "" in sources:
                    check_reasons.append(
                        "산식 변수가 하나의 완결 선례 묶음에서 오지 않음"
                    )
        if check_reasons:
            check["passed"] = False
            failures.extend(
                f"산식 감사({expectation.object_contains}): {reason}"
                for reason in check_reasons
            )
        checks.append(check)
    return {
        "passed": not failures,
        "failure_reasons": failures,
        "checks": checks,
    }
