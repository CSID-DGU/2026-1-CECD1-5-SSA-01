"""가장 단순한 3단계 파이프라인: 조문 추출 -> 비용항목화 -> DB 최유사 산식.

복잡한 것(임계값 튜닝, 중복제거, 앙상블, 도메인별 예외) 다 뺐다. 딱 3단계만.
"""
from __future__ import annotations

from backend.erce_web.analyzer_v2 import (
    _call_llm_raw_json,
    split_articles,
    strip_appendices,
    _extract_pdf_text_from_bytes,
    try_embed,
)
from backend.erce_web.estimator import tag_db

_ITEM_PROMPT = """다음 조문을 보고, 비용이 발생하는 조문이면 그 비용항목을
한 문장으로 설명하라. "설치한다·둔다·지급한다·지원한다·증원한다·인원을
늘린다"처럼 사람 수·조직·지급 대상이 늘어나는 조문도 비용 발생으로 본다.
비용 발생 여지가 조금이라도 있으면 설명하고, 확실히 없을 때만 빈 문자열로
답하라(과잉이 누락보다 낫다).

[조문 {ref}]
{text}

JSON: {{"cost_item": "비용 항목 설명 또는 빈 문자열"}}
"""


def run(pdf_bytes: bytes) -> list[dict]:
    # 1) 조문 추출
    raw_text = _extract_pdf_text_from_bytes(pdf_bytes)
    articles, _ = split_articles(strip_appendices(raw_text))

    results = []
    for article in articles:
        ref = str(article.get("no") or "")
        text = str(article.get("text") or "")[:1200]

        # 2) 비용항목으로 만들기
        prompt = _ITEM_PROMPT.format(ref=ref, text=text)
        try:
            parsed = _call_llm_raw_json(prompt, temperature=0.0, timeout=60)
        except Exception:
            continue
        cost_item = str((parsed or {}).get("cost_item") or "").strip()
        if not cost_item:
            continue

        # 3) DB에서 제일 유사한 놈 산식 가져오기
        query_vector = try_embed(cost_item)
        if not query_vector:
            continue
        data = tag_db._load()
        embeddings = tag_db._load_embeddings()
        formulas = tag_db._formula_by_item()
        best_item_id, best_sim = None, -1.0
        for item_id, vector in embeddings.items():
            sim = tag_db._cosine(query_vector, vector)
            if sim > best_sim:
                best_item_id, best_sim = item_id, sim
        if best_item_id is None:
            continue

        meta = data["items"].get(best_item_id, {})
        results.append(
            {
                "조문": ref,
                "비용항목": cost_item,
                "유사도": round(best_sim, 3),
                "매칭_의안": meta.get("bill_no", ""),
                "매칭_항목명": meta.get("name", ""),
                "산식": formulas.get(best_item_id, ""),
            }
        )
    return results
