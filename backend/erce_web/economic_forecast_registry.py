"""Versioned official economic-forecast series used by cost formulas.

Forecast vintages must not be mixed. A calculation records one series key,
its publication date and the rates actually applied to each calendar year.
Rates are stored as ratios (3.8% == 0.038), not display percentages.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ForecastSeries:
    key: str
    indicator: str
    published_at: str
    rates_by_year: dict[int, float]
    source: str
    source_ref: str
    extension_policy: str = "none"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


FORECAST_SERIES: dict[str, ForecastSeries] = {
    # Keep every vintage separate: a later forecast must not silently rewrite
    # an earlier estimate or historical backtest.
    "nabo_macro_2024_10_consumer_price": ForecastSeries(
        key="nabo_macro_2024_10_consumer_price",
        indicator="consumer_price_growth_rate",
        published_at="2024-10",
        rates_by_year={
            2025: 0.021,
            2026: 0.020,
            2027: 0.020,
            2028: 0.020,
            2029: 0.020,
        },
        source="국회예산정책처 경제전망(2024.10.)",
        source_ref="2025년 2.1%, 2026~2029년 2.0% 소비자물가상승률 전망",
    ),
    "nabo_nominal_wage_2025_07": ForecastSeries(
        key="nabo_nominal_wage_2025_07",
        indicator="nominal_wage_growth_rate",
        published_at="2025-07",
        rates_by_year={
            2026: 0.039,
            2027: 0.038,
            2028: 0.038,
            2029: 0.038,
            2030: 0.038,
            2031: 0.038,
        },
        source="국회예산정책처 명목임금상승률 전망(2025.7.)",
        source_ref=(
            "국회 의안 2212721 비용추계서 인용표: "
            "2026년 3.9%, 2027~2031년 3.8%"
        ),
    ),
    "nabo_macro_2025_09_nominal_wage": ForecastSeries(
        key="nabo_macro_2025_09_nominal_wage",
        indicator="nominal_wage_growth_rate",
        published_at="2025-09-25",
        rates_by_year={
            2025: 0.033,
            2026: 0.032,
            2027: 0.033,
            2028: 0.033,
            2029: 0.033,
        },
        source="국회예산정책처 2026년 NABO 경제전망: 2025~2029",
        source_ref="2025.9. 명목임금 상승률 전망표",
    ),
    "nabo_macro_2025_09_consumer_price": ForecastSeries(
        key="nabo_macro_2025_09_consumer_price",
        indicator="consumer_price_growth_rate",
        published_at="2025-09-25",
        rates_by_year={
            2025: 0.020,
            2026: 0.019,
            2027: 0.020,
            2028: 0.020,
            2029: 0.020,
        },
        source="국회예산정책처 2026년 NABO 경제전망: 2025~2029",
        source_ref="2025.9. 소비자물가 상승률 전망표",
    ),
}


def get_forecast_series(key: str) -> ForecastSeries:
    try:
        return FORECAST_SERIES[key]
    except KeyError as exc:
        raise KeyError(f"unknown forecast series: {key}") from exc


def growth_input_from_series(
    key: str,
    *,
    base_year: int,
    start_year: int,
    years: int,
) -> dict[str, dict[str, Any]]:
    """Return resolver inputs after proving that every needed year exists."""
    series = get_forecast_series(key)
    end_year = start_year + years - 1
    needed_years = range(base_year + 1, end_year + 1)
    missing = [year for year in needed_years if year not in series.rates_by_year]
    if missing:
        raise ValueError(
            f"forecast series {key} does not cover years: "
            + ", ".join(str(year) for year in missing)
        )
    source_ref = f"{series.source}; {series.source_ref}; series={series.key}"
    return {
        "base_year": {
            "value": base_year,
            "unit": "year",
            "source": "official_forecast_registry",
            "source_ref": source_ref,
        },
        "growth_rates_by_year": {
            "value": {
                str(year): series.rates_by_year[year]
                for year in needed_years
            },
            "unit": "ratio/year",
            "source": "official_forecast_registry",
            "source_ref": source_ref,
        },
    }


__all__ = [
    "FORECAST_SERIES",
    "ForecastSeries",
    "get_forecast_series",
    "growth_input_from_series",
]
