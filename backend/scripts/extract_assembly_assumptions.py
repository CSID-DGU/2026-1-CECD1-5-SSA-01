"""Extract reusable National Assembly cost-estimate assumption candidates.

Input is the TAG output produced by extract_tag_structures.py:
  - cost_estimate_structures.jsonl
  - cost_estimate_items.jsonl
  - cost_estimate_variables.jsonl

Output:
  - assembly_assumption_candidates.jsonl
  - assembly_assumption_summary.json
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from backend.config import GENERATED_DIR


DEFAULT_SEED_DIR = GENERATED_DIR / "assembly_rag_seed_22_ce"
DEFAULT_OUTPUT_DIR = GENERATED_DIR / "assembly_assumptions"

YEAR_RE = re.compile(r"(20\d{2})")


ASSUMPTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "public_official_wage_growth_rate",
        re.compile(r"공무원.*(임금|보수).*(상승|인상)|공무원.*평균상승률"),
    ),
    (
        "nominal_wage_growth_rate",
        re.compile(r"명목임금상승률|명목\s*임금.*상승"),
    ),
    (
        "consumer_price_growth_rate",
        re.compile(r"소비자물가|물가상승|물가지수|CPI"),
    ),
    (
        "employer_contribution_rate",
        re.compile(r"기관부담.*(요율|률)|기관부담금\s*요율|부담금\s*요율"),
    ),
    (
        "basic_expense_ratio",
        re.compile(r"기본경비.*(비율|비중)|인건비\s*대비\s*기본경비|보수액\s*대비\s*기본경비"),
    ),
    (
        "asset_acquisition_unit_cost",
        re.compile(r"1인당\s*자산취득비|자산취득비.*(단가|1인당)|정부기관\s*1인당\s*자산취득비"),
    ),
    (
        "staffing_count",
        re.compile(r"소요인력|증원인력|증원.*인력|지원인력|정원|배치|채용|인원"),
    ),
    (
        "grade_salary",
        re.compile(r"(직급별|[1-9]급|감사위원|특별검사|전문위원|입법조사관).*(보수|급여|연봉|봉급)"),
    ),
    (
        "committee_operating_cost",
        re.compile(r"위원회.*(운영비|운영경비|사업비|예산)|상임위원회.*(운영|경비)"),
    ),
)

MONEY_UNITS = {
    "원": 1,
    "천원": 1_000,
    "만원": 10_000,
    "백만원": 1_000_000,
    "억원": 100_000_000,
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def normalize_unit(unit: Any) -> str | None:
    if unit is None:
        return None
    text = str(unit).strip()
    if not text or text.lower() == "none":
        return None
    text = text.replace("％", "%")
    return re.sub(r"\s+", "", text)


def normalize_value(value: Any, unit: str | None) -> tuple[float | int | None, str | None]:
    if value is None:
        return None, unit
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None, unit

    if unit == "%":
        # Some TAG rows store 3.5% as 0.035 while still marking the unit as %.
        if 0 < abs(number) < 1:
            number *= 100
        return round(number, 6), "%"

    if unit in MONEY_UNITS:
        return int(round(number * MONEY_UNITS[unit])), "원"

    if unit in {"명", "개", "회", "년", "개월"}:
        return int(number) if number.is_integer() else number, unit

    return int(number) if number.is_integer() else number, unit


def extract_years(*texts: Any) -> list[str]:
    found: list[str] = []
    for text in texts:
        if text is None:
            continue
        found.extend(YEAR_RE.findall(str(text)))
    return sorted(set(found))


def primary_year(variable: dict[str, Any], mentioned_years: list[str]) -> str | None:
    name_years = extract_years(variable.get("variable_name"))
    if len(name_years) == 1:
        return name_years[0]
    if len(mentioned_years) == 1:
        return mentioned_years[0]
    return None


def classify(variable: dict[str, Any]) -> str | None:
    haystack = " ".join(
        str(variable.get(key) or "")
        for key in ("variable_name", "source_text", "variable_type")
    )
    for key, pattern in ASSUMPTION_PATTERNS:
        if pattern.search(haystack):
            return key
    return None


def value_matches_assumption(assumption_key: str, unit: str | None) -> bool:
    if assumption_key.endswith("_growth_rate") or assumption_key in {
        "employer_contribution_rate",
        "basic_expense_ratio",
    }:
        return unit == "%"
    if assumption_key in {"asset_acquisition_unit_cost", "grade_salary"}:
        return unit == "원"
    if assumption_key == "staffing_count":
        return bool(unit and "명" in unit)
    if assumption_key == "committee_operating_cost":
        return bool(unit and ("원" in unit or unit in {"만원", "백만원", "억원", "천원"}))
    return True


def build_candidates(seed_dir: Path) -> list[dict[str, Any]]:
    structures = {
        row["struct_id"]: row
        for row in read_jsonl(seed_dir / "cost_estimate_structures.jsonl")
        if row.get("struct_id")
    }
    items = {
        row["item_id"]: row
        for row in read_jsonl(seed_dir / "cost_estimate_items.jsonl")
        if row.get("item_id")
    }

    candidates: list[dict[str, Any]] = []
    for variable in read_jsonl(seed_dir / "cost_estimate_variables.jsonl"):
        assumption_key = classify(variable)
        if not assumption_key:
            continue

        unit = normalize_unit(variable.get("variable_unit"))
        value, normalized_unit = normalize_value(variable.get("variable_value"), unit)
        if value is None:
            continue
        if not value_matches_assumption(assumption_key, normalized_unit):
            continue

        item = items.get(variable.get("item_id"), {})
        structure = structures.get(variable.get("struct_id"), {})
        years = extract_years(
            variable.get("variable_name"),
            variable.get("source_text"),
        )

        candidates.append({
            "assumption_key": assumption_key,
            "variable_name": variable.get("variable_name"),
            "value": value,
            "unit": normalized_unit,
            "original_value": variable.get("variable_value"),
            "original_unit": unit,
            "mentioned_years": years,
            "primary_year": primary_year(variable, years),
            "source_text": variable.get("source_text"),
            "variable_type": variable.get("variable_type"),
            "bill_id": variable.get("bill_id") or structure.get("bill_id"),
            "bill_no": structure.get("bill_no"),
            "bill_name": structure.get("bill_name"),
            "age": structure.get("age"),
            "committee": structure.get("committee"),
            "propose_date": structure.get("propose_date"),
            "item_id": variable.get("item_id"),
            "item_name": item.get("item_name"),
            "item_category": item.get("item_category"),
            "trigger_ref": item.get("trigger_ref"),
        })
    return candidates


def summarize(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        by_key[row["assumption_key"]].append(row)

    summary: dict[str, Any] = {
        "total_candidates": len(candidates),
        "by_assumption_key": {},
    }

    for key, rows in sorted(by_key.items()):
        value_counter: Counter[tuple[Any, Any, Any]] = Counter()
        examples: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
        for row in rows:
            year_key = row.get("primary_year") or ",".join(row.get("mentioned_years") or []) or None
            counter_key = (year_key, row.get("value"), row.get("unit"))
            value_counter[counter_key] += 1
            examples.setdefault(counter_key, {
                "bill_no": row.get("bill_no"),
                "bill_name": row.get("bill_name"),
                "item_name": row.get("item_name"),
                "variable_name": row.get("variable_name"),
                "source_text": row.get("source_text"),
            })

        top_values = []
        for (year, value, unit), count in value_counter.most_common(20):
            top_values.append({
                "year": year,
                "value": value,
                "unit": unit,
                "count": count,
                "example": examples[(year, value, unit)],
            })

        summary["by_assumption_key"][key] = {
            "count": len(rows),
            "unique_values": len(value_counter),
            "top_values": top_values,
        }
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract assembly assumption candidates from TAG JSONL.")
    parser.add_argument("--seed-dir", type=Path, default=DEFAULT_SEED_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    candidates = build_candidates(args.seed_dir)
    summary = summarize(candidates)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "assembly_assumption_candidates.jsonl", candidates)
    (args.output_dir / "assembly_assumption_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps({
        "seed_dir": str(args.seed_dir),
        "output_dir": str(args.output_dir),
        "total_candidates": len(candidates),
        "by_assumption_key": {
            key: value["count"]
            for key, value in summary["by_assumption_key"].items()
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
