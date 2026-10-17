"""[4] 변수 해결 — 파이프라인의 핵심 단계.

각 비용항목의 변수를 다음 경로로 채운다:
  · 원문 명시값  → 파싱(결정적)
  · 재사용 상수  → 행정구역 수(시·도 17 / 시·군·구 229) 등
  · 선례 대표값  → representative value
  · 복제(×N)     → replication_factor
  · 외부데이터   → 채울 수 있으면 채우고, 아니면 EXTERNAL_PENDING 플래그

이 파일은 우선 committee_channel에서 검증된 복제(×N) 감지를 이식한다.
(대표값·원문파싱 해결기는 기존 로직을 재사용하며 점진 이식)
"""
from __future__ import annotations

import re
import statistics
from collections import Counter

from .types import Replication, ResolvedVariable, VariableStatus

# 구분자: · (U+00B7), ․ (U+2024), . , ㆍ (U+318D 아래아), ・ (U+30FB)
_SEP = r"[·․.ㆍ・]?"
_REPL_EXPLICIT_RE = re.compile(
    rf"(\d{{1,3}})개(?:의)?(?:광역|지방자치단체|시{_SEP}도|지역|기관|법원|권역|지부)"
)
# 재사용 가능한 행정구역 개수 상수. (좁은 단위=시·군·구를 먼저 검사)
# 오탐 방지: 실체명 매칭 또는 "…에 …둔다/설치" 설치 콜로케이션에서만 인정.
_JURISDICTION_UNITS: list[tuple[re.Pattern[str], re.Pattern[str], int, str]] = [
    (
        re.compile(rf"시{_SEP}군{_SEP}구|기초지방자치단체|기초자치단체|자치구"),
        re.compile(rf"(?:시{_SEP}군{_SEP}구|기초지방자치단체|자치구)[가-힣]{{0,12}}(?:둔다|설치|구성)"),
        229, "시·군·구(기초자치단체 229)",
    ),
    (
        re.compile(rf"시{_SEP}도위원회|시{_SEP}도[가-힣]{{0,6}}위원회|광역지방자치단체|광역자치단체"),
        re.compile(rf"각\s*시{_SEP}도[가-힣]{{0,12}}(?:둔다|설치|구성)|시{_SEP}도별[가-힣]{{0,12}}(?:둔다|설치)|시{_SEP}도마다[가-힣]{{0,12}}(?:둔다|설치)"),
        17, "시·도(광역자치단체 17)",
    ),
]
_REPL_FLAG_RE = re.compile(rf"지역위원회|각지역|각급|권역별")
_OPTIONAL_RE = re.compile(r"둘수있|설치할수있|구성할수있|임의")


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


# ── 변수값 대표값 선택 (DB 선례 후보 → 적절한 값) ──────────────────────────
# committee 채널의 검증된 로직을 유형 무관하게 사용. 값 리스트만 받으므로 범용.

def representative_value(values: list[float], *, prefer_mode: bool = True) -> tuple[float, str]:
    """DB 선례 값 후보에서 방어 가능한 대표값 선택 + 선택 방식 리포트.

    반복값이 곧 관례는 아니다. 최빈값은 (a)3건 이상 (b)유일 (c)2회 이상
    (d)2위 빈도보다 높고 (e)전체의 40% 이상일 때만. 아니면 중앙값(더 견고).
    표준값(수당 단가 등)은 prefer_mode=True, 규모의존값(인원 등)은 비율보정 후 median 권장.
    """
    if not values:
        raise ValueError("대표값 후보가 없습니다.")
    counts = Counter(values)
    top_count = max(counts.values())
    ranked = sorted(counts.values(), reverse=True)
    runner_up = ranked[1] if len(ranked) > 1 else 0
    modes = [v for v, c in counts.items() if c == top_count]
    clear_mode = (
        prefer_mode
        and len(values) >= 3
        and len(modes) == 1
        and top_count >= 2
        and top_count > runner_up
        and top_count / len(values) >= 0.4
    )
    if clear_mode:
        return modes[0], "clear_mode"
    return statistics.median(values), "median"


# 표준값(최빈값 적합) vs 규모의존값(중앙값 적합) DB 키 구분
_STANDARDIZED_KEYS = {
    "committee_allowance_unit", "committee_meeting_count", "employer_contribution_rate",
    "basic_expense_ratio", "asset_acquisition_unit_cost", "consumer_price_growth_rate",
    "public_official_wage_growth_rate", "nominal_wage_growth_rate",
}


def resolve_by_db_key(
    name: str,
    unit: str,
    db_key: str,
    *,
    exclude_bill_nos: set[str] | None = None,
) -> ResolvedVariable:
    """DB assumption 풀에서 db_key로 값 후보를 모아 대표값으로 변수 해결.

    holdout(본인 의안) 제외. 표준값 키는 최빈값, 규모의존 키는 중앙값.
    후보가 없으면 외부데이터/HITL로 표시.
    """
    from ..assembly_assumptions import load_assumption_candidates

    excluded = {str(b) for b in (exclude_bill_nos or set()) if b}
    values: list[float] = []
    for row in load_assumption_candidates():
        if str(row.get("assumption_key")) != db_key:
            continue
        if str(row.get("bill_no") or "") in excluded:
            continue
        v = row.get("value")
        try:
            if v is not None:
                values.append(float(v))
        except (TypeError, ValueError):
            continue
    if not values:
        return ResolvedVariable(name, None, unit, VariableStatus.EXTERNAL_PENDING,
                                basis=f"DB 키 '{db_key}' 후보 없음 → 외부/사용자 확인 필요")
    standardized = db_key in _STANDARDIZED_KEYS
    value, method = representative_value(values, prefer_mode=standardized)
    label = "최빈값" if method == "clear_mode" else "중앙값"
    return ResolvedVariable(
        name, value, unit, VariableStatus.PRECEDENT,
        basis=f"DB '{db_key}' {len(values)}건에서 {label} {value:g} 준용",
        source_ref=db_key,
    )


def resolve_from_precedents(
    name: str,
    unit: str,
    candidates: list[float],
    *,
    standardized: bool,
) -> ResolvedVariable:
    """DB 선례 값 후보로 변수 하나를 해결.

    standardized=True(수당 단가 등 표준값) → 최빈값 우선.
    standardized=False(인원 등 규모의존) → 중앙값(호출측에서 비율보정 후 전달 권장).
    """
    if not candidates:
        return ResolvedVariable(name, None, unit, VariableStatus.EXTERNAL_PENDING,
                                basis="선례 후보가 없어 외부데이터/사용자 확인 필요")
    value, method = representative_value(candidates, prefer_mode=standardized)
    basis = f"DB 선례 {len(candidates)}건에서 {method}({'최빈값' if method=='clear_mode' else '중앙값'})로 선택"
    return ResolvedVariable(name, value, unit, VariableStatus.PRECEDENT, basis=basis)


def replication_factor(text: str, entity: str) -> Replication:
    """복제(×N) 감지. 행정구역 수 상수/명시 개수 적용, 규모 미상이면 ×1 + 확인필요."""
    ent = _compact(entity)
    txt = _compact(text)
    m = _REPL_EXPLICIT_RE.search(ent + txt)
    if m:
        n = int(m.group(1))
        if 1 < n <= 300:
            return Replication(n, f"본문의 '{m.group(0)}' 표현에서 복제 설치 수 {n}개를 적용했습니다.", True)
    optional = bool(_OPTIONAL_RE.search(txt))
    for name_pat, establish_pat, count, label in _JURISDICTION_UNITS:
        if name_pat.search(ent) or establish_pat.search(txt):
            if optional:
                return Replication(1, (
                    f"{label} 단위 복제 정황이나 임의설치('둘 수 있다')라 전수 적용이 부적절합니다. "
                    "실제 설치 수 확인이 필요합니다."
                ), False)
            return Replication(count, (
                f"{label} 단위 의무 복제로 판단해 {count}개를 적용했습니다. "
                "실제 설치 수·지방비 여부 확인이 필요합니다."
            ), False)
    if _REPL_FLAG_RE.search(ent):
        return Replication(1, (
            "지역·기관에 복제 설치되는 정황이 있으나 설치 수가 명시되지 않았습니다. "
            "실제 비용은 표시값 × 설치 수이며 설치 수 확인이 필요합니다."
        ), False)
    return Replication(1, "", True)
