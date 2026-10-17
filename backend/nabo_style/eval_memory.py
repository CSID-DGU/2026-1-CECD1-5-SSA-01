"""Raw-estimate search (v4) vs citation memory vs their fusion, same gold set.

Hit = a retrieved estimate's text contains the precedent NABO cited.
Split by whether a same-law estimate is among the gold (sibling) or not (new family).
Run: python3 -m backend.nabo_style.eval_memory
"""
from __future__ import annotations

from collections import Counter

from backend.nabo_style import bill_features as BF
from backend.nabo_style.citation_memory import recall
from backend.nabo_style.eval_variants import gold_rows, query_for
from backend.nabo_style.precedent_search import search
from backend.nabo_style.reference import _texts


def _fuse(*lists, k=20, c=60):
    score = Counter()
    for ranked in lists:
        for rank, bill in enumerate(ranked):
            score[bill] += 1 / (c + rank)
    return [b for b, _ in score.most_common(k)]


def main() -> None:
    names = {d["bill_no"]: d["bill_name"] for d in _texts()}
    rows = gold_rows()
    tally = {m: Counter() for m in ("raw_v4", "memory", "fusion")}
    for r, _, cutoff, gold in rows:
        query, boosts = query_for(r, "v4_ministry_item")
        raw = [h["bill_no"] for h in search(query, cutoff, exclude_bill=r["bill_no"], k=20, **boosts)]
        mem = [h["bill_no"] for h in recall(query, cutoff, item_type=r["item_type"],
                                            exclude_bill=r["bill_no"], k=20)]
        group = "sibling" if any(BF.law_name(names[g]) == BF.law_name(r["bill_name"]) for g in gold) else "new"
        for method, ranked in (("raw_v4", raw), ("memory", mem), ("fusion", _fuse(raw, mem))):
            t = tally[method]
            t[f"{group}_n"] += 1
            t["all_n"] += 1
            for k in (1, 5, 20):
                hit = any(b in gold for b in ranked[:k])
                t[f"{group}@{k}"] += hit
                t[f"all@{k}"] += hit
    for method, t in tally.items():
        cols = "  ".join(f"{g} @1 {t[f'{g}@1'] / t[f'{g}_n']:.0%} @5 {t[f'{g}@5'] / t[f'{g}_n']:.0%} "
                         f"@20 {t[f'{g}@20'] / t[f'{g}_n']:.0%} (n={t[f'{g}_n']})"
                         for g in ("all", "sibling", "new"))
        print(f"{method:7s} {cols}")


if __name__ == "__main__":
    main()
