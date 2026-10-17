"""Score precedent retrieval against the NABO citation gold set.

For each gold citation naming a precedent, query = item-type terms + the
bill's competent ministry + bill title (all knowable before the answer);
retrieval sees only estimates replied before the bill's proposal date.
A hit means a retrieved estimate (top-k, one passage per estimate) contains
the cited precedent name anywhere in its text.
Run: python3 -m backend.nabo_style.research.eval_precedent_search
"""
from __future__ import annotations

import json
import re
from collections import Counter

import fitz

from backend.nabo_style.research.precedent_gold import OUT as GOLD
from backend.nabo_style.research.precedent_search import ITEM_QUERY, search
from backend.nabo_style.reference import _texts
from backend.nabo_style.reference_miner import ROOT

BILLS = ROOT / "generated/assembly_22_pdfs/by_bill"
_MINISTRY = re.compile(r"([가-힣]{2,12}(?:부|처|청|위원회))장관|([가-힣]{2,12}(?:처|청))장")


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _ministry(bill_no: str) -> str:
    try:
        text = "".join(p.get_text() for p in fitz.open(BILLS / bill_no / "bill_text.pdf"))
    except Exception:
        return ""
    found = Counter(a or b for a, b in _MINISTRY.findall(_norm(text)))
    return found.most_common(1)[0][0] if found else ""


def main(ks=(1, 5, 20)) -> None:
    full = {d["bill_no"]: _norm(d["text"]) for d in _texts()}
    dates = {d["bill_no"]: d["reply_date"] for d in _texts()}
    propose = {json.loads(l)["bill_no"]: json.loads(l)["propose_date"]
               for l in (ROOT / "generated/nabo_style/estimate_texts.jsonl").open(encoding="utf-8")}
    rows, ministries = [], {}
    for line in GOLD.open(encoding="utf-8"):
        r = json.loads(line)
        names = [_norm(n) for n in r["cited_names"]
                 if len(_norm(n)) >= 6 and not re.search(r"법률|법$|규정|지침|시행령|시행규칙", n)]
        if names and r["item_type"] in ITEM_QUERY and r["bill_no"] in propose:
            rows.append((r, names))
    hits, reach = Counter(), 0
    per_type = Counter()
    per_type_hit = Counter()
    for r, names in rows:
        cutoff = propose[r["bill_no"]]
        reachable = any(any(n in t for n in names) for b, t in full.items()
                        if dates[b] <= cutoff and b != r["bill_no"])
        if not reachable:
            continue
        reach += 1
        bill = r["bill_no"]
        ministries.setdefault(bill, _ministry(bill))
        query = f"{ITEM_QUERY[r['item_type']]} {ministries[bill]} {r['bill_name']}"
        found = search(query, cutoff, exclude_bill=bill, k=max(ks))
        rank = next((i for i, h in enumerate(found) if any(n in full[h["bill_no"]] for n in names)), None)
        per_type[r["item_type"]] += 1
        for k in ks:
            if rank is not None and rank < k:
                hits[k] += 1
        if rank is not None and rank < 5:
            per_type_hit[r["item_type"]] += 1
    print(f"gold with named precedent: {len(rows)}; reachable before proposal date: {reach}")
    for k in ks:
        print(f"  hit@{k}: {hits[k]}/{reach} ({hits[k] / max(reach, 1):.0%})")
    for t, v in per_type.most_common():
        print(f"  {t}: hit@5 {per_type_hit[t]}/{v}")


if __name__ == "__main__":
    main()
