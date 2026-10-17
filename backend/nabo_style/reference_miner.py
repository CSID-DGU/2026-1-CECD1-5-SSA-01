"""Mine NABO common forecast series quoted in earlier cost estimates.

Each observation keeps the quoting estimate's reply date as ``available_at``
so a target bill only sees forecasts that were public before its cutoff.
Run: python3 -m backend.nabo_style.reference_miner
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXTS = ROOT / "generated/nabo_style/estimate_texts.jsonl"
OUT = ROOT / "generated/nabo_style/reference_series.jsonl"

SERIES = {
    "civil_wage_growth": ("공무원임금평균상승률", "공무원임금 평균상승률", "공무원 임금 평균상승률",
                          "공무원보수상승률", "공무원 보수상승률"),
    "employer_rate": ("기관부담금요율", "기관부담금 요율", "기관부담 요율"),
    "asset_per_person": ("1인당 자산취득비", "1인당자산취득비"),
    "cpi": ("소비자물가상승률",),
    "nominal_wage_growth": ("명목임금상승률", "명목임금 상승률"),
}
# plausible ranges per series (percent for rates, thousand KRW for asset)
RANGES = {"civil_wage_growth": (0.0, 6.0), "employer_rate": (8.0, 20.0),
          "asset_per_person": (3000.0, 9000.0), "cpi": (0.0, 6.0),
          "nominal_wage_growth": (0.0, 8.0)}

_YEARS = re.compile(r"((?:20[2-3]\d\s*년?\s*){3,8})")
_NUM = re.compile(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?")
_TICK = re.compile(r"\(\s*[’'‘]\s*(\d{2})\s*\)\s*(-?\d+(?:\.\d+)?)")


def _table_after(window: str, series: str) -> dict[int, float] | None:
    m = _YEARS.search(window)
    if m:
        years = [int(y) for y in re.findall(r"20[2-3]\d", m.group(1))]
        if years == sorted(years) and len(set(years)) == len(years):
            rest = window[m.end():m.end() + 260]
            nums = []
            for tok in _NUM.findall(rest):
                value = float(tok.replace(",", ""))
                lo, hi = RANGES[series]
                if lo <= value <= hi:
                    nums.append(value)
                elif nums:
                    break
                if len(nums) == len(years):
                    break
            if len(nums) == len(years):
                return dict(zip(years, nums))
    ticks = _TICK.findall(window[:300])
    if len(ticks) >= 3:
        lo, hi = RANGES[series]
        values = {2000 + int(y): float(v) for y, v in ticks}
        if all(lo <= v <= hi for v in values.values()):
            return values
    return None


def mine() -> list[dict]:
    rows = []
    for line in TEXTS.open(encoding="utf-8"):
        doc = json.loads(line)
        if not doc.get("reply_date"):
            continue
        text = re.sub(r"\s+", " ", doc["text"])
        seen = set()
        for series, labels in SERIES.items():
            for label in labels:
                for m in re.finditer(re.escape(label), text):
                    window = text[m.start():m.start() + 420]
                    values = _table_after(window, series)
                    if not values:
                        continue
                    key = (series, tuple(sorted(values.items())))
                    if key in seen:
                        continue
                    seen.add(key)
                    vintage = re.search(r"\((20\d{2}\.\s?\d{1,2})[.)]?", window[:120])
                    rows.append(dict(series=series, values=values,
                                     unit="thousand KRW/person" if series == "asset_per_person" else "percent",
                                     vintage=vintage.group(1).replace(" ", "") if vintage else None,
                                     available_at=max(d for d in (doc["reply_date"], doc.get("propose_date")) if d),
                                     source_bill_no=doc["bill_no"],
                                     source_estimate_no=doc.get("estimate_no"),
                                     source_excerpt=window[:200]))
    return rows


def main() -> None:
    rows = mine()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps({**row, "values": {str(k): v for k, v in row["values"].items()}},
                                 ensure_ascii=False) + "\n")
    counts = defaultdict(int)
    for row in rows:
        counts[row["series"]] += 1
    print(f"reference observations: {len(rows)} {dict(counts)} -> {OUT}")


if __name__ == "__main__":
    main()
