"""범용 엔진 [1] 감지만 한 의안에 돌려본다.

committee 채널이 위원회만 잡던 것과 달리, LLM 의미 기반 범용 감지가
위원회 + 용역 + 지원 등 모든 비용유형을 섞어 잡는지 확인한다.
"""
from __future__ import annotations

import base64
import glob
import os
import sys
from pathlib import Path

os.environ.setdefault("ANALYZE_ARTICLE_WORKERS", "1")

from backend.analyzer_v2 import (
    _extract_bill_name,
    _extract_current_bill_no,
    _extract_pdf_text_from_bytes,
    split_articles,
    strip_appendices,
)
from backend.estimator.detect import detect_cost_items

FILES = Path("backend/generated/assembly_rag_seed_age21_50/files")


def _bill_pdf(bill: str) -> Path:
    cands = glob.glob(str(FILES / bill / "*의안원문*.pdf"))
    if not cands:
        raise SystemExit(f"본문 PDF 없음: {bill}")
    return Path(sorted(cands, key=len)[0])


def main() -> None:
    bill = sys.argv[1] if len(sys.argv) > 1 else "2126334"
    pdf_bytes = _bill_pdf(bill).read_bytes()
    raw = _extract_pdf_text_from_bytes(pdf_bytes)
    text = strip_appendices(raw) if raw else ""
    articles, doc_type = split_articles(text)
    bill_name = _extract_bill_name(text, bill)
    bill_no = _extract_current_bill_no(raw, bill)

    print("=" * 64)
    print(f"[{bill}] {bill_name} ({doc_type}) — 조문 {len(articles)}개")
    print("범용 감지(LLM 의미 기반, 표준산식/채널 없음) 결과:")
    print("=" * 64)
    items = detect_cost_items(articles)
    if not items:
        print("  (감지된 비용항목 없음)")
    for it in items:
        print(f"  · {it['name']}  [{it['cost_kind']}]  {it['article_refs']}")
        print(f"      → {it['cost_understanding']}")
    print(f"\n총 {len(items)}개 항목 감지.")


if __name__ == "__main__":
    main()
