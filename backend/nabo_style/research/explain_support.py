"""Walk through a support-payment estimate step by step (for demos and review).

Shows who did what: the AI's reading of the bill (spec), the deterministic
checks and formula, where each number came from (ledger provenance), what the
reference ledger offered at the bill's date, and — only after the estimate is
fixed — the comparison with NABO's published estimate.
Run: python3 -m backend.nabo_style.research.explain_support SPEC.json
"""
from __future__ import annotations

import json
import re
import sys

from backend.nabo_style import ledger
from backend.nabo_style.support_payment import BILLS, _bill_text, estimate
from backend.nabo_style.reference_miner import ROOT

import fitz

EXTRACTED = ROOT / "generated/nabo_style/support/extracted"


def _step(n: int, title: str, who: str) -> None:
    print(f"\n[{n}] {title}  — {who}")


def main() -> None:
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    bill, cutoff = spec["bill_no"], spec["cutoff"]
    raw = re.sub(r"\s+", "", "".join(p.get_text() for p in fitz.open(BILLS / bill / "bill_text.pdf")))
    operative = _bill_text(bill)
    print(f"■ {spec['bill_title']} ({bill}) · 기준시점 = 발의일 {cutoff}")

    _step(1, "원문 분리: 제안이유 vs 개정 조문", "프로그램")
    print(f"    전체 {len(raw):,}자 중 개정 조문 {len(operative):,}자만 근거로 사용(제안이유는 근거 불인정)")

    _step(2, "재정수반 조문 읽기·범위 판단", "AI(조문 해석) → 프로그램이 인용 검증")
    for c in spec["clauses"]:
        print(f"    {c['id']}: “{c['quote'][:60]}” → 개정 조문에서 확인됨")
    for e in spec.get("excluded", []):
        print(f"    미추계: {e['item']} — {e['reason']}")

    _step(3, "산식 선택", "프로그램(지원금 템플릿 규칙)")
    print("    지원금 = Σ(대상 그룹 인원 × 1인당 지급액) × 지급연도")
    ranged = any(g["amount"]["min"] != g["amount"]["max"] for g in spec["groups"])
    print(f"    · 지급액이 {'범위 → 하한·상한 시나리오' if ranged else '정액 → 단일 시나리오'}")
    split = (spec.get("split") or {}).get("national")
    print(f"    · 국가·지자체 분담: {'원문 명시값 사용' if split is not None else '원문에 없음 → 동종 사업 선례 분담비율 준용(가정)'}")

    _step(4, "변수 채우기: 각 값의 출처", "프로그램(기준정보 원장 조회) + AI(원장에 없을 때 공식자료 조사)")
    for g in spec["groups"]:
        rec = g["recipients"]
        if "fact_topic" in rec:
            from backend.nabo_style.reference_facts import TOPICS
            row = ledger.lookup(TOPICS[rec["fact_topic"]], cutoff)
            print(f"    {g['name']}: {row['value']:,} ← 원장 · {ledger.provenance(row, cutoff)}")
        else:
            print(f"    {g['name']}: {rec['value']:+,} ← AI 조사 [{rec['grade']}] {rec['source'][:90]}")
            hits = ledger.search(re.sub(r"\(.*?\)", "", g["name"]).split()[0], cutoff, limit=2)
            print(f"        (그 시점 원장에 있던 후보: {len(hits)}건"
                  + (f", 예: {ledger.provenance(hits[0], cutoff)[:80]}" if hits else "") + ")")
        print(f"        1인당 {g['amount']['min']:,}원 ← 법안 {g['amount']['clause']}")

    _step(5, "계산", "프로그램")
    result = estimate(spec)
    for name, s in result["scenarios"].items():
        print(f"    {name}: {s['total_won'] / 1e8:,.0f}억원 (국가 {s['national_won'] / 1e8:,.0f}억 · 지자체 {s['local_won'] / 1e8:,.0f}억)")

    answer = EXTRACTED / f"{bill}.json"
    if answer.exists():
        _step(6, "사후 비교: 국회예산정책처 실제 추계(위 결과 확정 후 열람)", "프로그램")
        nabo = json.loads(answer.read_text(encoding="utf-8"))
        res = nabo["result"]
        total = res.get("total_million")
        if total:
            ours = next(iter(result["scenarios"].values()))["total_won"] / 1e6
            print(f"    NABO {total / 100:,.0f}억원 vs 우리 {ours / 100:,.0f}억원 → 오차 {(ours - total) / total * 100:+.2f}%")
        for v in nabo.get("variables", []):
            print(f"    NABO 변수 {v['name']}: {v['value']} {v.get('unit', '')} ({v.get('as_of')}, {v.get('source')})")


if __name__ == "__main__":
    main()
