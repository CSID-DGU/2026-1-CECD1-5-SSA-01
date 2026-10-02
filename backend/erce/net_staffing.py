"""Evidence-backed net-staffing scenarios for organization cost estimates.

An earlier bill's *method* may be reused, but its final staff count must not
be copied to a new bill. The resulting total is not a grade distribution:
PERSONNEL_GRADE_V1 still needs grade-specific net staffing evidence.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping


METHODS = (
    {
        "key": "confirmed_plan",
        "label": "확인된 계획 정원 기준",
        "formula": "계획 정원 - 기존 인원 - 전입·재배치 인원",
        "assumption": "대상 조직의 계획 정원이 별도 자료로 확인됨",
        "role": "계획 정원 확인 시 우선 후보",
        "required": ("planned_staff_total", "existing_staff_total", "incoming_staff_total"),
    },
    {
        "key": "parent_population_share",
        "label": "모기관 정원·관할인구 비례",
        "formula": "반올림(모기관 정원 × 대상 관할인구 ÷ 모기관 관할인구) - 기존 인원 - 전입·재배치 인원",
        "assumption": "대상 조직의 인구당 업무·인력 밀도가 모기관과 유사함",
        "role": "모기관과 업무가 유사하면 우선 검토",
        "required": ("parent_staff_total", "target_population", "parent_population",
                     "existing_staff_total", "incoming_staff_total"),
    },
    {
        "key": "population_per_staff",
        "label": "유사기관 1인당 관할인구 기준",
        "formula": "반올림(대상 관할인구 ÷ 공무원 1인당 관할인구) - 기존 인원 - 전입·재배치 인원",
        "assumption": "비교기관의 인구당 업무·인력 밀도를 대상에도 적용할 수 있음",
        "role": "광범위한 비교기관 평균을 쓴 민감도 후보",
        "required": ("target_population", "population_per_staff",
                     "existing_staff_total", "incoming_staff_total"),
    },
    {
        "key": "grade_by_grade",
        "label": "직급별 계획·기존·전입 인원 차감",
        "formula": "직급마다 계획 인원 - 기존 인원 - 전입·재배치 인원",
        "assumption": "동일한 직급 기준의 세 인원표를 확인함",
        "role": "직급별 원자료 확인 시 인건비 계산용",
        "required": ("planned_staff_by_grade", "existing_staff_by_grade",
                     "incoming_staff_by_grade"),
    },
)

_UNITS = {
    "planned_staff_total": "person", "existing_staff_total": "person",
    "incoming_staff_total": "person", "parent_staff_total": "person",
    "target_population": "person", "parent_population": "person",
    "population_per_staff": "person/staff",
    "planned_staff_by_grade": "person/grade",
    "existing_staff_by_grade": "person/grade",
    "incoming_staff_by_grade": "person/grade",
}


def _check_source(key: str, row: Mapping[str, Any], *, cutoff_date: str,
                  target_bill_no: str) -> None:
    if row.get("unit") != _UNITS[key]:
        raise ValueError(f"{key}: 단위는 {_UNITS[key]}여야 합니다.")
    if not str(row.get("source_ref") or "").strip():
        raise ValueError(f"{key}: 근거가 필요합니다.")
    if row.get("available_at"):
        if date.fromisoformat(str(row["available_at"])) > date.fromisoformat(cutoff_date):
            raise ValueError(f"{key}: 기준일 이후의 자료를 사용할 수 없습니다.")
    source_bill = str(row.get("source_bill_no") or "")
    source_kind = str(row.get("source_kind") or "")
    if source_bill and source_bill != target_bill_no and not row.get("available_at"):
        raise ValueError(f"{key}: 선례의 공개일이 필요합니다.")
    if (source_bill and target_bill_no and source_bill == target_bill_no and source_kind not in
            {"bill_text", "target_current_actual"}):
        raise ValueError(f"{key}: 대상 의안의 정답 추계서를 사용할 수 없습니다.")


def _checked_value(key: str, row: Mapping[str, Any], *, cutoff_date: str,
                   target_bill_no: str) -> Decimal | dict[str, int]:
    _check_source(key, row, cutoff_date=cutoff_date, target_bill_no=target_bill_no)
    if key.endswith("_by_grade"):
        raw = row.get("value")
        if not isinstance(raw, Mapping) or not raw:
            raise ValueError(f"{key}: 비어 있지 않은 직급별 인원표가 필요합니다.")
        grade_counts: dict[str, int] = {}
        for grade, count in raw.items():
            if not str(grade).strip() or isinstance(count, bool):
                raise ValueError(f"{key}: 직급과 정수 인원이 필요합니다.")
            try:
                number = Decimal(str(count))
            except (InvalidOperation, TypeError) as exc:
                raise ValueError(f"{key}: 직급별 정수 인원이 필요합니다.") from exc
            if not number.is_finite() or number < 0 or number != number.to_integral_value():
                raise ValueError(f"{key}: 직급별 0 이상의 정수 인원이 필요합니다.")
            grade_counts[str(grade)] = int(number)
        return grade_counts
    try:
        value = Decimal(str(row["value"]))
    except (KeyError, InvalidOperation, TypeError) as exc:
        raise ValueError(f"{key}: 숫자 값이 필요합니다.") from exc
    if not value.is_finite() or value < 0:
        raise ValueError(f"{key}: 0 이상의 유한한 값이어야 합니다.")
    if key.endswith("staff_total") and value != value.to_integral_value():
        raise ValueError(f"{key}: 인원은 정수여야 합니다.")
    if key in {"parent_population", "population_per_staff"} and value == 0:
        raise ValueError(f"{key}: 0으로 나눌 수 없습니다.")
    return value


def net_staffing_scenarios(
    inputs: Mapping[str, Any] | None = None, *, cutoff_date: str = "",
    target_bill_no: str = "",
) -> list[dict[str, Any]]:
    """Return partial or complete candidate methods, never an invented count.

    ``inputs`` contains sourced scalar rows: ``value``, ``unit``, ``source_ref``;
    optional ``available_at``, ``source_bill_no`` and ``source_kind`` enforce
    the blind-test boundary. An incomplete method remains a request for inputs.
    """
    if cutoff_date:
        date.fromisoformat(cutoff_date)
    elif inputs:
        raise ValueError("근거값을 사용할 때 cutoff_date가 필요합니다.")
    raw = dict(inputs or {})
    unknown = set(raw) - set(_UNITS)
    if unknown:
        raise ValueError("지원하지 않는 순증 인원 변수: " + ", ".join(sorted(unknown)))
    numbers: dict[str, Decimal | dict[str, int]] = {}
    for key, row in raw.items():
        if not isinstance(row, Mapping):
            raise ValueError(f"{key}: 값·단위·근거 객체가 필요합니다.")
        numbers[key] = _checked_value(key, row, cutoff_date=cutoff_date,
                                      target_bill_no=target_bill_no)

    scenarios: list[dict[str, Any]] = []
    for method in METHODS:
        required = method["required"]
        missing = [key for key in required if key not in numbers]
        gross: int | None = None
        net_by_grade: dict[str, int] | None = None
        if method["key"] == "confirmed_plan" and "planned_staff_total" in numbers:
            gross = int(numbers["planned_staff_total"])
        elif method["key"] == "parent_population_share" and all(
            key in numbers for key in ("parent_staff_total", "target_population", "parent_population")
        ):
            gross = int((numbers["parent_staff_total"] * numbers["target_population"]
                         / numbers["parent_population"]).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        elif method["key"] == "population_per_staff" and all(
            key in numbers for key in ("target_population", "population_per_staff")
        ):
            gross = int((numbers["target_population"] / numbers["population_per_staff"])
                        .quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        elif method["key"] == "grade_by_grade" and "planned_staff_by_grade" in numbers:
            gross = sum(numbers["planned_staff_by_grade"].values())
        net: int | None = None
        warning = ""
        if method["key"] == "grade_by_grade" and not missing:
            planned = numbers["planned_staff_by_grade"]
            existing = numbers["existing_staff_by_grade"]
            incoming = numbers["incoming_staff_by_grade"]
            grades = set(planned) | set(existing) | set(incoming)
            net_by_grade = {
                grade: planned.get(grade, 0) - existing.get(grade, 0) - incoming.get(grade, 0)
                for grade in sorted(grades)
            }
            if any(count < 0 for count in net_by_grade.values()):
                warning = "어떤 직급은 기존·전입 인원이 계획 인원보다 많습니다. 직급별 대체·승진을 확인해야 합니다."
                net_by_grade = None
            else:
                net = sum(net_by_grade.values())
        elif gross is not None and all(key in numbers for key in
                                     ("existing_staff_total", "incoming_staff_total")):
            net = gross - int(numbers["existing_staff_total"]) - int(numbers["incoming_staff_total"])
            if net < 0:
                warning = "기존·전입 인원이 예상 정원보다 많아 적용 가능성을 다시 확인해야 합니다."
                net = None
        used = [key for key in required if key in raw]
        approximate = [key for key in used if raw[key].get("approximate") is True]
        if approximate and net is not None:
            warning = "근사치 입력이 포함돼 있어 인원 확정 전 검토가 필요합니다."
        scenarios.append({
            "methodKey": method["key"], "label": method["label"],
            "formula": method["formula"], "assumption": method["assumption"],
            "candidateRole": method["role"],
            "status": "needs_review" if warning else (
                "ready_for_salary_calculation" if net_by_grade is not None
                else "ready_for_grade_breakdown" if net is not None else "needs_input"
            ),
            "grossStaff": gross, "netStaff": net, "netStaffByGrade": net_by_grade,
            "missingInputs": missing, "sourceRefs": [str(raw[key]["source_ref"]) for key in used],
            "warning": warning, "approximateInputs": approximate,
            "nextStep": ("직급별 보수 단가를 확인하고 인건비 산식에 반영" if net_by_grade is not None
                         else "직급별 순증 인원 확인 후 인건비 산식에 반영" if net is not None
                         else "부족한 항목의 근거값을 확인"),
        })
    return scenarios


def court_upgrade_precedent_inputs(*, cutoff_date: str,
                                   parent_court: str = "") -> dict[str, dict[str, Any]]:
    """Sourced inputs known before the Anyang bill, not its answer values.

    Goyang 2212273 reports both the 18-court population/staff benchmark and
    Suwon District Court's staffing/population. Parent-court values are only
    offered when the user/AI has identified Suwon as the parent court.
    """
    if date.fromisoformat(cutoff_date) < date(2025, 9, 12):
        return {}
    common = {
        "available_at": "2025-09-12", "source_bill_no": "2212273",
        "source_kind": "earlier_cost_estimate",
    }
    rows: dict[str, dict[str, Any]] = {
        "population_per_staff": {
            "value": 4656, "unit": "person/staff",
            "source_ref": "2212273 비용추계서 25D4478 PDF 3쪽, 18개 지방법원 법원공무원 1명당 평균 관할인구",
            **common,
        },
    }
    if parent_court == "수원지방법원":
        rows.update({
            "parent_staff_total": {
                "value": 1360, "unit": "person",
                "source_ref": "2212273 비용추계서 25D4478 PDF 3쪽, 수원지방법원 법원공무원 정원",
                **common,
            },
            "parent_population": {
                "value": 8804589, "unit": "person",
                "source_ref": "2212273 비용추계서 25D4478 PDF 3쪽, 수원지방법원 관할인구",
                **common,
            },
        })
    return rows
