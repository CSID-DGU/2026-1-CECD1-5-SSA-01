"""Validate extracted support-payment estimates and rank what the 단가표 needs.

- every variable quote must appear (whitespace-insensitive) in the estimate text
- counts roles and frequent variable names → which reference values to collect first
Run: python3 -m backend.nabo_style.support_extract_check
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from backend.nabo_style.reference_miner import ROOT

BASE = ROOT / "generated/nabo_style/support"
_WS = re.compile(r"\s+")
_TOPIC = [  # coarse grouping of free-text variable names
    ("주민등록·총인구", r"주민등록|총인구|전국민|국민 수"), ("연령별 인구", r"\d+세|아동|청년|노인|고령|인구"),
    ("국가유공자·보훈", r"유공자|보훈|참전|유족|고엽제|특수임무"), ("장애인", r"장애"),
    ("기초생활·차상위", r"수급자|차상위|기초생활|생계급여"), ("기준중위소득", r"중위소득"),
    ("최저임금", r"최저임금"), ("물가·증가율", r"물가|상승률|증가율|인상률"),
    ("고용보험·구직", r"구직|실업|고용보험|육아휴직"), ("농어민", r"농어|농가|어가|농업인|어업인"),
    ("공무원·군인", r"공무원|군인|장병|병사"), ("외국인", r"외국인|체류"),
]


def _topic(name: str) -> str:
    return next((t for t, p in _TOPIC if re.search(p, name)), "기타")


def _forms(x) -> set[str]:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return set()
    forms = {f"{x:,}", str(x)}
    if float(x).is_integer():
        forms |= {f"{int(x):,}", str(int(x))}
    return forms


def _value_in_quote(v: dict) -> bool:
    """A numeric value (or every value of a year table) must be visible in its quote."""
    quote = _WS.sub("", v.get("quote") or "")
    vals = v.get("value")
    vals = list(vals.values()) if isinstance(vals, dict) else [vals]
    nums = [x for x in vals if isinstance(x, (int, float)) and not isinstance(x, bool)]
    return all(any(form in quote for form in _forms(x)) for x in nums) if nums else True


def main() -> None:
    files = sorted((BASE / "extracted").glob("*.json"))
    bad, value_miss, roles, topics, sources = [], [], Counter(), Counter(), Counter()
    n_var = n_support = 0
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        text = _WS.sub("", (BASE / "texts" / f"{f.stem}.txt").read_text(encoding="utf-8"))
        n_support += bool(data.get("is_support_payment"))
        for v in data.get("variables") or []:
            n_var += 1
            if not v.get("quote") or _WS.sub("", v["quote"]) not in text:
                bad.append((f.stem, v.get("name")))
            elif not _value_in_quote(v):
                value_miss.append((f.stem, v.get("name"), v.get("value")))
            roles[v.get("role")] += 1
            topics[_topic(v.get("name") or "")] += 1
            if v.get("source"):
                sources[re.sub(r"[「」｢｣\s]", "", v["source"])[:24]] += 1
    print(f"files {len(files)}, support {n_support}, variables {n_var}, quote failures {len(bad)}")
    if bad:
        print("  failed quotes:", bad[:10])
    print(f"numeric values not literally in their quote: {len(value_miss)}")
    for m in value_miss[:15]:
        print("  ", m)
    print("roles:", roles.most_common())
    print("topics (단가표 우선순위):", topics.most_common())
    print("top sources:", sources.most_common(12))


if __name__ == "__main__":
    main()
