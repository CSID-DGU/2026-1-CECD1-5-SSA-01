"""[1] 비용항목 감지 — LLM이 조문 의미를 이해해 비용 유발 항목을 찾는다.

표준산식 템플릿·정규식 라우팅을 쓰지 않는다. LLM이 조문을 읽고
"이 조문이 어떤 비용을 유발하는가"를 의미로 파악해 항목 목록을 만든다.
산식·변수값은 이후 단계(DB 검색 + 선택 + 해결)에서 채운다.
"""
from __future__ import annotations

import json
from typing import Any

from ..analyzer_v2 import gemini_json


_DETECT_PROMPT = """당신은 국회 의안 비용추계 분석가다.
아래 조문들을 읽고, 재정지출(비용)을 유발하는 항목을 모두 찾아라.

원칙:
- 조문의 '의미'를 파악해 비용을 유발하는 실체/행위를 찾는다. 특정 단어에 의존하지 마라.
- 예: 위원회·심의회 설치(회의수당), 사무처·전담조직 설치(인건비), 센터·기관 신설(운영비),
  실태조사·계획수립·연구용역(용역비), 지원금·보조금 지급(지원 소요), 시설·시스템 구축 등.
- 같은 실체가 여러 조문에 걸치면(설치+구성+회의) 하나의 항목으로 묶는다.
- 정의·목적·벌칙 등 독립적 비용이 없는 조문은 제외한다.
- 산식이나 금액은 만들지 마라. '무엇이 비용을 유발하는지'만 식별한다.

각 항목에 대해:
- name: 비용 항목 이름 (예: "○○위원회 운영비", "○○종합계획 수립")
- article_refs: 근거 조문 번호들 (예: ["제7조","제8조"])
- cost_understanding: 이 항목이 왜/어떻게 비용을 유발하는지 한 문장
- cost_kind: 비용 성격을 자유롭게 (예: "회의수당","인건비","연구용역","지원금","운영비","시설구축")

JSON 형식만 출력:
{"items": [{"name":"...","article_refs":["제N조"],"cost_understanding":"...","cost_kind":"..."}]}

조문:
"""


def detect_cost_items(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """조문 목록 → 비용항목 후보 목록(dict). LLM 의미 기반, 표준산식/규칙 미사용."""
    if not articles:
        return []
    blocks = []
    for art in articles:
        no = str(art.get("no") or "")
        text = str(art.get("text") or "")[:1500]
        if not text:
            continue
        blocks.append(f"[{no}]\n{text}")
    corpus = "\n\n".join(blocks)[:28000]
    parsed = gemini_json(_DETECT_PROMPT + corpus, temperature=0.0)
    if not isinstance(parsed, dict):
        return []
    items = parsed.get("items")
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict) or not it.get("name"):
            continue
        refs = it.get("article_refs")
        out.append({
            "name": str(it.get("name")).strip(),
            "article_refs": [str(r) for r in refs] if isinstance(refs, list) else [],
            "cost_understanding": str(it.get("cost_understanding") or "").strip(),
            "cost_kind": str(it.get("cost_kind") or "").strip(),
        })
    return out
