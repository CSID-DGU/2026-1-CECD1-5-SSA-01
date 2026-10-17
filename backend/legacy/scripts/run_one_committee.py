"""단일 의안을 위원회 채널에 태우고 holdout(본인 제외)이 실제로 걸렸는지 검증한다."""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("ANALYZE_ARTICLE_WORKERS", "1")

from backend.erce_web.committee_channel import analyze_committee_document

FILES = Path("backend/generated/assembly_rag_seed_age21_50/files")


def _collect_source_bills(obj, found: set[str]) -> None:
    """결과 트리에서 선례 출처 의안번호로 보이는 값을 전부 수집."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in {"bill_no", "bill_id", "source_bill", "source_bill_no", "sourceBillNo"} and value:
                found.add(str(value))
            _collect_source_bills(value, found)
    elif isinstance(obj, list):
        for item in obj:
            _collect_source_bills(item, found)


def main() -> None:
    bill = sys.argv[1] if len(sys.argv) > 1 else "2126640"
    pdf = FILES / bill / "bill_text_의안원문.pdf"
    if not pdf.exists():
        raise SystemExit(f"PDF 없음: {pdf}")

    content_b64 = base64.b64encode(pdf.read_bytes()).decode()
    # 파일명에 의안번호를 넣어 bill_no 추출 폴백이 확실히 잡히게 한다.
    result = analyze_committee_document(f"{bill}_의안원문.pdf", content_b64)

    detected = str(result.get("billNo") or "")
    print("=" * 60)
    print(f"입력 의안번호   : {bill}")
    print(f"감지 billNo     : {detected}  {'OK' if detected == bill else '!! 불일치 → holdout 위험'}")
    print(f"의안명          : {result.get('billName')}")
    print(f"문서유형        : {result.get('documentType')}")
    print(f"조문 수         : {result.get('totalArticles')}")
    print(f"위원회 수       : {result.get('scope', {}).get('committeeCount')}")
    print(f"상태 요약       : {result.get('summary')}")
    print(f"소요(초)        : {result.get('elapsedSec')}")

    # --- holdout 검증: 결과 어디에도 본인 의안번호가 선례로 새어들면 안 됨 ---
    source_bills: set[str] = set()
    _collect_source_bills(result.get("committees"), source_bills)
    leak = bill in source_bills
    print("-" * 60)
    print(f"선례 출처 의안들 : {sorted(source_bills) if source_bills else '(없음)'}")
    print(f"EVIDENCE LEAK   : {'!! 누출 발생' if leak else 'false (본인 제외됨)'}")
    print("=" * 60)

    Path("backend/generated/_run_one_committee.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("전체 결과 저장: backend/generated/_run_one_committee.json")


if __name__ == "__main__":
    main()
