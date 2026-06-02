from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import GENERATED_DIR


ASSUMPTION_CANDIDATES_PATH = (
    GENERATED_DIR / "assembly_assumptions" / "assembly_assumption_candidates.jsonl"
)

ASSUMPTION_LABELS = {
    "public_official_wage_growth_rate": "공무원임금상승률",
    "nominal_wage_growth_rate": "명목임금상승률",
    "consumer_price_growth_rate": "소비자물가상승률",
    "employer_contribution_rate": "기관부담요율",
    "basic_expense_ratio": "기본경비 비율",
    "asset_acquisition_unit_cost": "자산취득비 단가",
    "staffing_count": "소요인력",
    "grade_salary": "직급별 보수",
    "committee_operating_cost": "위원회 운영비",
}

VARIABLE_TO_KEY = {
    "공무원임금상승률": "public_official_wage_growth_rate",
    "공무원보수상승률": "public_official_wage_growth_rate",
    "명목임금상승률": "nominal_wage_growth_rate",
    "소비자물가상승률": "consumer_price_growth_rate",
    "물가상승률": "consumer_price_growth_rate",
}

KEY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("employer_contribution_rate", re.compile(r"기관부담|부담요율|부담률|사회보험")),
    ("basic_expense_ratio", re.compile(r"기본경비|인건비\s*대비|운영경비\s*비율")),
    ("asset_acquisition_unit_cost", re.compile(r"자산취득|비품|집기|PC")),
    ("staffing_count", re.compile(r"소요인력|증원인력|지원인력|정원|배치|채용|인원")),
    ("grade_salary", re.compile(r"직급|보수|봉급|급여|연봉|인건비")),
    ("committee_operating_cost", re.compile(r"위원회|심의회|협의회|특별위원회|운영비|사업비|회의수당")),
    ("consumer_price_growth_rate", re.compile(r"물가|운영비|사업비|자산취득")),
    ("public_official_wage_growth_rate", re.compile(r"공무원|보수|인건비")),
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


@lru_cache(maxsize=1)
def load_assumption_candidates() -> list[dict[str, Any]]:
    rows = _read_jsonl(ASSUMPTION_CANDIDATES_PATH)
    counts = Counter(
        (
            row.get("assumption_key"),
            row.get("primary_year"),
            row.get("value"),
            row.get("unit"),
        )
        for row in rows
    )
    for row in rows:
        row["repeat_count"] = counts[
            (
                row.get("assumption_key"),
                row.get("primary_year"),
                row.get("value"),
                row.get("unit"),
            )
        ]
    return rows


def _tokens(text: str) -> set[str]:
    compact = re.sub(r"\s+", "", text.lower())
    if len(compact) < 2:
        return {compact} if compact else set()
    return {compact[i:i + 2] for i in range(len(compact) - 1)}


def _overlap(a: str, b: str) -> float:
    ta = _tokens(a)
    tb = _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _wanted_keys(item: dict[str, Any]) -> list[str]:
    keys: list[str] = []

    calc = item.get("calculation") or {}
    if isinstance(calc, dict):
        growth = str(calc.get("growth_variable") or "").strip()
        if growth in VARIABLE_TO_KEY:
            keys.append(VARIABLE_TO_KEY[growth])

    for var in item.get("variables_needed") or []:
        clean = str(var).strip()
        if clean in VARIABLE_TO_KEY:
            keys.append(VARIABLE_TO_KEY[clean])

    text = " ".join(
        str(part or "")
        for part in [
            item.get("name"),
            item.get("category"),
            item.get("formula"),
            item.get("trigger_ref"),
            " ".join(str(v) for v in item.get("variables_needed") or []),
        ]
    )
    for key, pattern in KEY_PATTERNS:
        if pattern.search(text):
            keys.append(key)

    out: list[str] = []
    for key in keys:
        if key not in out:
            out.append(key)
    return out[:6]


def find_assumption_candidates(
    item: dict[str, Any],
    *,
    form_type: str = "assembly",
    limit: int = 8,
) -> list[dict[str, Any]]:
    wanted = _wanted_keys(item)
    if not wanted:
        return []

    current_year = datetime.now().year
    query = " ".join(
        str(part or "")
        for part in [
            item.get("name"),
            item.get("category"),
            item.get("formula"),
            " ".join(str(v) for v in item.get("variables_needed") or []),
        ]
    )
    ranked: list[dict[str, Any]] = []
    for row in load_assumption_candidates():
        key = row.get("assumption_key")
        if key not in wanted:
            continue

        source_text = str(row.get("source_text") or "")
        candidate_text = " ".join(
            str(part or "")
            for part in [
                row.get("variable_name"),
                row.get("item_name"),
                row.get("item_category"),
                source_text[:300],
            ]
        )

        score = 0.25 + 0.04 * min(int(row.get("repeat_count") or 1), 10)
        if key == wanted[0]:
            score += 0.2
        score += min(0.35, _overlap(query, candidate_text))

        year = row.get("primary_year")
        try:
            year_int = int(year) if year else None
        except (TypeError, ValueError):
            year_int = None
        if year_int == current_year:
            score += 0.15
        elif year_int and abs(year_int - current_year) <= 1:
            score += 0.08
        if form_type == "assembly":
            if key in {"basic_expense_ratio", "committee_operating_cost"}:
                if "국회" in candidate_text or "상임위원회" in candidate_text:
                    score += 0.3
                if "지방자치단체" in candidate_text or "지방의회" in candidate_text:
                    score -= 0.2

        ranked.append({
            "assumption_key": key,
            "label": ASSUMPTION_LABELS.get(str(key), str(key)),
            "variable_name": row.get("variable_name"),
            "value": row.get("value"),
            "unit": row.get("unit"),
            "year": year,
            "mentioned_years": row.get("mentioned_years") or [],
            "repeat_count": row.get("repeat_count") or 1,
            "bill_no": row.get("bill_no"),
            "bill_name": row.get("bill_name"),
            "item_name": row.get("item_name"),
            "source_text": source_text,
            "score": round(score, 3),
        })

    if not ranked:
        return []

    unique: dict[tuple[Any, Any, Any, Any, Any], dict[str, Any]] = {}
    for row in ranked:
        unique_key = (
            row.get("assumption_key"),
            row.get("year"),
            row.get("value"),
            row.get("unit"),
            row.get("bill_no"),
        )
        current = unique.get(unique_key)
        if not current or float(row.get("score") or 0) > float(current.get("score") or 0):
            unique[unique_key] = row

    return sorted(unique.values(), key=lambda r: float(r.get("score") or 0), reverse=True)[:limit]
