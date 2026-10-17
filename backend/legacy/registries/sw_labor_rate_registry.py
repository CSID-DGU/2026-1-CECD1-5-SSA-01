"""Versioned KOSA SW-technician wage tables.

The table is an official statistical average, not a mandatory tariff.  It is
used only when a current budget/contract/settlement amount is unavailable.
Every lookup is bound to an application year and, optionally, an as-of date so
future publications cannot leak into historical estimates.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class SWLaborRate:
    role_key: str
    role_label: str
    monthly_won: int
    daily_won: int
    hourly_won: int


@dataclass(frozen=True)
class SWLaborRateTable:
    application_year: int
    published_at: str
    effective_from: str
    effective_to: str
    source: str
    source_url: str
    rates: dict[str, SWLaborRate]


def _rate(key: str, label: str, monthly: int, daily: int, hourly: int) -> SWLaborRate:
    return SWLaborRate(key, label, monthly, daily, hourly)


SW_LABOR_RATE_TABLES: dict[int, SWLaborRateTable] = {
    2025: SWLaborRateTable(
        application_year=2025,
        published_at="2024-12-03",
        effective_from="2025-01-01",
        effective_to="2025-12-31",
        source="한국소프트웨어산업협회 2025년 적용 SW기술자 평균임금",
        source_url=(
            "https://www.sw.or.kr/site/sw/ex/board/"
            "View.do?bcIdx=61152&cbIdx=304&searchExt1="
        ),
        rates={
            row.role_key: row for row in (
                _rate("it_planner", "IT기획자", 11_597_656, 562_993, 70_374),
                _rate("it_consultant", "IT컨설턴트", 9_706_020, 471_166, 58_896),
                _rate("business_analyst", "업무분석가", 8_997_359, 436_765, 54_596),
                _rate("data_analyst", "데이터분석가", 7_751_183, 376_271, 47_034),
                _rate("it_pm", "IT PM", 9_145_473, 443_955, 55_494),
                _rate("it_architect", "IT아키텍트", 10_147_745, 492_609, 61_576),
                _rate("uiux_planner_developer", "UI/UX기획·개발자", 6_727_260, 326_566, 40_821),
                _rate("uiux_designer", "UI/UX디자이너", 5_176_203, 251_272, 31_409),
                _rate("application_sw_developer", "응용SW개발자", 6_943_457, 337_061, 42_133),
                _rate("system_sw_developer", "시스템SW개발자", 6_099_042, 296_070, 37_009),
                _rate("information_system_operator", "정보시스템운용자", 10_154_626, 492_943, 61_618),
                _rate("it_support_technician", "IT지원기술자", 5_058_021, 245_535, 30_692),
                _rate("it_marketer", "IT마케터", 11_056_617, 536_729, 67_091),
                _rate("it_quality_manager", "IT품질관리자", 9_692_094, 470_490, 58_811),
                _rate("it_tester", "IT테스터", 3_570_557, 173_328, 21_666),
                _rate("it_auditor", "IT감리", 10_351_376, 502_494, 62_812),
                _rate("information_security_specialist", "정보보안전문가", 9_857_100, 478_500, 59_813),
            )
        },
    ),
    2026: SWLaborRateTable(
        application_year=2026,
        published_at="2025-12-19",
        effective_from="2026-01-01",
        effective_to="2026-12-31",
        source="한국인공지능·소프트웨어산업협회 2026년 적용 SW기술자 평균임금",
        source_url=(
            "https://www.sw.or.kr/site/sw/ex/board/"
            "View.do?bcIdx=64717&cbIdx=304&searchExt1="
        ),
        rates={
            row.role_key: row for row in (
                _rate("it_planner", "IT기획자", 11_853_218, 578_206, 72_276),
                _rate("it_consultant", "IT컨설턴트", 10_707_960, 522_340, 65_292),
                _rate("business_analyst", "업무분석가", 9_740_667, 475_154, 59_394),
                _rate("data_analyst", "데이터분석가", 8_499_309, 414_600, 51_825),
                _rate("it_pm", "IT PM", 10_086_804, 492_039, 61_505),
                _rate("it_architect", "IT아키텍트", 11_103_230, 541_621, 67_703),
                _rate("uiux_planner_developer", "UI/UX기획·개발자", 6_901_660, 336_666, 42_083),
                _rate("uiux_designer", "UI/UX디자이너", 5_159_246, 251_671, 31_459),
                _rate("application_sw_developer", "응용SW개발자", 7_754_124, 378_250, 47_281),
                _rate("system_sw_developer", "시스템SW개발자", 5_840_196, 284_888, 35_611),
                _rate("information_system_operator", "정보시스템운용자", 10_649_117, 519_469, 64_934),
                _rate("it_support_technician", "IT지원기술자", 5_170_016, 252_196, 31_524),
                _rate("it_marketer", "IT마케터", 11_793_500, 575_293, 71_912),
                _rate("it_quality_manager", "IT품질관리자", 11_042_071, 538_638, 67_330),
                _rate("it_tester", "IT테스터", 4_053_137, 197_714, 24_714),
                _rate("it_auditor", "IT감리", 11_745_154, 572_934, 71_617),
                _rate("information_security_specialist", "정보보안전문가", 10_411_680, 507_887, 63_486),
            )
        },
    ),
}


ROLE_ALIASES = {
    "정보시스템운용자": "information_system_operator",
    "IT시스템운용자": "information_system_operator",
    "데이터베이스운용자": "information_system_operator",
    "NW엔지니어": "information_system_operator",
    "IT지원기술자": "it_support_technician",
    "헬프데스크": "it_support_technician",
    "응용SW개발자": "application_sw_developer",
    "시스템SW개발자": "system_sw_developer",
    "정보보안전문가": "information_security_specialist",
}


def _iso_date(value: str) -> date:
    return date.fromisoformat(value)


def resolve_role_key(role: str) -> str:
    clean = str(role or "").strip()
    if clean in ROLE_ALIASES:
        return ROLE_ALIASES[clean]
    if any(clean in table.rates for table in SW_LABOR_RATE_TABLES.values()):
        return clean
    if clean == "중급기술자":
        raise ValueError("중급기술자는 현행 KOSA 직무명이 아니므로 직무 확인이 필요합니다")
    raise KeyError(f"unknown KOSA SW role: {role}")


def get_sw_labor_rate(
    role: str,
    *,
    application_year: int,
    as_of_date: str | None = None,
) -> tuple[SWLaborRateTable, SWLaborRate]:
    try:
        table = SW_LABOR_RATE_TABLES[int(application_year)]
    except KeyError as exc:
        raise KeyError(f"missing KOSA table for application year: {application_year}") from exc
    if as_of_date and _iso_date(table.published_at) > _iso_date(as_of_date):
        raise ValueError(
            f"{application_year} KOSA table was not available at {as_of_date}"
        )
    role_key = resolve_role_key(role)
    return table, table.rates[role_key]


def annual_labor_cost_input(
    role: str,
    *,
    application_year: int,
    months: float = 12.0,
    as_of_date: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Build an evidenced resolver operand from an official monthly rate."""
    if not 0 < months <= 12:
        raise ValueError("months must be greater than 0 and at most 12")
    table, rate = get_sw_labor_rate(
        role,
        application_year=application_year,
        as_of_date=as_of_date,
    )
    value = int(round(rate.monthly_won * months))
    return {
        "annual_labor_cost_per_person": {
            "value": value,
            "unit": "KRW/person/year",
            "source": "KOSA_official_average_wage",
            "source_ref": (
                f"{table.source}; {rate.role_label} 월 {rate.monthly_won:,}원 × "
                f"{months:g}개월; 적용기간 {table.effective_from}~{table.effective_to}; "
                f"{table.source_url}"
            ),
            "evidence_keys": [
                f"kosa_sw_wage:{table.application_year}:{rate.role_key}:monthly"
            ],
        }
    }


__all__ = [
    "ROLE_ALIASES",
    "SWLaborRate",
    "SWLaborRateTable",
    "SW_LABOR_RATE_TABLES",
    "annual_labor_cost_input",
    "get_sw_labor_rate",
    "resolve_role_key",
]
