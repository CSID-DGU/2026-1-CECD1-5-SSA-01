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


def _headline_total_million(section: str) -> int | None:
    """Parse the prose headline total ("총 130억 6,600만원") to 백만원.

    The five-year summary table is read from a PDF whose extraction frequently
    merges the last year cell and the row total onto one line
    (e.g. "2,680 12,726"), which silently breaks positional cell alignment and
    makes the heuristic return a per-year figure as the total.  The headline
    sentence states the same total in a fixed prose form and is unit-explicit,
    so it is the more reliable source.  Handles compound Korean amounts
    (조/억/만/천 segments), not just a single unit.
    """
    match = re.search(
        r"총\s*((?:[0-9][0-9,]*\s*(?:조|억|만|천)\s*)+)원",
        section,
    )
    if not match:
        return None
    unit_to_million = {"조": 1_000_000, "억": 100, "만": 0.01, "천": 0.001}
    total = 0.0
    found = False
    for number, unit in re.findall(r"([0-9][0-9,]*)\s*(조|억|만|천)", match.group(1)):
        total += float(number.replace(",", "")) * unit_to_million[unit]
        found = True
    return int(round(total)) if found else None


def _parse_first_cost_table(text: str) -> dict[str, Any]:
    """Read the summary cost table, never a later statistics table.

    Cost-estimate PDFs contain many five-year tables.  Matching only a year
    header can therefore mistake historical meeting counts or beneficiary
    statistics for money.  Restrict extraction to ``Ⅰ. 비용추계 결과`` and
    require the table's monetary unit before reading numeric-only cells.
    Returned values are normalised to 백만원.
    """

    def to_million(value: float, unit: str) -> int:
        multipliers = {
            "조원": 1_000_000,
            "억원": 100,
            "백만원": 1,
            "만원": 0.01,
            "천원": 0.001,
            "원": 0.000001,
        }
        return int(round(value * multipliers[unit]))

    section_start = re.search(
        r"(?:Ⅰ|I)\s*[.．]?\s*비용추계\s*결과",
        text,
        re.IGNORECASE,
    )
    if not section_start:
        return {"years": [], "total": None, "average": None, "raw": ""}
    tail = text[section_start.end():]
    section_end = re.search(
        r"\n\s*(?:Ⅱ|II)\s*[.．]?\s*재정수반요인",
        tail,
        re.IGNORECASE,
    )
    section = tail[: section_end.start()] if section_end else tail[:5_000]
    unit_match = re.search(
        r"단위\s*:\s*(조원|억원|백만원|만원|천원|원)",
        section,
    )
    if not unit_match:
        return {"years": [], "total": None, "average": None, "raw": section.strip()}
    unit = unit_match.group(1)
    # Prefer the prose headline total; the table cell heuristic below is only a
    # fallback for years (and for the rare report with no headline sentence).
    headline_total = _headline_total_million(section)

    marker = re.search(
        r"((?:20\d{2}\s+){1,5})(?:합\s*계|계)(?:\s*(?:평균|연평균))?",
        section,
    )
    if marker:
        year_count = len(re.findall(r"20\d{2}", marker.group(1)))
        table = section[marker.end():]
        table = re.split(
            r"\n\s*(?:주\s*:|자료\s*:|\[표|\u203b)",
            table,
            maxsplit=1,
        )[0]
        numeric_cells = [
            float(line.strip().replace(",", ""))
            for line in table.splitlines()
            if re.fullmatch(
                r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?",
                line.strip(),
            )
        ]
        has_average = bool(
            re.search(r"(?:합\s*계|계)\s*(?:평균|연평균)", marker.group(0))
        )
        width = year_count + 1 + int(has_average)
        if len(numeric_cells) >= width:
            values = numeric_cells[-width:]
            years = [
                to_million(value, unit)
                for value in values[:year_count]
            ]
            total = (
                headline_total
                if headline_total is not None
                else to_million(values[year_count], unit)
            )
            average = (
                to_million(values[year_count + 1], unit)
                if has_average
                else int(round(total / year_count))
            )
            return {
                "years": years,
                "total": total,
                "average": average,
                "raw": table.strip(),
            }

    # Table cells were unusable (merged/misaligned).  Fall back to the prose
    # headline total, which needs no positional alignment.
    if headline_total is not None:
        return {
            "years": [],
            "total": headline_total,
            "average": int(round(headline_total / 5)),
            "raw": section.strip(),
        }

    # Some reports state a total in prose without a machine-readable table.
    narrative = re.search(
        r"총\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)\s*"
        r"(조원|억원|백만원|만원|천원|원)",
        section,
    )
    if narrative:
        total = to_million(
            float(narrative.group(1).replace(",", "")),
            narrative.group(2),
        )
        return {
            "years": [],
            "total": total,
            "average": int(round(total / 5)),
            "raw": section.strip(),
        }
    return {"years": [], "total": None, "average": None, "raw": section.strip()}


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
    year_count = len(official_years)
    if official_years and official_years == system_years[:year_count]:
        return "exact"
    if (
        official_years
        and len(system_years) >= year_count
        and all(v is not None for v in system_years[:year_count])
    ):
        diffs = [
            abs(a - int(b))
            for a, b in zip(official_years, system_years[:year_count])
        ]
        denom = max(1, sum(official_years))
        if sum(diffs) / denom <= 0.05:
            return "near"
        return "wrong_amount"
    if system_years and any(v is not None for v in system_years):
        return "partial"
    return "miss"


def _find_pdf(bill_dir: Path, *, answer: bool) -> Path:
    candidates = []
    for path in bill_dir.glob("*.pdf"):
        name = path.name
        if answer:
            if ("비용추계서" in name or "cost_estimate" in name) and "미첨부" not in name:
                candidates.append(path)
        elif "의안원문" in name or "bill_text" in name:
            candidates.append(path)
    if not candidates:
        kind = "official cost estimate" if answer else "source bill"
        raise FileNotFoundError(f"{bill_dir}: {kind} PDF not found")
    return sorted(candidates, key=lambda path: path.name)[0]


def _evidence_bill_nos(result: dict[str, Any]) -> set[str]:
    """Collect source bill numbers, excluding holdout audit metadata."""
    found: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"bill_no", "source_bill_no"} and child:
                    found.add(str(child))
                else:
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(result.get("references") or {})
    walk(result.get("estimate") or {})
    return found


def evaluate_bill(bill_no: str, out_dir: Path) -> dict[str, Any]:
    bill_dir = BASE_DIR / bill_no
    bill_pdf = _find_pdf(bill_dir, answer=False)
    answer_pdf = _find_pdf(bill_dir, answer=True)
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
        "holdout": (result.get("workflow") or {}).get("rag") or {},
        "evidence_leak": bill_no in _evidence_bill_nos(result),
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
