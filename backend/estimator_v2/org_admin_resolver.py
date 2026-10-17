"""Deterministic organization/administration resolver.

The AI-facing boundary is a small structured request: route, cost components,
canonical variables and (optionally) one selected precedent profile per
component.  This module never invents a number and never combines operands
from several precedent profiles.  It either executes a versioned formula or
returns the exact variables that still need evidence/user confirmation.

The sidecar currently contains candidate rows.  Production-safe resolution
therefore requires ``review_status=verified``.  Candidate rows can be enabled
only with the explicit diagnostic flag; the output remains ``computed_review``
and carries a warning reason code.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from backend.config import GENERATED_DIR


RESOLVER_VERSION = "org-admin-resolver-v2"
DEFAULT_SIDECAR_DIR = GENERATED_DIR / "org_admin_sidecar_v1"


@dataclass(frozen=True)
class FormulaDefinition:
    key: str
    route: str
    component: str
    label: str
    expression: str
    required: tuple[str, ...]
    optional: tuple[str, ...] = ()
    recurrence: str = "annual"


FORMULAS: dict[str, FormulaDefinition] = {
    formula.key: formula
    for formula in (
        FormulaDefinition(
            "ORG_PERSONNEL_GRADE_V1",
            "organization",
            "personnel",
            "직급별 보수",
            "Σ(직급별 순증인원 × 직급별 1인당 보수)",
            ("headcount_by_grade", "salary_by_grade"),
            ("wage_growth_rate",),
        ),
        FormulaDefinition(
            "ORG_PERSONNEL_AVERAGE_V1",
            "organization",
            "personnel",
            "평균단가 보수",
            "순증인원 × 1인당 연간 보수",
            ("headcount", "salary_per_person"),
            ("wage_growth_rate",),
        ),
        FormulaDefinition(
            "ORG_EMPLOYER_CONTRIBUTION_V1",
            "organization",
            "employer_contribution",
            "기관부담금",
            "보수총액 × 기관부담률",
            ("total_salary", "employer_contribution_rate"),
        ),
        FormulaDefinition(
            "ORG_BASIC_EXPENSE_RATIO_V1",
            "organization",
            "basic_expense",
            "인건비 비율형 기본경비",
            "보수총액 × 기본경비비율",
            ("total_salary", "basic_expense_ratio"),
            ("price_growth_rate",),
        ),
        FormulaDefinition(
            "ORG_BASIC_EXPENSE_PER_PERSON_V1",
            "organization",
            "basic_expense",
            "1인당 기본경비",
            "순증인원 × 1인당 기본경비",
            ("headcount", "basic_expense_per_person"),
            ("price_growth_rate",),
        ),
        FormulaDefinition(
            "ORG_ASSET_PER_PERSON_V1",
            "organization",
            "asset",
            "1인당 자산취득비",
            "순증인원 × 1인당 자산취득비",
            ("headcount", "asset_unit_price_per_person"),
            recurrence="one_time",
        ),
        FormulaDefinition(
            "ORG_OPERATING_DIRECT_V1",
            "organization",
            "operating_expense",
            "조직 연간 운영비",
            "대상 조직의 연간 운영비",
            ("annual_operating_amount",),
            ("price_growth_rate",),
        ),
        FormulaDefinition(
            "COMMITTEE_MEETING_V1",
            "committee",
            "committee_meeting",
            "위원회 회의수당",
            "수당지급 위원 수 × 연간 회의횟수 × 1인 1회당 수당",
            ("paid_member_count", "annual_meetings", "meeting_unit_price"),
        ),
        FormulaDefinition(
            "COMMITTEE_MULTI_INSTANCE_V1",
            "committee",
            "committee_meeting",
            "복수 위원회 회의수당",
            "위원회 설치 개수 × 수당지급 위원 수 × 연간 회의횟수 × 1인 1회당 수당",
            (
                "committee_instance_count",
                "paid_member_count",
                "annual_meetings",
                "meeting_unit_price",
            ),
        ),
        FormulaDefinition(
            "COMMITTEE_OPERATING_DIRECT_V1",
            "committee",
            "committee_operation",
            "위원회 연간 운영비",
            "대상 위원회의 연간 운영비",
            ("committee_operating_amount",),
            ("price_growth_rate",),
        ),
    )
}


@dataclass(frozen=True)
class CanonicalInput:
    value: Any
    unit: str
    source: str
    source_ref: str = ""
    evidence_keys: tuple[str, ...] = ()


@dataclass
class OrgAdminPlanRequest:
    route: str
    components: tuple[str, ...]
    years: int = 5
    inputs: dict[str, CanonicalInput] = field(default_factory=dict)
    selected_profile_keys: dict[str, str] = field(default_factory=dict)
    context_gates_passed: bool = False
    diagnostic_allow_candidate_evidence: bool = False
    effective_year_offset: int = 0
    # Appended after the original positional fields for backwards
    # compatibility with callers that passed ``years`` positionally.
    target_bill_no: str = ""
    target_bill_id: str = ""
    cutoff_date: str = ""


@dataclass
class ComponentResolution:
    component: str
    status: str
    formula_key: str
    formula: str
    annual_amounts_thousand: list[int | None]
    resolved_inputs: dict[str, CanonicalInput] = field(default_factory=dict)
    missing_variables: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    selected_profile_key: str = ""
    selected_source_item_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OrgAdminPlanResolution:
    status: str
    resolver_version: str
    rows: list[ComponentResolution]
    year_totals_thousand: list[int]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_COMPONENT_ORDER = {
    "personnel": 10,
    "employer_contribution": 20,
    "basic_expense": 30,
    "asset": 40,
    "committee_meeting": 50,
    "committee_operation": 60,
    "operating_expense": 70,
}
_PROFILE_COMPONENTS = {
    "committee_meeting": {"committee_meeting", "committee_operation"},
    "committee_operation": {"committee_operation", "committee_meeting"},
}
_EXPECTED_UNITS = {
    "headcount": {"person"},
    "headcount_by_grade": {"person_by_grade"},
    "salary_by_grade": {"KRW/person/year", "KRW/person/year_by_grade"},
    "salary_per_person": {"KRW/person/year"},
    "total_salary": {"KRW/year"},
    "employer_contribution_rate": {"ratio"},
    "wage_growth_rate": {"ratio", "ratio/year"},
    "basic_expense_ratio": {"ratio"},
    "basic_expense_per_person": {"KRW/person/year"},
    "asset_unit_price_per_person": {"KRW/person"},
    "paid_member_count": {"person"},
    "committee_instance_count": {"instance"},
    "annual_meetings": {"meeting/year"},
    "meeting_unit_price": {"KRW/person/meeting"},
    "committee_operating_amount": {"KRW/year"},
    "annual_operating_amount": {"KRW/year"},
    "price_growth_rate": {"ratio", "ratio/year"},
}
_TARGET_INPUT_KEYS = {
    "headcount",
    "headcount_by_grade",
    "committee_instance_count",
    "annual_operating_amount",
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_sidecar(
    sidecar_dir: Path = DEFAULT_SIDECAR_DIR,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return (
        _read_jsonl(sidecar_dir / "item_profiles.jsonl"),
        _read_jsonl(sidecar_dir / "variable_evidence.jsonl"),
    )


def _coerce_input(value: CanonicalInput | Mapping[str, Any]) -> CanonicalInput:
    if isinstance(value, CanonicalInput):
        return value
    return CanonicalInput(
        value=value.get("value"),
        unit=str(value.get("unit") or ""),
        source=str(value.get("source") or ""),
        source_ref=str(value.get("source_ref") or ""),
        evidence_keys=tuple(str(key) for key in value.get("evidence_keys") or ()),
    )


def request_from_dict(payload: Mapping[str, Any]) -> OrgAdminPlanRequest:
    return OrgAdminPlanRequest(
        route=str(payload.get("route") or ""),
        components=tuple(str(value) for value in payload.get("components") or ()),
        target_bill_no=str(payload.get("target_bill_no") or ""),
        target_bill_id=str(payload.get("target_bill_id") or ""),
        cutoff_date=str(payload.get("cutoff_date") or ""),
        years=int(payload.get("years") or 5),
        inputs={
            str(key): _coerce_input(value)
            for key, value in dict(payload.get("inputs") or {}).items()
        },
        selected_profile_keys={
            str(key): str(value)
            for key, value in dict(payload.get("selected_profile_keys") or {}).items()
        },
        context_gates_passed=bool(payload.get("context_gates_passed")),
        diagnostic_allow_candidate_evidence=bool(
            payload.get("diagnostic_allow_candidate_evidence")
        ),
        effective_year_offset=int(payload.get("effective_year_offset") or 0),
    )


def _profile_inputs(
    *,
    component: str,
    profile_key: str,
    profiles: Iterable[dict[str, Any]],
    evidence: Iterable[dict[str, Any]],
    target_bill_no: str,
    target_bill_id: str,
    cutoff_date: str,
    context_gates_passed: bool,
    diagnostic_allow_candidate_evidence: bool,
) -> tuple[dict[str, CanonicalInput], list[str], str]:
    profile = next(
        (row for row in profiles if str(row.get("profile_key")) == profile_key),
        None,
    )
    if profile is None:
        return {}, ["SELECTED_PROFILE_NOT_FOUND"], ""
    source_item_key = str(profile.get("source_item_key") or "")
    attributes = dict(profile.get("raw_attributes") or {})
    profile_bill_no = str(
        profile.get("bill_no") or attributes.get("bill_no") or ""
    )
    profile_bill_id = str(profile.get("bill_id") or "")
    propose_date = str(
        profile.get("propose_date") or attributes.get("propose_date") or ""
    )
    if (
        target_bill_no
        and profile_bill_no
        and profile_bill_no == target_bill_no
    ) or (
        target_bill_id
        and profile_bill_id
        and profile_bill_id == target_bill_id
    ):
        return {}, ["TARGET_PROFILE_EXCLUDED"], source_item_key
    if cutoff_date:
        if not propose_date:
            return {}, ["PROFILE_DATE_UNKNOWN"], source_item_key
        if propose_date > cutoff_date:
            return {}, ["FUTURE_PROFILE_EXCLUDED"], source_item_key
    compatible = _PROFILE_COMPONENTS.get(component, {component})
    if str(profile.get("component")) not in compatible:
        return {}, ["SELECTED_PROFILE_COMPONENT_MISMATCH"], source_item_key

    grouped: dict[str, list[dict[str, Any]]] = {}
    rejected_for_review = False
    rejected_for_context = False
    for row in evidence:
        if str(row.get("profile_key")) != profile_key:
            continue
        key = str(row.get("canonical_key") or "")
        if not key or row.get("normalized_value") is None:
            continue
        if row.get("unit_status") != "normalized":
            continue
        review_status = str(row.get("review_status") or "candidate")
        policy = str(row.get("transfer_policy") or "review_required")
        if review_status != "verified" and not diagnostic_allow_candidate_evidence:
            rejected_for_review = True
            continue
        if policy in {"target_specific", "do_not_transfer"}:
            continue
        if policy in {"comparable_only", "scope_check_required"} and not context_gates_passed:
            rejected_for_context = True
            continue
        if policy == "review_required" and not (
            diagnostic_allow_candidate_evidence and context_gates_passed
        ):
            rejected_for_review = True
            continue
        grouped.setdefault(key, []).append(row)

    result: dict[str, CanonicalInput] = {}
    for key, rows in grouped.items():
        units = {str(row.get("normalized_unit") or "") for row in rows}
        if len(units) != 1 or "" in units:
            continue
        if key == "committee_instance_count":
            value: Any = sum(float(row["normalized_value"]) for row in rows)
        else:
            distinct = {float(row["normalized_value"]) for row in rows}
            if len(distinct) != 1:
                continue
            value = next(iter(distinct))
        result[key] = CanonicalInput(
            value=value,
            unit=next(iter(units)),
            source=(
                "sidecar_candidate_diagnostic"
                if any(str(row.get("review_status")) != "verified" for row in rows)
                else "verified_precedent"
            ),
            source_ref=str(profile.get("source_item_key") or ""),
            evidence_keys=tuple(str(row.get("evidence_key") or "") for row in rows),
        )

    reason_codes: list[str] = []
    if rejected_for_review:
        reason_codes.append("UNVERIFIED_EVIDENCE_REJECTED")
    if rejected_for_context:
        reason_codes.append("CONTEXT_GATES_REQUIRED")
    if any(value.source == "sidecar_candidate_diagnostic" for value in result.values()):
        reason_codes.append("UNVERIFIED_EVIDENCE_USED_DIAGNOSTIC")
    return result, reason_codes, source_item_key


def _select_formula(
    route: str,
    component: str,
    values: Mapping[str, CanonicalInput],
) -> FormulaDefinition | None:
    if route == "organization" and component == "personnel":
        if {"headcount_by_grade", "salary_by_grade"} <= values.keys():
            return FORMULAS["ORG_PERSONNEL_GRADE_V1"]
        return FORMULAS["ORG_PERSONNEL_AVERAGE_V1"]
    if route == "organization" and component == "employer_contribution":
        return FORMULAS["ORG_EMPLOYER_CONTRIBUTION_V1"]
    if route == "organization" and component == "basic_expense":
        if "total_salary" in values and "basic_expense_ratio" in values:
            return FORMULAS["ORG_BASIC_EXPENSE_RATIO_V1"]
        return FORMULAS["ORG_BASIC_EXPENSE_PER_PERSON_V1"]
    if route == "organization" and component == "asset":
        return FORMULAS["ORG_ASSET_PER_PERSON_V1"]
    if route == "organization" and component == "operating_expense":
        return FORMULAS["ORG_OPERATING_DIRECT_V1"]
    if route == "committee" and component == "committee_meeting":
        if "committee_instance_count" in values:
            return FORMULAS["COMMITTEE_MULTI_INSTANCE_V1"]
        return FORMULAS["COMMITTEE_MEETING_V1"]
    if route == "committee" and component == "committee_operation":
        return FORMULAS["COMMITTEE_OPERATING_DIRECT_V1"]
    return None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _valid_input(key: str, value: CanonicalInput) -> bool:
    if value.unit not in _EXPECTED_UNITS.get(key, {value.unit}):
        return False
    if key in {"headcount_by_grade", "salary_by_grade"}:
        return isinstance(value.value, Mapping) and bool(value.value)
    if key == "total_salary" and isinstance(value.value, list):
        return bool(value.value) and all(_is_number(item) and item >= 0 for item in value.value)
    if not _is_number(value.value):
        return False
    if key.endswith("_rate") or key.endswith("_ratio"):
        return 0 <= float(value.value) <= 1
    return float(value.value) >= 0


def _rate(values: Mapping[str, CanonicalInput], key: str) -> float:
    value = values.get(key)
    return float(value.value) if value and _valid_input(key, value) else 0.0


def _annual_series(value: CanonicalInput, years: int, growth: float = 0.0) -> list[float]:
    if isinstance(value.value, list):
        if len(value.value) != years:
            raise ValueError("annual series length does not match estimate years")
        return [float(item) for item in value.value]
    base = float(value.value)
    return [base * ((1.0 + growth) ** year) for year in range(years)]


def _execute_formula(
    formula: FormulaDefinition,
    values: Mapping[str, CanonicalInput],
    *,
    years: int,
    effective_year_offset: int,
) -> list[float]:
    key = formula.key
    if key == "ORG_PERSONNEL_GRADE_V1":
        counts = values["headcount_by_grade"].value
        salaries = values["salary_by_grade"].value
        if not isinstance(counts, Mapping) or not isinstance(salaries, Mapping):
            raise ValueError("grade inputs must be mappings")
        missing_grades = set(counts) - set(salaries)
        if missing_grades:
            raise ValueError(f"missing salary grades: {sorted(missing_grades)}")
        base = sum(float(count) * float(salaries[grade]) for grade, count in counts.items())
        growth = _rate(values, "wage_growth_rate")
        return [base * ((1.0 + growth) ** year) for year in range(years)]
    if key == "ORG_PERSONNEL_AVERAGE_V1":
        base = float(values["headcount"].value) * float(values["salary_per_person"].value)
        growth = _rate(values, "wage_growth_rate")
        return [base * ((1.0 + growth) ** year) for year in range(years)]
    if key == "ORG_EMPLOYER_CONTRIBUTION_V1":
        salary = _annual_series(values["total_salary"], years)
        rate = float(values["employer_contribution_rate"].value)
        return [amount * rate for amount in salary]
    if key == "ORG_BASIC_EXPENSE_RATIO_V1":
        salary = _annual_series(values["total_salary"], years)
        ratio = float(values["basic_expense_ratio"].value)
        return [amount * ratio for amount in salary]
    if key == "ORG_BASIC_EXPENSE_PER_PERSON_V1":
        base = float(values["headcount"].value) * float(
            values["basic_expense_per_person"].value
        )
        growth = _rate(values, "price_growth_rate")
        return [base * ((1.0 + growth) ** year) for year in range(years)]
    if key == "ORG_ASSET_PER_PERSON_V1":
        result = [0.0] * years
        if 0 <= effective_year_offset < years:
            result[effective_year_offset] = float(values["headcount"].value) * float(
                values["asset_unit_price_per_person"].value
            )
        return result
    if key in {"COMMITTEE_MEETING_V1", "COMMITTEE_MULTI_INSTANCE_V1"}:
        amount = (
            float(values["paid_member_count"].value)
            * float(values["annual_meetings"].value)
            * float(values["meeting_unit_price"].value)
        )
        if key == "COMMITTEE_MULTI_INSTANCE_V1":
            amount *= float(values["committee_instance_count"].value)
        return [amount] * years
    if key in {"ORG_OPERATING_DIRECT_V1", "COMMITTEE_OPERATING_DIRECT_V1"}:
        amount_key = (
            "annual_operating_amount"
            if key == "ORG_OPERATING_DIRECT_V1"
            else "committee_operating_amount"
        )
        growth = _rate(values, "price_growth_rate")
        return _annual_series(values[amount_key], years, growth)
    raise ValueError(f"formula executor missing: {key}")


def resolve_org_admin_plan(
    request: OrgAdminPlanRequest,
    *,
    profiles: Iterable[dict[str, Any]] = (),
    evidence: Iterable[dict[str, Any]] = (),
) -> OrgAdminPlanResolution:
    if request.route not in {"organization", "committee"}:
        raise ValueError("route must be organization or committee")
    if not 1 <= request.years <= 10:
        raise ValueError("years must be between 1 and 10")
    if not request.components:
        raise ValueError("at least one component is required")

    profile_rows = list(profiles)
    evidence_rows = list(evidence)
    shared = {key: _coerce_input(value) for key, value in request.inputs.items()}
    rows: list[ComponentResolution] = []
    warnings: list[str] = []
    components = sorted(dict.fromkeys(request.components), key=lambda value: _COMPONENT_ORDER.get(value, 999))

    for component in components:
        values = dict(shared)
        profile_key = request.selected_profile_keys.get(component, "")
        source_item_key = ""
        reason_codes: list[str] = []
        if profile_key:
            profile_values, profile_codes, source_item_key = _profile_inputs(
                component=component,
                profile_key=profile_key,
                profiles=profile_rows,
                evidence=evidence_rows,
                target_bill_no=request.target_bill_no,
                target_bill_id=request.target_bill_id,
                cutoff_date=request.cutoff_date,
                context_gates_passed=request.context_gates_passed,
                diagnostic_allow_candidate_evidence=(
                    request.diagnostic_allow_candidate_evidence
                ),
            )
            # Target-law, current-standard and user-confirmed values always win.
            values = {**profile_values, **values}
            reason_codes.extend(profile_codes)

        formula = _select_formula(request.route, component, values)
        if formula is None:
            rows.append(
                ComponentResolution(
                    component=component,
                    status="excluded",
                    formula_key="",
                    formula="",
                    annual_amounts_thousand=[None] * request.years,
                    reason_codes=["UNSUPPORTED_ROUTE_COMPONENT"],
                    selected_profile_key=profile_key,
                    selected_source_item_key=source_item_key,
                )
            )
            continue

        invalid = [
            key
            for key in formula.required
            if key in values and not _valid_input(key, values[key])
        ]
        missing = [key for key in formula.required if key not in values or key in invalid]
        if missing:
            reason_codes.extend(f"INVALID_OR_MISSING_VARIABLE:{key}" for key in missing)
            status = (
                "needs_user_input"
                if any(key in _TARGET_INPUT_KEYS for key in missing)
                else "needs_evidence"
            )
            rows.append(
                ComponentResolution(
                    component=component,
                    status=status,
                    formula_key=formula.key,
                    formula=formula.expression,
                    annual_amounts_thousand=[None] * request.years,
                    resolved_inputs={
                        key: value for key, value in values.items() if key in formula.required + formula.optional
                    },
                    missing_variables=missing,
                    reason_codes=reason_codes,
                    selected_profile_key=profile_key,
                    selected_source_item_key=source_item_key,
                )
            )
            continue

        used = {
            key: values[key]
            for key in formula.required + formula.optional
            if key in values and _valid_input(key, values[key])
        }
        try:
            annual_won = _execute_formula(
                formula,
                used,
                years=request.years,
                effective_year_offset=request.effective_year_offset,
            )
        except ValueError as exc:
            rows.append(
                ComponentResolution(
                    component=component,
                    status="needs_evidence",
                    formula_key=formula.key,
                    formula=formula.expression,
                    annual_amounts_thousand=[None] * request.years,
                    resolved_inputs=used,
                    missing_variables=list(formula.required),
                    reason_codes=[*reason_codes, f"FORMULA_INPUT_ERROR:{exc}"],
                    selected_profile_key=profile_key,
                    selected_source_item_key=source_item_key,
                )
            )
            continue
        amounts_thousand = [int(round(amount / 1_000.0)) for amount in annual_won]
        rows.append(
            ComponentResolution(
                component=component,
                status="computed_review",
                formula_key=formula.key,
                formula=formula.expression,
                annual_amounts_thousand=amounts_thousand,
                resolved_inputs=used,
                reason_codes=reason_codes,
                selected_profile_key=profile_key,
                selected_source_item_key=source_item_key,
            )
        )
        if component == "personnel":
            shared["total_salary"] = CanonicalInput(
                value=annual_won,
                unit="KRW/year",
                source="derived",
                source_ref=formula.key,
            )

    totals = [0] * request.years
    for row in rows:
        for index, amount in enumerate(row.annual_amounts_thousand):
            totals[index] += amount or 0
    incomplete = any(row.status != "computed_review" for row in rows)
    if any("UNVERIFIED_EVIDENCE_USED_DIAGNOSTIC" in row.reason_codes for row in rows):
        warnings.append(
            "검수되지 않은 sidecar 근거를 진단 모드로 사용했습니다. 운영 자동확정 결과가 아닙니다."
        )
    return OrgAdminPlanResolution(
        status="partial" if incomplete else "computed_review",
        resolver_version=RESOLVER_VERSION,
        rows=rows,
        year_totals_thousand=totals,
        warnings=warnings,
    )


__all__ = [
    "CanonicalInput",
    "ComponentResolution",
    "FORMULAS",
    "FormulaDefinition",
    "OrgAdminPlanRequest",
    "OrgAdminPlanResolution",
    "load_sidecar",
    "request_from_dict",
    "resolve_org_admin_plan",
]
