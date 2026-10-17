"""Point-in-time lookup of mined NABO forecast series and precedent text."""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date, timedelta
from functools import lru_cache

from backend.nabo_style.reference_miner import OUT as SERIES_PATH, TEXTS


@lru_cache(maxsize=1)
def _series_rows() -> tuple[dict, ...]:
    return tuple(json.loads(line) for line in SERIES_PATH.open(encoding="utf-8"))


def forecast(series: str, cutoff: str, *, exclude_bill: str = "", window_days: int = 120) -> dict:
    """Consensus of the latest observations public on or before ``cutoff``.

    Only quotes in the ``window_days`` before the newest visible quote vote,
    so one mis-parsed table cannot override the prevailing NABO vintage.
    """
    rows = [r for r in _series_rows() if r["series"] == series
            and r["available_at"] <= cutoff and r["source_bill_no"] != exclude_bill]
    if not rows:
        raise LookupError(f"no {series} forecast public before {cutoff}")
    newest = max(r["available_at"] for r in rows)
    floor = (date.fromisoformat(newest) - timedelta(days=window_days)).isoformat()
    recent = [r for r in rows if r["available_at"] >= floor]
    years = sorted({y for r in recent for y in r["values"]})
    values, support = {}, {}
    for year in years:
        votes = Counter(r["values"][year] for r in recent if year in r["values"])
        value, count = votes.most_common(1)[0]
        values[int(year)] = value
        support[int(year)] = f"{count}/{sum(votes.values())}"
    sources = sorted({(r["available_at"], r["source_bill_no"]) for r in recent})[-3:]
    return dict(series=series, values=values, support=support, newest_quote=newest,
                sources=[f"{b}({d})" for d, b in sources])


@lru_cache(maxsize=1)
def _texts() -> tuple[dict, ...]:
    keep = ("bill_no", "bill_name", "estimate_no", "text")
    paths = [TEXTS, TEXTS.with_name("estimate_texts_21.jsonl"), TEXTS.with_name("estimate_texts_extra.jsonl")]
    out = []
    for path in paths:
        if not path.exists():
            continue
        for d in map(json.loads, path.open(encoding="utf-8")):
            if d.get("reply_date"):
                out.append({**{k: d.get(k) for k in keep}, "nabo_reply_date": d["reply_date"],
                            "reply_date": public_date(d)})
    return tuple(out)


def public_date(doc: dict) -> str:
    """An estimate is public only once its bill is proposed (it is attached to the bill).

    Members often request the estimate before proposing, so the reply date can
    precede the proposal date; until proposal only the requesting office has it.
    """
    return max(d for d in (doc.get("reply_date"), doc.get("propose_date")) if d)


def search_precedents(terms: list[str], cutoff: str, *, exclude_bill: str = "",
                      limit: int = 8, span: int = 260) -> list[dict]:
    """Keyword search over estimates public before ``cutoff``; never selects."""
    hits = []
    for doc in _texts():
        if doc["reply_date"] > cutoff or doc["bill_no"] == exclude_bill:
            continue
        text = re.sub(r"\s+", " ", doc["text"])
        if all(term in text for term in terms):
            i = text.find(terms[0])
            hits.append(dict(bill_no=doc["bill_no"], bill_name=doc["bill_name"],
                             reply_date=doc["reply_date"], estimate_no=doc["estimate_no"],
                             excerpt=text[max(0, i - 80):i + span]))
    hits.sort(key=lambda h: h["reply_date"], reverse=True)
    return hits[:limit]
