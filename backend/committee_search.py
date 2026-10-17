"""위원회를 family로 좁혀 검색한다 (격리 모듈, additive).

실측(2214559 친환경농어업발전위원회): 전체 DB(3,346개, 지원금 965개 포함)
에서 검색하면 최고매치가 0.73(임계값 0.80 미달)에 그쳤다. family=="committee"
로 좁히면(396개) 같은 질문에 최고매치가 0.90으로 뛰어오른다 — 가장 적절한
선례(친환경농식품발전위원회, 24명×4회×30만원)가 원래도 있었는데 무관한
카테고리들(지원금 등)에 묻혀 순위가 밀렸던 것이다.

위원회 산식은 거의 항상 A×B×C(민간위원 수 × 회의 횟수 × 사례금 단가)
패턴으로 수렴하므로, subsidy처럼 shape을 더 세분류할 필요 없이 family만
좁혀도 바로 정확도가 오른다.
"""
from __future__ import annotations

import re

from .estimator import tag_db

COMMITTEE_SEARCH_VERSION = "committee-search-v1"

# finale_engine과 달리 "방법론 서술형"(유사사례 준용 등)은 통과시키지
# 않는다. 실측(2214561 탈석탄위원회): "유사사례 준용 추계"(2213471)처럼
# 숫자 분해가 없는 항목이 committee 스코프의 낮은 임계값(0.60)까지 겹쳐서
# 최상위로 올라오면, 재사용 가능한 변수가 하나도 없는 답을 내놓게 된다.
# 위원회는 연구계획과 달리 실제 A×B×C 값이 있을 때만 쓸모가 있으므로,
# 연산자가 명시된 산식만 인정한다(더 엄격).
_FORMULA_OPERATOR = re.compile(r"[×xX*+\-÷/]|Σ")


def _is_decomposed_formula(formula: str) -> bool:
    text = formula or ""
    if not text.strip():
        return False
    return bool(_FORMULA_OPERATOR.search(text))


def search_committee(
    query_vector: list[float],
    *,
    exclude_bill_nos: set[str],
    k: int = 5,
) -> list[dict]:
    """committee family로 좁혀서 검색한다.

    반환: 후보 목록(bill_no, item_name, similarity, formula, variables).
    힌트 없이 항상 committee family로만 본다 — 호출자가 이 조문이 위원회
    관련임을 이미 알고 있을 때만 불러야 한다(finale_engine에서 description에
    "위원회" 등장 여부로 게이트).
    """
    data = tag_db._load()
    embeddings = tag_db._load_embeddings()
    formulas = tag_db._formula_by_item()

    scored: list[tuple[float, str]] = []
    for item_id, vector in embeddings.items():
        meta = data["items"].get(item_id, {})
        if meta.get("family") != "committee":
            continue
        if str(meta.get("bill_no") or "") in exclude_bill_nos:
            continue
        formula = formulas.get(item_id, "")
        if not _is_decomposed_formula(formula):
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
                "category": meta.get("category", ""),
                "family": "committee",
                "similarity": round(similarity, 4),
                "formula": formulas.get(item_id, ""),
                "variables": data["vars"].get(item_id, []),
            }
        )
    return results
