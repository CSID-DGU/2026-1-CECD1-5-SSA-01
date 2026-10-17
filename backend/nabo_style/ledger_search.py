"""Everyday-language search over the 기준정보 원장 ("우리나라 인구" → 주민등록인구).

Two layers:
1. scored search (free, instant): stop-words dropped, synonyms expanded, every row scored by
   term hits (name weighs most) plus character-bigram overlap, so partial wording still ranks;
2. ask_ai(): only when the user asks — the model rewrites the question into ledger terms,
   then the same scored search runs. The model never returns a value itself.
"""
from __future__ import annotations

import json
import re
import time
from functools import lru_cache

from backend.nabo_style import ledger
from backend.nabo_style.display import clean_name

STOP = {"우리나라", "한국", "대한민국의", "몇", "몇명", "명", "얼마", "얼마나", "수", "의", "은", "는", "이", "가",
        "현재", "요즘", "최근", "알려줘", "찾아줘", "검색", "자료", "통계", "기준", "총"}
SYNONYMS = {
    "인구": ["주민등록인구", "인구"],
    "우리나라": ["주민등록인구", "전국"], "전국민": ["주민등록인구"], "국민": ["주민등록인구", "내국인"],
    "노인": ["65세", "노인"], "어르신": ["65세", "노인"], "고령자": ["65세"],
    "아이": ["아동", "0~"], "아동": ["아동"], "청년": ["청년", "19~34세", "39세"],
    "외국인": ["외국인", "체류"], "이민자": ["결혼이민", "외국인"], "영주권": ["영주"],
    "최저시급": ["최저임금"], "시급": ["최저임금", "시급"], "월급": ["봉급", "임금"], "공무원": ["공무원", "봉급"],
    "중위소득": ["기준 중위소득"], "기초연금": ["기초연금"], "물가": ["소비자물가"], "죄수": ["교정시설"],
    "수감자": ["교정시설"], "교도소": ["교정시설"], "농민": ["농가", "농업인"], "어민": ["어가", "어업인"],
    "장애인": ["장애인"], "분담": ["재원분담", "국고보조율", "분담"], "국비": ["국고보조율", "재원분담"],
}
OFFICIAL = ("공식", "법령", "통계")
PEOPLE_WORDS = {"인구", "인원", "수", "명", "몇명", "수급자", "대상자", "수감자", "죄수", "외국인", "노인", "어르신",
                "아동", "아이", "청년", "농민", "어민", "장애인", "이민자"}
PEOPLE_UNITS = ("명", "person", "인", "가구", "household")
MONEY_UNITS = ("원", "KRW", "%", "ratio")


def _bigrams(text: str) -> set[str]:
    t = re.sub(r"\s+", "", text)
    return {t[i:i + 2] for i in range(len(t) - 1)}


@lru_cache(maxsize=1)
def _index() -> tuple[tuple[dict, str, str, frozenset], ...]:
    out = []
    for r in ledger.all_rows():
        if r["id"].startswith("erce:salary:"):  # 수천 행의 봉급표는 '봉급' 검색에서만
            name = f"{r['name']} 봉급"
        else:
            name = r["name"]
        body = f"{r['id']} {r.get('category', '')} {r['document']} {r.get('note', '')} {r.get('publisher', '')}"
        out.append((r, name, body, frozenset(_bigrams(name))))
    return tuple(out)


def expand(query: str) -> tuple[list[str], list[str]]:
    words = [w for w in re.split(r"[\s,·/]+", query.strip()) if w]
    core = [w for w in words if w not in STOP]
    extra = [s for w in words for s in SYNONYMS.get(w, [])]
    return core, [e for e in dict.fromkeys(extra) if e not in core]


def search(query: str, cutoff: str, *, limit: int = 20, exclude_bill: str | None = None) -> tuple[list[dict], dict]:
    core, extra = expand(query)
    if not core and not extra:
        return [], dict(core=[], extra=[])
    qgrams = _bigrams("".join(core))
    people = any(w in PEOPLE_WORDS for w in re.split(r"[\s,·/]+", query))
    scored = []
    for r, name, body, grams in _index():
        if r["published_at"] > cutoff or (exclude_bill and r.get("source_bill") == exclude_bill):
            continue
        score = 0.0
        for t in core:
            score += 5 if t in name else 2 if t in body else 0
        for t in extra:
            score += 3.5 if t in name else 1 if t in body else 0
        if qgrams:
            score += 4 * len(qgrams & grams) / len(qgrams)
        if score >= 3:
            official = any(w in (r.get("grade") or "") for w in OFFICIAL)
            curated = ":" not in r["id"].split(":", 1)[0] and not r["id"].startswith(("erce:", "nabo_support:"))
            unit = r.get("unit") or ""
            if people:
                score += 2 if any(u in unit for u in PEOPLE_UNITS) else -3 if any(u in unit for u in MONEY_UNITS) else 0
            scored.append((score + (1.5 if official else 0) + (3 if curated else 0), r["published_at"], r))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    seen, rows = set(), []
    for _s, _p, r in scored:
        key = (clean_name(r["name"]), str(r["value"])[:60])
        if key in seen:
            continue
        seen.add(key)
        rows.append(r)
        if len(rows) >= limit:
            break
    return rows, dict(core=core, extra=extra)


def ask_ai(question: str, cutoff: str, *, limit: int = 20) -> tuple[list[dict], dict]:
    from backend.nabo_style.ai_pipeline import gpt
    schema = {"type": "object", "additionalProperties": False, "required": ["keywords", "why"],
              "properties": {"keywords": {"type": "array", "items": {"type": "string"}}, "why": {"type": "string"}}}
    prompt = ("아래 질문에 답할 통계를 비용추계용 기준정보 원장에서 찾으려 합니다. 원장 행 이름은 "
              "'주민등록인구(내국인)', '65세 이상 인구', '장기체류 외국인', '최저임금 시급', '기준 중위소득(월)', "
              "'교정시설 1일 평균 수용인원', '국고보조율'처럼 공식 통계 용어입니다. 질문을 이런 공식 용어 검색어 2~5개로 "
              "바꾸세요(각 2~10자). 숫자는 만들지 마세요. why에는 어떻게 해석했는지 한 문장.\n질문: " + question)
    plan, _info = gpt("ledger_query", prompt, schema)
    merged, seen = [], set()
    for k in plan["keywords"]:
        for r in search(k, cutoff, limit=8)[0]:
            if r["id"] not in seen:
                seen.add(r["id"])
                merged.append(r)
    return merged[:limit], dict(core=plan["keywords"], extra=[], why=plan["why"])


WEB_PROMPT = """비용추계 기준정보로 쓸 공식 통계를 웹에서 찾아 주세요.

규칙
- {cutoff} 이전에 공표된 자료만(published_at YYYY-MM-DD). 공표일을 모르면 제외.
- 통계청(KOSIS)·정부부처·공공기관 자료를 우선하고, 언론보도는 공식 자료가 없을 때만 씁니다.
- 질문의 대상과 가장 가까운 통계 1~3개. 서로 다른 해석(예: 농가 수 vs 농업인 수)이면 각각 하나씩.
- value는 원문에 적힌 숫자 그대로(단위 환산 금지), unit은 원문 단위.
- url은 숫자가 실제로 적힌 페이지/PDF, quote는 그 숫자를 포함한 원문 문장을 그대로 복사.
- name은 짧은 통계 이름(예: '40세 미만 농업경영체 등록 농업인 수').

질문: {q}"""

WEB_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["hits"], "properties": {"hits": {
    "type": "array", "items": {"type": "object", "additionalProperties": False,
                               "required": ["name", "value", "unit", "url", "quote", "publisher", "document",
                                            "as_of", "published_at", "why"],
                               "properties": {k: ({"type": "number"} if k == "value" else {"type": "string"}) for k in (
                                   "name", "value", "unit", "url", "quote", "publisher", "document", "as_of",
                                   "published_at", "why")}}}}}


def web_search(q: str, cutoff: str) -> tuple[list[dict], dict]:
    """AI searches the web; code opens every cited page and checks the number is printed there."""
    from backend.nabo_style.ai_pipeline import _official_url, gpt, verify_web
    found, info = gpt("ledger_web", WEB_PROMPT.format(q=q, cutoff=cutoff), WEB_SCHEMA, web=True)
    hits = []
    for h in found["hits"]:
        if not h["url"].startswith("http") or h["value"] <= 0:
            continue
        ok, note = verify_web(h, cutoff)
        hits.append({**h, "verified": ok, "verify_note": note, "official": _official_url(h["url"])})
    return hits, dict(searches=[s for s in info.get("searches", []) if s])


def add_web_row(h: dict) -> dict:
    """Store a verified web hit as a new ledger row (never overwrites; a new value is a new row)."""
    from backend.nabo_style.ai_pipeline import _official_url, verify_web
    ok, note = verify_web(h, h["published_at"])  # re-check on the server, never trust the client copy
    if not ok:
        raise ValueError(f"원문 확인 실패: {note}")
    rows = ledger.web_rows()
    slug = re.sub(r"[^0-9A-Za-z가-힣]+", "_", h["name"])[:40]
    row = dict(id=f"web:{slug}:{h['as_of'] or h['published_at']}", indicator=f"web:{slug}", name=h["name"],
               category="웹 검색 추가", value=h["value"], unit=h["unit"], reference_year=None, as_of=h["as_of"],
               publisher=h["publisher"], document=h["document"], locator=f"인용: “{h['quote'][:80]}”",
               published_at=h["published_at"], published_at_confirmed=False, url=h["url"],
               grade="공식 통계" if _official_url(h["url"]) else "가정(언론보도)", update_cycle_years=None,
               supersedes=None, learned_from_answer=False, quote=h["quote"],
               note=f"웹 검색으로 추가({time.strftime('%Y-%m-%d')}) · {note} · 공개일은 AI 보고값")
    if any(r["id"] == row["id"] for r in rows):
        raise ValueError("이미 원장에 있는 자료예요.")
    ledger.WEB_LEDGER.write_text(json.dumps(rows + [row], ensure_ascii=False, indent=1), encoding="utf-8")
    _index.cache_clear()
    from backend.nabo_style import ai_pipeline
    ai_pipeline._rows.cache_clear()
    return row
