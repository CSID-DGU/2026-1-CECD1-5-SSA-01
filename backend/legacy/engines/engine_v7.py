"""engine_v7 — finale_engine(조문 인식+DB 전체검색)과 인건비 자동계산을 통합.

오늘 밤 흩어져 있던 두 트랙을 하나로 합친다:
  - finale_engine.py: 조문별 인식(배치 없음) + DB 전체 검색 + 중복제거 +
    임계값 필터 (검증됨: 12건→3건, 자기누출 방지, holdout 적용)
  - grade_salary.py: 인건비 직급별 단가표(국가 표준, 검증됨: -14.5%~-1%)

라우팅 규칙(항목 단위, 의안 단위 아님):
  - 매칭된 DB 항목의 category가 "인건비"이고, 순증 인원(직급 구성)이
    HITL로 주어지면 → 자동 계산(보수+기관부담금+기본경비+자산취득비)
  - 그 외 전부 → finale_engine 그대로: 산식 + 확인필요 값만 표시,
    숫자 확정 안 함

"의안을 고르는" 게 아니라 "의안 안의 항목마다" 신뢰 가능한 만큼만
자동화한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.erce_web.estimator_v2.grade_salary import _decomposed_series, normalize_grade_composition
from backend.legacy.engines.finale_engine import FormulaSuggestion, FINALE_ENGINE_VERSION, suggest_formulas

ENGINE_V7_VERSION = "engine-v7-unified-v1"


@dataclass
class ResolvedItem:
    article_ref: str
    description: str
    matched_bill_no: str
    matched_item_name: str
    similarity: float
    status: str  # "computed" 또는 "confirm_needed"
    formula: str
    year_amounts_thousand: list[int] = field(default_factory=list)
    missing_value_names: list[str] = field(default_factory=list)
    note: str = ""


def _is_personnel_item(suggestion: FormulaSuggestion) -> bool:
    return suggestion.matched_category == "인건비"


def _compute_personnel_bundle(
    grade_composition: dict[str, float], *, years: int
) -> dict[str, list[int]]:
    composition = normalize_grade_composition(grade_composition)
    return _decomposed_series(composition, years)


def resolve_bill(
    pdf_bytes: bytes,
    *,
    filename: str = "uploaded.pdf",
    years: int = 5,
    grade_composition: dict[str, float] | None = None,
) -> list[ResolvedItem]:
    suggestions = suggest_formulas(pdf_bytes, filename=filename)
    resolved: list[ResolvedItem] = []
    for suggestion in suggestions:
        if _is_personnel_item(suggestion) and grade_composition:
            series = _compute_personnel_bundle(grade_composition, years=years)
            total_by_year = [
                sum(series[k][y] for k in series) for y in range(years)
            ]
            resolved.append(
                ResolvedItem(
                    article_ref=suggestion.article_ref,
                    description=suggestion.description,
                    matched_bill_no=suggestion.matched_bill_no,
                    matched_item_name=suggestion.matched_item_name,
                    similarity=suggestion.similarity,
                    status="computed",
                    formula="직급별 순증인원(HITL) × 국가 표준 단가 + 기관부담금 + 기본경비 + 자산취득비",
                    year_amounts_thousand=total_by_year,
                    note="인건비 도메인: 순증인원(HITL) 전제로 국가 표준 단가 자동 계산",
                )
            )
            continue
        is_personnel = _is_personnel_item(suggestion)
        missing_values = suggestion.missing_value_names
        if is_personnel and not missing_values:
            missing_values = ["순증인원(직급별)"]
        resolved.append(
            ResolvedItem(
                article_ref=suggestion.article_ref,
                description=suggestion.description,
                matched_bill_no=suggestion.matched_bill_no,
                matched_item_name=suggestion.matched_item_name,
                similarity=suggestion.similarity,
                status="confirm_needed",
                formula=suggestion.formula,
                missing_value_names=missing_values,
                note="인건비로 매칭됐으나 순증인원(HITL) 미제공 — 산식만 제시"
                if is_personnel
                else "",
            )
        )
    return resolved
