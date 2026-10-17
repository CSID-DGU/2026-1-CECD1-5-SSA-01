"""analyzer_v2(통합 채널)로 단일 의안을 돌려 총액/항목/holdout을 뽑는다."""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("ANALYZE_ARTICLE_WORKERS", "1")

from backend.analyzer_v2 import analyze_v2

FILES = Path("backend/generated/assembly_rag_seed_age21_50/files")


def _walk_bills(obj, found):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in {"bill_no", "source_bill_no"} and v:
                found.add(str(v))
            _walk_bills(v, found)
    elif isinstance(obj, list):
        for v in obj:
            _walk_bills(v, found)


def main():
    bill = sys.argv[1] if len(sys.argv) > 1 else "2126640"
    pdf = FILES / bill / "bill_text_의안원문.pdf"
    content_b64 = base64.b64encode(pdf.read_bytes()).decode()
    result = analyze_v2(f"{bill}_의안원문.pdf", content_b64, form_type="assembly")

    est = result.get("estimate") or result.get("if_needs_estimate") or {}
    total = est.get("total_amount_thousand")
    total_m = None if total is None else round(total / 1000)
    items = est.get("items") or []
    year_rows = est.get("year_estimates") or []

    bills = set()
    _walk_bills(result.get("estimate"), bills)
    _walk_bills(result.get("references"), bills)

    print("=" * 60)
    print(f"[{bill}] analyzer_v2 (통합 채널)")
    print(f"  의안명       : {result.get('billName') or result.get('bill_name')}")
    print(f"  판정         : {result.get('verdict')}")
    print(f"  계산상태     : {est.get('calculation_status')}")
    print(f"  총액         : {total_m} 백만원")
    print(f"  연도별(천원) : {[r.get('amount_thousand') for r in year_rows[:5]]}")
    print(f"  LEAK(2126640): {'!! ' if bill in bills else 'false '} (선례 {len(bills)}건)")
    print(f"  항목 수      : {len(items)}")
    for it in items:
        print(f"   · {it.get('name')} | {it.get('formula')} | {it.get('amount_thousand')}천원")
    print("=" * 60)

    out_dir = Path("backend/generated/eval_v2")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{bill}.json").write_text(
        json.dumps({"bill_no": bill, "total_million": total_m,
                    "year_thousand": [r.get("amount_thousand") for r in year_rows[:5]],
                    "status": est.get("calculation_status"),
                    "leak": bill in bills, "n_precedents": len(bills),
                    "full": result}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
