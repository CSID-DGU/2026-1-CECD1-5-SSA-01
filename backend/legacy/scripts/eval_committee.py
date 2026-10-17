"""위원회 채널 자가개선 루프용 평가 하네스.

한 건(또는 여러 건)을 위원회 채널에 태우고:
 - 공식 비용추계서 총액 파싱
 - 시스템 프리뷰 총액과 오차율
 - 산식/변수/출처, 쌍둥이(같은 bill_name) 참조 여부
를 진단용으로 한 번에 뽑는다.

사용: python3 -m backend.legacy.scripts.eval_committee 2126640 [2126636 ...]
"""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("ANALYZE_ARTICLE_WORKERS", "1")

import fitz  # noqa: E402

from backend.erce_web.committee_channel import analyze_committee_document  # noqa: E402
from backend.legacy.scripts.evaluate_assembly_batch import _parse_first_cost_table  # noqa: E402

FILES = Path("backend/generated/assembly_rag_seed_age21_50/files")
OUT_DIR = Path("backend/generated/eval_committee")


def _find_pdf(bill_dir: Path, *, answer: bool) -> Path | None:
    """의안 폴더에서 본문/정답지 PDF를 파일명 패턴으로 찾는다.

    파일명 규칙이 두 가지("bill_text_의안원문.pdf" / "{의안}_의사국 의안과_의안원문.pdf")라
    하드코딩하지 않고 키워드로 매칭한다.
    """
    cands: list[Path] = []
    for p in bill_dir.glob("*.pdf"):
        name = p.name
        if answer:
            if ("비용추계서" in name or "cost_estimate" in name) and "미첨부" not in name:
                cands.append(p)
        else:
            if "의안원문" in name or "bill_text" in name:
                cands.append(p)
    return sorted(cands, key=lambda p: len(p.name))[0] if cands else None


def _pdf_text(path: Path) -> str:
    with fitz.open(path) as doc:
        return "\n".join(page.get_text() for page in doc)


def _collect_evidence(committees: list[dict], self_bill: str, self_name: str) -> dict[str, Any]:
    """선례 출처 의안번호와, 같은 법률명(쌍둥이) 참조 여부를 수집."""
    bills: set[str] = set()
    twin_refs: list[dict[str, str]] = []
    self_name_key = "".join(self_name.split())

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            bn = str(obj.get("bill_no") or obj.get("source_bill_no") or "")
            nm = str(obj.get("bill_name") or "")
            if bn:
                bills.add(bn)
                nm_key = "".join(nm.split())
                if bn != self_bill and nm_key and nm_key == self_name_key:
                    twin_refs.append({"bill_no": bn, "bill_name": nm})
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(committees)
    # 중복 twin 제거
    seen = set()
    uniq_twins = []
    for t in twin_refs:
        if t["bill_no"] in seen:
            continue
        seen.add(t["bill_no"])
        uniq_twins.append(t)
    return {"source_bills": sorted(bills), "twin_refs": uniq_twins, "leak": self_bill in bills}


def _committee_brief(c: dict) -> dict[str, Any]:
    vars_brief = {}
    for key, v in (c.get("variables") or {}).items():
        if isinstance(v, dict):
            vars_brief[key] = {
                "value": v.get("value"),
                "source": v.get("source_type"),
                "confirmed": v.get("confirmed"),
            }
    formula = c.get("formula")
    label = formula.get("label") if isinstance(formula, dict) else formula
    return {
        "name": c.get("name"),
        "change_type": c.get("change_type"),
        "status": c.get("status"),
        "formula": label,
        "total_thousand": c.get("total_amount_thousand"),
        "variables": vars_brief,
        "unconfirmed": c.get("unconfirmed_variables"),
    }


def evaluate(bill: str) -> dict[str, Any]:
    bill_dir = FILES / bill
    bill_pdf = _find_pdf(bill_dir, answer=False)
    official_pdf = _find_pdf(bill_dir, answer=True)
    if bill_pdf is None:
        raise SystemExit(f"본문 PDF 없음: {bill_dir}")

    content_b64 = base64.b64encode(bill_pdf.read_bytes()).decode()
    result = analyze_committee_document(f"{bill}_의안원문.pdf", content_b64)

    official = {"total": None}
    if official_pdf is not None:
        official = _parse_first_cost_table(_pdf_text(official_pdf))

    system_total_thousand = result.get("summary", {}).get("previewTotalThousand")
    system_million = None if system_total_thousand is None else round(system_total_thousand / 1000)
    official_million = official.get("total")

    error_pct = None
    if official_million and system_million is not None and official_million != 0:
        error_pct = round((system_million - official_million) / official_million * 100, 1)

    evidence = _collect_evidence(
        result.get("committees") or [], bill, result.get("billName") or ""
    )

    report = {
        "bill_no": bill,
        "bill_name": result.get("billName"),
        "doc_type": result.get("documentType"),
        "committee_count": result.get("scope", {}).get("committeeCount"),
        "official_million": official_million,
        "system_million": system_million,
        "error_pct": error_pct,
        "status_summary": result.get("summary"),
        "leak": evidence["leak"],
        "twin_refs": evidence["twin_refs"],
        "committees": [_committee_brief(c) for c in (result.get("committees") or [])],
        "elapsed_sec": result.get("elapsedSec"),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{bill}.json").write_text(
        json.dumps({"report": report, "full": result}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def _print(report: dict[str, Any]) -> None:
    r = report
    print("=" * 64)
    print(f"[{r['bill_no']}] {r['bill_name']}  ({r['doc_type']})")
    print(f"  공식 총액   : {r['official_million']} 백만원")
    print(f"  시스템 총액 : {r['system_million']} 백만원   오차: {r['error_pct']}%")
    print(f"  위원회 수   : {r['committee_count']}   상태: {r['status_summary']}")
    print(f"  LEAK        : {'!! ' + str(r['leak']) if r['leak'] else 'false'}")
    if r["twin_refs"]:
        print(f"  쌍둥이 참조 : {r['twin_refs']}  ← 같은 법률명 선례 (near-leak)")
    for c in r["committees"]:
        print(f"  · {c['name']} [{c['change_type']}/{c['status']}] {c['total_thousand']}천원")
        print(f"      산식: {c['formula']}")
        for k, v in (c["variables"] or {}).items():
            print(f"      {k}={v['value']} ({v['source']}, confirmed={v['confirmed']})")
    print(f"  소요: {r['elapsed_sec']}초")
    print("=" * 64)


def main() -> None:
    bills = sys.argv[1:] or ["2126640"]
    reports = []
    for bill in bills:
        rep = evaluate(bill)
        _print(rep)
        reports.append(rep)
    if len(reports) > 1:
        print("\n요약:")
        for r in reports:
            print(f"  {r['bill_no']} {r['bill_name'][:16]:16} 공식 {r['official_million']} / 시스템 {r['system_million']} / 오차 {r['error_pct']}% / twin {len(r['twin_refs'])}")


if __name__ == "__main__":
    main()
