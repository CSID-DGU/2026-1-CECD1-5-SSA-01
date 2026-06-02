from __future__ import annotations

from statistics import median
from typing import Any


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rate_average(kosis_lookup: dict[str, Any] | None) -> float | None:
    if not kosis_lookup:
        return None
    values: list[float] = []
    for row in kosis_lookup.get("year_values") or []:
        value = _to_float(row.get("value"))
        if value is not None:
            values.append(value)
    if not values:
        return None
    return sum(values) / len(values) / 100


def _lookup_by_variable(item: dict[str, Any], variable: str | None) -> dict[str, Any] | None:
    if not variable:
        return None
    for lookup in item.get("kosis_lookups") or []:
        if lookup.get("variable") == variable:
            return lookup
    return None


def _string_similarity(a: str, b: str) -> float:
    def tokens(text: str) -> set[str]:
        words = {token for token in text.lower().split() if token}
        compact = "".join(words)
        if len(compact) >= 2:
            words |= {compact[i:i + 2] for i in range(len(compact) - 1)}
        return words

    a_tokens = tokens(a)
    b_tokens = tokens(b)
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / len(a_tokens | b_tokens)


def _amount_candidates_from_patterns(item: dict[str, Any], tag_patterns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    item_name = str(item.get("name") or "")
    category = str(item.get("category") or "")
    candidates: list[dict[str, Any]] = []

    for pattern in tag_patterns:
        for tagged_item in pattern.get("items") or []:
            amount_rows = tagged_item.get("amounts") or []
            amount = None
            total_row = next((row for row in amount_rows if row.get("is_total")), None)
            if total_row and _to_float(total_row.get("amount_thousand")) is not None:
                amount = int(round(float(total_row["amount_thousand"]) / 5))
            else:
                annual_rows = [
                    _to_float(row.get("amount_thousand"))
                    for row in amount_rows
                    if not row.get("is_total") and _to_float(row.get("amount_thousand")) is not None
                ]
                if annual_rows:
                    amount = int(round(median(annual_rows)))

            if amount is None or amount <= 0:
                continue

            score = 0.0
            tagged_category = str(tagged_item.get("category") or "")
            tagged_name = str(tagged_item.get("name") or "")
            if category and tagged_category and category == tagged_category:
                score += 0.5
            score += _string_similarity(item_name, tagged_name)
            if score < 0.25:
                continue
            formula = next(
                (row.get("formula") for row in amount_rows if row.get("formula")),
                "",
            )
            candidates.append({
                "score": round(score, 3),
                "amount_thousand": amount,
                "bill_no": pattern.get("bill_no"),
                "bill_name": pattern.get("bill_name"),
                "category": tagged_category,
                "name": tagged_name,
                "formula": formula,
            })

    if not candidates:
        return []
    candidates.sort(key=lambda row: row["score"], reverse=True)
    best_score = candidates[0]["score"]
    return [row for row in candidates if row["score"] >= max(0.35, best_score * 0.6)][:5]


def _apply_tag_fallback(item: dict[str, Any], tag_patterns: list[dict[str, Any]], years: int) -> float | None:
    candidates = _amount_candidates_from_patterns(item, tag_patterns)
    if not candidates:
        return None
    amounts = [int(candidate["amount_thousand"]) for candidate in candidates]
    amount = float(median(amounts))
    item.setdefault("calculation", {})
    item["calculation"]["base_amount_thousand"] = int(round(amount))
    item["calculation"].setdefault("recurrence", "annual")
    item["calculation"].setdefault("start_year", 1)
    item["calculation"].setdefault("end_year", years)
    item["calculation"]["source_note"] = "TAG 유사 비용추계서 금액 중앙값 기반 추정"
    item["requires_review"] = True
    item["review_reason"] = "통계/명시 수치가 부족해 유사 비용추계서 TAG 금액으로 산정"
    item["evidence_basis"] = {
        "type": "tag_median",
        "label": "유사 비용추계서 TAG 중앙값",
        "amount_candidates": candidates,
    }
    return amount


def compute_year_estimates(
    estimate: dict[str, Any],
    *,
    years: int = 5,
    tag_patterns: list[dict[str, Any]] | None = None,
    allow_estimated: bool = True,
) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]]]:
    """Compute estimate totals with deterministic arithmetic only.

    Supported item calculation schema:
      {
        "base_amount_thousand": 120000,
        "recurrence": "annual" | "one_time",
        "start_year": 1,
        "end_year": 5,
        "growth_variable": "소비자물가상승률" | null
      }

    If allow_estimated is true, missing base amounts can fall back to the
    median annual amount from similar TAG structures. Those rows are marked
    requires_review so the UI can clearly show that confirmation is needed.
    """
    items = estimate.get("items") or []
    if not items:
        return None, []

    totals = [0] * years
    issues: list[dict[str, Any]] = []
    any_computed = False

    for index, item in enumerate(items, 1):
        calc = item.get("calculation") or {}
        if not isinstance(calc, dict):
            calc = {}

        base_amount = _to_float(calc.get("base_amount_thousand"))
        recurrence = str(calc.get("recurrence") or "unknown")
        start_year = int(_to_float(calc.get("start_year")) or 1)
        end_year = int(_to_float(calc.get("end_year")) or years)
        growth_variable = calc.get("growth_variable")

        item_name = str(item.get("name") or f"항목 {index}")
        if base_amount is None and allow_estimated:
            base_amount = _apply_tag_fallback(item, tag_patterns or [], years)
            if base_amount is not None:
                calc = item.get("calculation") or {}
                recurrence = str(calc.get("recurrence") or "annual")
                start_year = int(_to_float(calc.get("start_year")) or 1)
                end_year = int(_to_float(calc.get("end_year")) or years)
                issues.append({
                    "item": item_name,
                    "level": "warn",
                    "reason": "TAG 유사사례 기반 추정값 사용",
                    "requires_review": True,
                })
        if base_amount is None:
            issues.append({
                "item": item_name,
                "level": "error",
                "reason": "base_amount_thousand 누락",
            })
            item["year_amounts_thousand"] = [None] * years
            continue
        if recurrence not in {"annual", "one_time"}:
            issues.append({
                "item": item_name,
                "level": "error",
                "reason": "recurrence는 annual 또는 one_time이어야 함",
            })
            item["year_amounts_thousand"] = [None] * years
            continue
        if start_year < 1 or end_year < start_year:
            issues.append({
                "item": item_name,
                "level": "error",
                "reason": "start_year/end_year 범위 오류",
            })
            item["year_amounts_thousand"] = [None] * years
            continue

        growth_rate = 0.0
        if growth_variable:
            growth_rate_value = _rate_average(_lookup_by_variable(item, str(growth_variable)))
            if growth_rate_value is None:
                issues.append({
                    "item": item_name,
                    "level": "warn" if item.get("requires_review") else "error",
                    "reason": f"증가율 변수 조회값 없음: {growth_variable}",
                })
                if not item.get("requires_review"):
                    item["year_amounts_thousand"] = [None] * years
                    continue
                growth_rate_value = 0.0
            growth_rate = growth_rate_value

        item_amounts: list[int | None] = []
        for year_index in range(years):
            year_no = year_index + 1
            amount = 0.0
            if recurrence == "one_time":
                if year_no == start_year:
                    amount = base_amount
            elif start_year <= year_no <= min(end_year, years):
                amount = base_amount * ((1 + growth_rate) ** max(0, year_no - start_year))

            rounded = int(round(amount))
            item_amounts.append(rounded)
            totals[year_index] += rounded

        item["year_amounts_thousand"] = item_amounts
        any_computed = True

    if not any_computed:
        return None, issues

    year_estimates = [
        {
            "year": index + 1,
            "amount_thousand": amount,
            "note": "Python 계산기 산출",
            "missing_vars": [],
            "requires_review": any(item.get("requires_review") for item in items),
        }
        for index, amount in enumerate(totals)
    ]
    return year_estimates, issues
