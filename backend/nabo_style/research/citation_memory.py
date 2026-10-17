"""Analyst memory: "for this kind of item, NABO reused that precedent".

Each NABO citation sentence (public from its estimate's reply date) is an
entry describing what was being estimated and which precedent was reused.
A new item is matched on what it does (item type, function words, ministry,
named target), not on the precedent's own name or the bill's topic.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from functools import lru_cache

from backend.nabo_style.research.precedent_gold import OUT as GOLD
from backend.nabo_style.research.precedent_search import _tokens


@lru_cache(maxsize=1)
def _entries():
    entries = [json.loads(l) for l in GOLD.open(encoding="utf-8")]
    entries = [e for e in entries if e.get("reply_date")]
    postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
    lengths = []
    for i, e in enumerate(entries):
        counts = Counter(_tokens(f"{e['item_type']} {e['sentence']} {e['bill_name']}"))
        lengths.append(sum(counts.values()))
        for token, tf in counts.items():
            postings[token].append((i, tf))
    return entries, postings, lengths, sum(lengths) / len(lengths)


def recall(query: str, cutoff: str, *, item_type: str = "", exclude_bill: str = "",
           k: int = 10, w_item: float = 0.3, k1: float = 1.2, b: float = 0.75) -> list[dict]:
    """Earlier citations most like the new item; one per citing estimate."""
    entries, postings, lengths, avg = _entries()
    n = len(entries)
    scores: dict[int, float] = defaultdict(float)
    for token, _ in Counter(_tokens(query)).items():
        plist = postings.get(token)
        if not plist:
            continue
        idf = math.log(1 + (n - len(plist) + .5) / (len(plist) + .5))
        for i, tf in plist:
            scores[i] += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * lengths[i] / avg))
    if not scores:
        return []
    top = max(scores.values())
    for i in scores:
        if item_type and entries[i]["item_type"] == item_type:
            scores[i] += w_item * top
    out, seen = [], set()
    for i, score in sorted(scores.items(), key=lambda x: -x[1]):
        e = entries[i]
        if e["reply_date"] > cutoff or e["bill_no"] == exclude_bill or e["bill_no"] in seen:
            continue
        seen.add(e["bill_no"])
        out.append(dict(bill_no=e["bill_no"], bill_name=e["bill_name"], reply_date=e["reply_date"],
                        score=round(score, 2), cited_names=e["cited_names"], sentence=e["sentence"]))
        if len(out) == k:
            break
    return out
