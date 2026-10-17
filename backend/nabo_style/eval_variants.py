"""Ablation of analyst-style query/boost choices on the same gold set.

Run: python3 -m backend.nabo_style.eval_variants
"""
from __future__ import annotations

import json
import re

from backend.nabo_style import bill_features as BF
from backend.nabo_style.eval_precedent_search import _ministry as old_ministry, _norm
from backend.nabo_style.precedent_gold import OUT as GOLD
from backend.nabo_style.precedent_search import ITEM_QUERY, search
from backend.nabo_style.reference import _texts
from backend.nabo_style.reference_miner import ROOT

_NOT_PRECEDENT = re.compile(r"법률|법$|규정|지침|시행령|시행규칙|요령|고시"  # statutes and guidelines
                            r"|(?:교육청|재단|공단|진흥원|연구원|[부청처])$"  # bare agency names
                            r"|에따른|수립에|소요|비용$|용역비$|예산$|급여$|사업비$")  # descriptions, not names


def gold_rows() -> list[tuple[dict, list[str], str, list[str]]]:
    docs = {d["bill_no"]: d for d in _texts()}
    full = {b: _norm(d["text"]) for b, d in docs.items()}
    propose = {json.loads(l)["bill_no"]: json.loads(l)["propose_date"]
               for l in (ROOT / "generated/nabo_style/estimate_texts.jsonl").open(encoding="utf-8")}
    rows = []
    for line in GOLD.open(encoding="utf-8"):
        r = json.loads(line)
        names = [_norm(n) for n in r["cited_names"] if len(_norm(n)) >= 6 and not _NOT_PRECEDENT.search(_norm(n))]
        if not (names and r["item_type"] in ITEM_QUERY and r["bill_no"] in propose):
            continue
        cutoff = propose[r["bill_no"]]
        gold = [b for b, t in full.items() if docs[b]["reply_date"] <= cutoff and b != r["bill_no"]
                and any(n in t for n in names)]
        if gold:
            rows.append((r, names, cutoff, gold))
    return rows


def query_for(r: dict, variant: str) -> tuple[str, dict]:
    feats = BF.features(r["bill_no"])
    base = ITEM_QUERY[r["item_type"]]
    if variant == "v0_baseline":
        return f"{base} {old_ministry(r['bill_no'])} {r['bill_name']}", {}
    law = BF.law_name(r["bill_name"])
    query = f"{base} {feats['ministry']} {r['bill_name']}"
    if variant == "v1_ministry":
        return query, {}
    boosts = dict(law=law, w_law=0.5)
    if variant == "v2_same_law":
        return query, boosts
    targets = " ".join(feats["targets"].get(r["item_type"], []))
    if variant == "v3_targets":
        return f"{query} {targets}", boosts
    boosts.update(ministry=feats["ministry"], w_ministry=0.15, item_type=r["item_type"], w_item=0.15)
    return f"{query} {targets}", boosts  # v4_ministry_item


VARIANTS = ("v0_baseline", "v4_ministry_item")


def main() -> None:
    rows = gold_rows()
    print(f"reachable gold: {len(rows)}")
    for variant in VARIANTS:
        hits = {1: 0, 5: 0, 20: 0}
        for r, _, cutoff, gold in rows:
            query, boosts = query_for(r, variant)
            found = search(query, cutoff, exclude_bill=r["bill_no"], k=20, **boosts)
            rank = next((i for i, h in enumerate(found) if h["bill_no"] in gold), None)
            for k in hits:
                hits[k] += rank is not None and rank < k
        n = len(rows)
        print(f"{variant:18s} hit@1 {hits[1] / n:.0%}  hit@5 {hits[5] / n:.0%}  hit@20 {hits[20] / n:.0%}")
    BF.save_cache()


if __name__ == "__main__":
    main()
