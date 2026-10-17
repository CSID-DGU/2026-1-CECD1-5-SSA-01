"""지원금을 유형(shape) 안에서만 검색한다 (격리 모듈, additive).

실측(2126650): 전체 965개에서 검색하니 "보전원 인건비"처럼 완전히 무관한
항목이 걸렸다(유사도 0.61). 위원회가 family로 좁혀서 검색하듯, 지원금도
shape로 먼저 좁히면 후보 풀이 965개 -> 100~270개로 줄어 정확도가 오른다.

방식: 대상 사건의 설명 텍스트에 유형 힌트 키워드가 있으면 그 shape로 검색
범위를 제한한다. 힌트가 없으면 전체에서 검색(기존과 동일, 안전한 fallback).
"""
from __future__ import annotations

import re

from backend.erce_web.estimator import tag_db
from backend.legacy.subsidy.subsidy_shape import classify_subsidy_shape

SUBSIDY_SHAPE_SEARCH_VERSION = "subsidy-shape-search-v1"

_SHAPE_HINT_KEYWORDS = {
    "tax_relief_recent_actual": re.compile(r"감면|세액공제|면제|비과세"),
    "tax_relief_fraction": re.compile(r"감면|세액공제|면제|비과세"),
    "tax_relief_other": re.compile(r"감면|세액공제|면제|비과세|세율|과세"),
    "simple_multiplication": re.compile(r"지급|지원|수당|대상자|보조금"),
}


def _guess_shape_hints(description: str) -> list[str]:
    """설명 텍스트에서 그럴듯한 shape 힌트를 모두 찾는다(복수 가능, 순서 유지)."""
    hints = []
    for shape, pattern in _SHAPE_HINT_KEYWORDS.items():
        if pattern.search(description or ""):
            hints.append(shape)
    return hints


def search_subsidy_by_shape(
    query_vector: list[float],
    description: str,
    *,
    exclude_bill_nos: set[str],
    k: int = 5,
) -> tuple[list[dict], str]:
    """설명에서 유형 힌트를 찾아 그 유형 안에서만 검색. 힌트 없으면 전체 검색.

    반환: (후보 목록, 사용된 범위 설명)
    """
    data = tag_db._load()
    embeddings = tag_db._load_embeddings()
    formulas = tag_db._formula_by_item()

    hints = _guess_shape_hints(description)
    scope = "+".join(hints) if hints else "전체(힌트 없음)"

    scored: list[tuple[float, str]] = []
    for item_id, vector in embeddings.items():
        meta = data["items"].get(item_id, {})
        if meta.get("category") != "지원금":
            continue
        if str(meta.get("bill_no") or "") in exclude_bill_nos:
            continue
        formula = formulas.get(item_id, "")
        if hints and classify_subsidy_shape(formula) not in hints:
            continue
        similarity = tag_db._cosine(query_vector, vector)
        scored.append((similarity, item_id))
    scored.sort(key=lambda value: -value[0])

    results = []
    for similarity, item_id in scored[:k]:
        meta = data["items"].get(item_id, {})
        results.append(
            {
                "bill_no": meta.get("bill_no", ""),
                "item_name": meta.get("name", ""),
                "similarity": round(similarity, 4),
                "formula": formulas.get(item_id, ""),
                "shape": classify_subsidy_shape(formulas.get(item_id, "")),
            }
        )
    return results, scope
