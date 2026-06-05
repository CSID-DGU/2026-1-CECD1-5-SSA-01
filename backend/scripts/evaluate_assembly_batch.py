from __future__ import annotations

import argparse
import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import fitz

os.environ.setdefault("ANALYZE_ARTICLE_WORKERS", "1")

from backend.analyzer_v2 import analyze_v2  # noqa: E402


BASE_DIR = Path("backend/generated/assembly_rag_seed_age21_50/files")
DEFAULT_BILLS = ["2126635", "2126636", "2126639", "2126640", "2126648"]


def _pdf_text(path: Path) -> str:
    with fitz.open(path) as doc:
        return "\n".join(page.get_text() for page in doc)


def _parse_first_cost_table(text: str) -> dict[str, Any]:
    marker = re.search(r"2025\s+2026\s+2027\s+2028\s+2029\s+합계\s+(?:평균|연평균)", text)
    if not marker:
        return {"years": [], "total": None, "average": None, "raw": ""}
    block = text[marker.end(): marker.end() + 900]
    block = re.split(r"\n\s*(?:주:|자료:|\[표|\u203b)", block, maxsplit=1)[0]
    numbers = [int(n.replace(",", "")) for n in re.findall(r"\d{1,3}(?:,\d{3})*|\d+", block)]
    if len(numbers) < 7:
        return {"years": [], "total": None, "average": None, "raw": block.strip()}
    values = numbers[-7:]
    return {
        "years": values[:5],
        "total": values[5],
        "average": values[6],
        "raw": block.strip(),
    }


def _system_amounts(result: dict[str, Any]) -> dict[str, Any]:
    estimate = result.get("estimate") or result.get("if_needs_estimate") or {}
    year_rows = estimate.get("year_estimates") or []
    years: list[int | None] = []
    for row in year_rows[:5]:
        amount = row.get("amount_thousand") if isinstance(row, dict) else None
        try:
            years.append(None if amount is None else int(round(float(amount) / 1000)))
        except (TypeError, ValueError):
            years.append(None)
    total = estimate.get("total_amount_thousand")
    average = estimate.get("average_amount_thousand")
    return {
        "years": years,
        "total": None if total is None else int(round(float(total) / 1000)),
        "average": None if average is None else int(round(float(average) / 1000)),
        "unit": "백만원",
        "status": estimate.get("calculation_status"),
        "items": [item.get("name") for item in estimate.get("items") or []],
    }


def _match_level(official: dict[str, Any], system: dict[str, Any]) -> str:
    official_years = official.get("years") or []
    system_years = system.get("years") or []
    if official_years and official_years == system_years[:5]:
        return "exact"
    if official_years and len(system_years) >= 5 and all(v is not None for v in system_years[:5]):
        diffs = [abs(a - int(b)) for a, b in zip(official_years, system_years[:5])]
        denom = max(1, sum(official_years))
        if sum(diffs) / denom <= 0.05:
            return "near"
        return "wrong_amount"
    if system_years and any(v is not None for v in system_years):
        return "partial"
    return "miss"


def evaluate_bill(bill_no: str, out_dir: Path) -> dict[str, Any]:
    bill_dir = BASE_DIR / bill_no
    bill_pdf = bill_dir / "bill_text_의안원문.pdf"
    answer_pdf = bill_dir / "cost_estimate_비용추계서.pdf"
    started = time.time()
    content = base64.b64encode(bill_pdf.read_bytes()).decode("ascii")
    result = analyze_v2(bill_pdf.name, content, form_type="assembly")
    elapsed = round(time.time() - started, 1)
    official = _parse_first_cost_table(_pdf_text(answer_pdf))
    system = _system_amounts(result)
    row = {
        "bill_no": bill_no,
        "elapsed_sec": elapsed,
        "match_level": _match_level(official, system),
        "official": official,
        "system": system,
        "verdict": result.get("verdict"),
        "doc_type": result.get("docType") or result.get("doc_type"),
        "workflow_issues": (result.get("workflow") or {}).get("issues") or result.get("workflow_issues") or [],
    }
    (out_dir / f"{bill_no}_analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bill_no", nargs="*", default=DEFAULT_BILLS)
    parser.add_argument("--out", default="/private/tmp/assembly_eval_batch")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for bill_no in args.bill_no:
        try:
            rows.append(evaluate_bill(bill_no, out_dir))
        except Exception as exc:  # noqa: BLE001
            rows.append({"bill_no": bill_no, "error": str(exc), "match_level": "error"})
    summary = {"bills": args.bill_no, "rows": rows}
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
