"""Compatibility shim: facts now live in the 기준정보 원장 (ledger.py)."""
from __future__ import annotations

from backend.nabo_style import ledger

TOPICS = {"주민등록인구": "resident_population", "현금지원금 재원분담": "cash_relief_split",
          "장기체류 외국인": "long_stay_foreigners"}


def facts(topic: str, cutoff: str) -> list[dict]:
    """Ledger rows for a topic public on/before cutoff, newest first, in the old fact shape."""
    indicator = TOPICS[topic]
    rows = [r for r in ledger.rows() if r["indicator"] == indicator and r["published_at"] <= cutoff]
    rows.sort(key=lambda r: (r["published_at"], r.get("as_of", "")), reverse=True)
    return [dict(key=r["id"], value=r["value"], unit=r["unit"], as_of=r.get("as_of") or r["reference_year"],
                 available_at=r["published_at"], title=r["document"], publisher=r["publisher"],
                 url=r["url"], scope=r.get("note", ""), learned_from_answer=r["learned_from_answer"],
                 note=ledger.provenance(r, cutoff)) for r in rows]
