"""Item-level precedent retrieval over earlier NABO estimates (BM25, char bigrams).

Passages, not whole bills, are the unit: NABO reuses a precedent per cost
item. A query is built only from what is known before the answer: the cost
item type, the bill's competent ministry and the bill's title.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from functools import lru_cache

from backend.nabo_style.reference import _texts

ITEM_QUERY = {
    "위원회": "위원회 민간위원 회의참석수당 위원 구성 회의 개최 운영",
    "기본·종합계획": "기본계획 종합계획 수립 연구용역 용역비",
    "실태조사": "실태조사 조사 연구용역 표본 조사비",
    "연구용역": "연구용역 용역비 연구 사업비",
    "인건비·조직": "정원 직급별 보수 인건비 기본경비 증원",
    "정보시스템": "시스템 구축 운영 유지보수 정보화",
    "교육·홍보": "교육 홍보 캠페인 사업 예산",
    "시설·장비": "시설 설치 장비 건립 공사비 단가",
    "기관·센터 운영": "센터 지정 운영 운영비 지원 예산",
    "급여·지원금": "지원금 지원단가 지급 대상자 예산",
    "행사·기념일": "기념일 기념행사 홍보 예산",
    "조세·감면": "감면 조세지출 실적 세수효과",
}
_HANGUL = re.compile(r"[가-힣A-Za-z0-9]+")


def _tokens(text: str) -> list[str]:
    out = []
    for word in _HANGUL.findall(text):
        out.extend(word[i:i + 2] for i in range(max(1, len(word) - 1)))
    return out


@lru_cache(maxsize=1)
def _index(width: int = 450, step: int = 300):
    passages, meta = [], []
    for doc in _texts():
        text = re.sub(r"\s+", " ", doc["text"])
        for start in range(0, max(1, len(text) - 100), step):
            passages.append(text[start:start + width])
            meta.append((doc["reply_date"], doc["bill_no"], doc["bill_name"]))
    postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
    lengths = []
    for pid, passage in enumerate(passages):
        counts = Counter(_tokens(passage))
        lengths.append(sum(counts.values()))
        for token, tf in counts.items():
            postings[token].append((pid, tf))
    return passages, meta, postings, lengths, sum(lengths) / len(lengths)


def search(query: str, cutoff: str, *, exclude_bill: str = "", k: int = 10,
           k1: float = 1.2, b: float = 0.75, law: str = "", ministry: str = "",
           item_type: str = "", w_law: float = 0.0, w_ministry: float = 0.0,
           w_item: float = 0.0) -> list[dict]:
    """BM25, then analyst-style boosts: same amended law, same ministry, same item type."""
    if w_law or w_ministry or w_item:
        return _boosted(query, cutoff, exclude_bill=exclude_bill, k=k, law=law, ministry=ministry,
                        item_type=item_type, w_law=w_law, w_ministry=w_ministry, w_item=w_item)
    passages, meta, postings, lengths, avg = _index()
    n = len(passages)
    scores: dict[int, float] = defaultdict(float)
    for token, qtf in Counter(_tokens(query)).items():
        plist = postings.get(token)
        if not plist:
            continue
        idf = math.log(1 + (n - len(plist) + .5) / (len(plist) + .5))
        for pid, tf in plist:
            scores[pid] += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * lengths[pid] / avg))
    ranked, seen_bills = [], set()
    for pid, score in sorted(scores.items(), key=lambda x: -x[1]):
        date, bill, name = meta[pid]
        if date > cutoff or bill == exclude_bill or bill in seen_bills:
            continue
        seen_bills.add(bill)
        ranked.append(dict(bill_no=bill, bill_name=name, reply_date=date,
                           score=round(score, 2), passage=passages[pid]))
        if len(ranked) == k:
            break
    return ranked


def _boosted(query, cutoff, *, exclude_bill, k, law, ministry, item_type, w_law, w_ministry, w_item):
    from backend.nabo_style.research.bill_features import law_name
    pool = search(query, cutoff, exclude_bill=exclude_bill, k=300)
    if not pool:
        return []
    top = max(h["score"] for h in pool)
    for hit in pool:
        bonus = 0.0
        if w_law and law and law_name(hit["bill_name"]) == law:
            bonus += w_law
        if w_ministry and ministry and ministry in hit["passage"]:
            bonus += w_ministry
        if w_item and item_type and _passage_item(hit["passage"]) == item_type:
            bonus += w_item
        hit["score"] = round(hit["score"] + bonus * top, 2)
    return sorted(pool, key=lambda h: -h["score"])[:k]


def _passage_item(passage: str) -> str:
    from backend.nabo_style.research.precedent_gold import ITEM_TYPES, _label
    return _label(ITEM_TYPES, passage)
