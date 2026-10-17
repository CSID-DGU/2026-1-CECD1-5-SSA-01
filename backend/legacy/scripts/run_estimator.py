"""범용 엔진 전체 파이프라인 실행 + 정답지 오차 + 단계별 진단."""
from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

os.environ.setdefault("ANALYZE_ARTICLE_WORKERS", "1")

import fitz

from backend.estimator.pipeline import estimate_from_pdf
from backend.estimator.types import RowStatus
from backend.legacy.scripts.evaluate_assembly_batch import _parse_first_cost_table

FILES = Path("backend/generated/assembly_rag_seed_age21_50/files")


def _pdf(bill: str, answer: bool) -> Path | None:
    kw = "비용추계서" if answer else "의안원문"
    cands = [p for p in glob.glob(str(FILES / bill / f"*{kw}*.pdf")) if "미첨부" not in p]
    return Path(sorted(cands, key=len)[0]) if cands else None


def main() -> None:
    bill = sys.argv[1] if len(sys.argv) > 1 else "2126334"
    table = estimate_from_pdf(_pdf(bill, False).read_bytes(), filename=f"{bill}.pdf")

    off = {"total": None}
    ap = _pdf(bill, True)
    if ap:
        off = _parse_first_cost_table("\n".join(p.get_text() for p in fitz.open(ap)))
    official = off.get("total")

    sys_total = round(table.computed_total_thousand() / 1000)
    err = None
    if official and sys_total:
        err = round((sys_total - official) / official * 100, 1)

    print("=" * 66)
    print(f"[{bill}] {table.bill_name}  leak제외={table.holdout_excluded}")
    print(f"  공식 총액   : {official} 백만원")
    print(f"  시스템 총액 : {sys_total} 백만원   오차: {err}%")
    print(f"  상태 분포   : {table.status_counts()}")
    print("=" * 66)
    # 단계별 깔때기
    n = len(table.items)
    estimable = [it for it in table.items if it.status != RowStatus.BLOCKED or it.year_amounts_thousand and any(table.items)]
    computed = [it for it in table.items if it.status in (RowStatus.COMPUTED, RowStatus.REVIEW_REQUIRED)]
    needs_ext = [it for it in table.items if it.status == RowStatus.NEEDS_EXTERNAL]
    blocked = [it for it in table.items if it.status == RowStatus.BLOCKED]
    print(f"깔때기: 감지 {n} → 계산됨 {len(computed)} / 외부값필요 {len(needs_ext)} / 추계제외·blocked {len(blocked)}")
    print()
    for it in table.items:
        amt = it.total_thousand
        amt_s = f"{amt//1000}백만" if amt else "-"
        rep = f" ×{it.replication.factor}" if it.replication.factor > 1 else ""
        print(f"  [{it.status.value:15}] {it.name[:26]:26} {amt_s:>7}{rep}")
        if it.status.value in ("needs_external", "blocked"):
            miss = it.unfilled_variables
            why = it.evidence[-1] if it.evidence else {}
            note = why.get("non_estimable") or (f"미확보변수 {miss}" if miss else "")
            if note:
                print(f"       └ {str(note)[:70]}")


if __name__ == "__main__":
    main()
