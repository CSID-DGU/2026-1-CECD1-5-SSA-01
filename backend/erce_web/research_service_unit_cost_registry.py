"""Versioned public-sector research-service benchmarks.

These values are reusable comparables, not universal tariffs.  A benchmark is
available only after the source cost estimate's reply date, and only for the
same implementing agency and research-service route.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class ResearchServiceBenchmark:
    key: str
    mechanism: str
    agency: str
    available_at: str
    applied_unit_cost_won: int
    recurrence_interval_years: int | None
    sample_costs_won: tuple[int, ...]
    source: str
    source_ref: str
    source_url: str
    policy_domain: str = ""
    source_bill_no: str = ""


RESEARCH_SERVICE_BENCHMARKS: tuple[ResearchServiceBenchmark, ...] = (
    ResearchServiceBenchmark(
        key="borderline_intelligence_plan_2024_10_22", mechanism="research_plan",
        agency="보건복지부", available_at="2024-10-22",
        applied_unit_cost_won=70_000_000, recurrence_interval_years=5,
        sample_costs_won=(70_000_000,), source="국회예산정책처 비용추계서",
        source_ref="의안 2203298, 24C3255, PDF p.5~6; 교육부 2021년 특수교육발전 계획 기초연구 준용",
        source_url="backend/generated/assembly_22_validation_holdout_v1/by_bill/2203298/cost_estimate.pdf",
        policy_domain="경계선지능인", source_bill_no="2203298",
    ),
    ResearchServiceBenchmark(
        key="borderline_intelligence_survey_2024_10_22", mechanism="research_survey",
        agency="보건복지부", available_at="2024-10-22",
        applied_unit_cost_won=300_000_000, recurrence_interval_years=3,
        sample_costs_won=(300_000_000,), source="국회예산정책처 비용추계서",
        source_ref="의안 2203298, 24C3255, PDF p.6~7; 보건복지부 2024년 경계선지능 현황 조사 예산 준용",
        source_url="backend/generated/assembly_22_validation_holdout_v1/by_bill/2203298/cost_estimate.pdf",
        policy_domain="경계선지능인", source_bill_no="2203298",
    ),
    ResearchServiceBenchmark(
        key="mcst_library_survey_2026_04_03",
        mechanism="research_survey",
        agency="문화체육관광부",
        available_at="2026-04-03",
        applied_unit_cost_won=210_000_000,
        recurrence_interval_years=3,
        sample_costs_won=(210_000_000,),
        source="국회예산정책처 도서관법 개정안 비용추계서",
        source_ref=("의안 2217373, 추계번호 26C1390, 표 1~2; "
                    "2025년 전국도서관 통계조사 예산 2억 1천만원 준용; "
                    "주기는 명시 규정이 없어 유사사례에 따라 3년 가정. "
                    "본문의 2억원 표기와 달리 결과표·인용 예산은 2억 1천만원"),
        source_url="backend/generated/assembly_22_validation_holdout_v1/by_bill/2217373/cost_estimate.pdf",
        policy_domain="도서관",
        source_bill_no="2217373",
    ),
    ResearchServiceBenchmark(
        key="moe_plan_research_2024_07_25",
        mechanism="research_plan",
        agency="교육부",
        available_at="2024-07-25",
        applied_unit_cost_won=32_000_000,
        recurrence_interval_years=5,
        sample_costs_won=(36_364_000, 30_000_000, 30_000_000),
        source="국회예산정책처 초·중등교육법 일부개정법률안 비용추계서",
        source_ref=(
            "의안 2201446, 추계번호 24C1763, 표 2~3; 최근 교육부 기본계획 "
            "연구용역 3건을 바탕으로 회당 3,200만원·5년 주기 적용"
        ),
        source_url="https://opinion.lawmaking.go.kr/gcom/nsmLmSts/out/2201446/detailRP",
    ),
    ResearchServiceBenchmark(
        key="moe_survey_research_2024_07_25",
        mechanism="research_survey",
        agency="교육부",
        available_at="2024-07-25",
        applied_unit_cost_won=22_000_000,
        recurrence_interval_years=1,
        sample_costs_won=(18_182_000, 27_273_000),
        source="국회예산정책처 초·중등교육법 일부개정법률안 비용추계서",
        source_ref=(
            "의안 2201446, 추계번호 24C1763, 표 4~5; 최근 교육부 실태조사 "
            "연구용역 2건을 바탕으로 연 2,200만원 적용"
        ),
        source_url="https://opinion.lawmaking.go.kr/gcom/nsmLmSts/out/2201446/detailRP",
    ),
)


def get_research_service_benchmark(
    mechanism: str,
    agency: str,
    *,
    as_of_date: str,
    policy_domain: str = "",
    target_bill_no: str = "",
) -> ResearchServiceBenchmark:
    """Return the latest benchmark that was knowable at ``as_of_date``."""
    cutoff = date.fromisoformat(as_of_date)
    matches = [
        row for row in RESEARCH_SERVICE_BENCHMARKS
        if row.mechanism == mechanism
        and row.agency == agency
        and (not row.policy_domain or row.policy_domain == policy_domain)
        and (not target_bill_no or row.source_bill_no != target_bill_no)
        and date.fromisoformat(row.available_at) <= cutoff
    ]
    if not matches:
        raise KeyError(
            f"no research-service benchmark for {agency}/{mechanism} at {as_of_date}"
        )
    return max(matches, key=lambda row: row.available_at)


def research_service_formula_inputs(
    mechanism: str,
    agency: str,
    *,
    as_of_date: str,
    policy_domain: str = "",
    target_bill_no: str = "",
) -> dict[str, dict[str, Any]]:
    benchmark = get_research_service_benchmark(
        mechanism,
        agency,
        as_of_date=as_of_date,
        policy_domain=policy_domain,
        target_bill_no=target_bill_no,
    )
    common = {
        "source": "official_research_service_benchmark",
        "source_ref": (
            f"{benchmark.source}; {benchmark.source_ref}; "
            f"available_at={benchmark.available_at}; {benchmark.source_url}"
        ),
        "evidence_keys": [benchmark.key],
    }
    if mechanism == "research_plan":
        return {
            "plan_unit_cost": {
                "value": benchmark.applied_unit_cost_won,
                "unit": "KRW/plan",
                **common,
            },
            "recurrence_interval_years": {
                "value": benchmark.recurrence_interval_years,
                "unit": "year",
                **common,
            },
        }
    if mechanism == "research_survey":
        return {
            "survey_unit_cost": {
                "value": benchmark.applied_unit_cost_won,
                "unit": "KRW/survey",
                **common,
            },
            "recurrence_interval_years": {
                "value": benchmark.recurrence_interval_years,
                "unit": "year",
                **common,
            },
        }
    raise KeyError(f"unsupported research-service mechanism: {mechanism}")


__all__ = [
    "RESEARCH_SERVICE_BENCHMARKS",
    "ResearchServiceBenchmark",
    "get_research_service_benchmark",
    "research_service_formula_inputs",
]
