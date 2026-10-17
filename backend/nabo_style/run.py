"""Run an AI-written NABO-style spec and print a NABO-shaped result.

Spec (JSON):
  bill_no, cutoff (proposal date), years [..],
  scope: [{clause, decision: estimated|not_estimated|not_applicable, reason}],
  items: [{label, clause, template, inputs: {name: {value, source} | {ref: series}}}]
``{"ref": "civil_wage_growth"}`` pulls a point-in-time forecast (cutoff-filtered).
Run: python3 -m backend.nabo_style.run SPEC.json [OUT.json]
"""
from __future__ import annotations

import json
import sys

from backend.nabo_style.reference import forecast
from backend.nabo_style.templates import TEMPLATES

DECISIONS = {"estimated", "not_estimated", "not_applicable"}


def _resolve(inputs: dict, *, cutoff: str, bill_no: str) -> dict:
    out = {}
    for name, spec in inputs.items():
        if "ref" in spec:
            fc = forecast(spec["ref"], cutoff, exclude_bill=bill_no)
            out[name] = {"value": fc["values"],
                         "source": f"NABO 전망 {spec['ref']} (공개일≤{cutoff}, 최신인용 {fc['newest_quote']}, "
                                   f"출처 {', '.join(fc['sources'])})"}
        else:
            if not str(spec.get("source") or "").strip():
                raise ValueError(f"{name}: every value needs a source")
            out[name] = spec
    return out


def run(spec: dict) -> dict:
    years = list(spec["years"])
    for row in spec["scope"]:
        if row["decision"] not in DECISIONS or not row.get("reason", "").strip() and row["decision"] != "estimated":
            raise ValueError(f"scope row needs a decision and reason: {row}")
    items, total = [], [0.0] * len(years)
    for item in spec["items"]:
        inputs = _resolve(item["inputs"], cutoff=spec["cutoff"], bill_no=spec["bill_no"])
        parts = TEMPLATES[item["template"]](years, inputs)
        amount = [sum(p[i] for p in parts.values()) for i in range(len(years))]
        total = [t + a for t, a in zip(total, amount)]
        items.append(dict(label=item["label"], clause=item.get("clause", ""), template=item["template"],
                          parts={k: [round(x) for x in v] for k, v in parts.items()},
                          annual_thousand=[round(x) for x in amount],
                          inputs={k: v.get("source") for k, v in inputs.items()}))
    partial = any(r["decision"] == "not_estimated" for r in spec["scope"])
    result_type = ("미첨부(전 항목 추계곤란)" if not items and partial
                   else "미대상" if not items else "일부추계" if partial else "추계")
    return dict(bill_no=spec["bill_no"], cutoff=spec["cutoff"], years=years,
                result_type=result_type,
                annual_million=[round(x / 1000) for x in total],
                total_million=round(sum(total) / 1000), items=items, scope=spec["scope"])


def main() -> None:
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    result = run(spec)
    if len(sys.argv) > 2:
        json.dump(result, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"{result['bill_no']} {result['result_type']} 합계 {result['total_million']:,}백만원 "
          f"연도별 {result['annual_million']}")
    for item in result["items"]:
        print(f"  - {item['label']}: {[round(x / 1000) for x in item['annual_thousand']]}백만원")
    for row in result["scope"]:
        if row["decision"] != "estimated":
            print(f"  · [{row['decision']}] {row['clause']}: {row['reason']}")


if __name__ == "__main__":
    main()
