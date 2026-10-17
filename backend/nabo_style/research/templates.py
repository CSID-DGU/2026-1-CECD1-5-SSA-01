"""Budget-item templates in NABO's own decomposition.

Amounts are in thousand KRW. Every input arrives as {"value", "source"};
templates never invent numbers.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping


def _v(inputs: Mapping[str, Any], key: str):
    try:
        return inputs[key]["value"]
    except KeyError as exc:
        raise KeyError(f"missing input: {key}") from exc


def _growth_path(rates: Mapping[int, float], base_year: int, years: list[int]) -> list[float]:
    """Cumulative factor from base_year to each year; rates in percent."""
    out = []
    for year in years:
        factor = 1.0
        for step in range(base_year + 1, year + 1):
            if step not in rates:
                raise KeyError(f"growth rate missing for {step}")
            factor *= 1 + rates[step] / 100
        out.append(factor)
    return out


def org_personnel(years: list[int], inputs: Mapping[str, Any]) -> dict[str, list[float]]:
    """보수 → 기관부담금 → 기본경비(보수+부담금 기준) → 자산취득비(첫해)."""
    headcount = _v(inputs, "headcount_by_grade")
    pay = _v(inputs, "pay_by_grade_thousand")
    base_year = int(_v(inputs, "pay_base_year"))
    growth = _growth_path({int(k): v for k, v in _v(inputs, "wage_growth_pct").items()}, base_year, years)
    base = sum(headcount[g] * pay[g] for g in headcount)
    salary = [base * f for f in growth]
    rate = {int(k): v for k, v in _v(inputs, "employer_rate_pct").items()}
    employer = [s * rate[y] / 100 for s, y in zip(salary, years)]
    ratio = _v(inputs, "basic_expense_ratio")
    basic = [(s + e) * ratio for s, e in zip(salary, employer)]
    asset_price = {int(k): v for k, v in _v(inputs, "asset_per_person_thousand").items()}
    heads = sum(headcount.values())
    asset = [heads * asset_price[years[0]]] + [0.0] * (len(years) - 1)
    return {"보수": salary, "기관부담금": employer, "기본경비": basic, "자산취득비": asset}


def committee_allowance(years: list[int], inputs: Mapping[str, Any]) -> dict[str, list[float]]:
    members = _v(inputs, "paid_members")
    meetings = _v(inputs, "meetings_per_year")
    unit = _v(inputs, "allowance_per_meeting_thousand")
    return {"회의참석수당": [members * meetings * unit] * len(years)}


def precedent_package(years: list[int], inputs: Mapping[str, Any]) -> dict[str, list[float]]:
    """Whole precedent budget reused in the years it recurs (no re-pricing)."""
    amount = _v(inputs, "package_amount_thousand")
    occurs = set(_v(inputs, "occurrence_years"))
    return {"유사사례 준용": [amount if y in occurs else 0.0 for y in years]}


def annual_with_growth(years: list[int], inputs: Mapping[str, Any]) -> dict[str, list[float]]:
    base = _v(inputs, "base_amount_thousand")
    base_year = int(_v(inputs, "base_year"))
    rates = {int(k): v for k, v in (inputs.get("growth_pct", {}).get("value") or {}).items()}
    path = _growth_path(rates, base_year, years) if rates else [1.0] * len(years)
    return {"연간사업비": [base * f for f in path]}


def tax_base_rate(years: list[int], inputs: Mapping[str, Any]) -> dict[str, list[float]]:
    base = _v(inputs, "tax_base_thousand")
    rate = _v(inputs, "rate_change")
    local = inputs.get("local_surtax_ratio", {}).get("value", 0.0)
    national = [-base * rate] * len(years)
    out = {"국세": national}
    if local:
        out["지방세"] = [n * local for n in national]
    return out


def transfer_recipients(years: list[int], inputs: Mapping[str, Any]) -> dict[str, list[float]]:
    """Σ(group recipients × benefit) in the payment years (amounts in thousand KRW)."""
    groups = _v(inputs, "groups")  # {name: [recipients, benefit_thousand]}
    pay = set(_v(inputs, "payment_years"))
    return {name: [n * amount if y in pay else 0.0 for y in years] for name, (n, amount) in groups.items()}


def precedent_path_shift(years: list[int], inputs: Mapping[str, Any]) -> dict[str, list[float]]:
    """A precedent's annual path for the same measure, moved by the sunset shift
    and re-priced by a growth factor (e.g. a later sunset of the same tax relief)."""
    path = {int(y) + int(_v(inputs, "shift_years")): v
            for y, v in _v(inputs, "precedent_path_thousand").items()}
    factor = _v(inputs, "price_factor")
    return {"선례경로 이동": [path.get(y, 0.0) * factor for y in years]}


TEMPLATES: dict[str, Callable[[list[int], Mapping[str, Any]], dict[str, list[float]]]] = {
    "org_personnel": org_personnel,
    "committee_allowance": committee_allowance,
    "precedent_package": precedent_package,
    "annual_with_growth": annual_with_growth,
    "tax_base_rate": tax_base_rate,
    "precedent_path_shift": precedent_path_shift,
    "transfer_recipients": transfer_recipients,
}
