"""Historical committee operating-budget models."""
from backend.erce.reviewed_variable_rows import evidence_row


def committee_annual_operation_rows():
    rows = []
    versions = [
        ("2203830", "2024-11-15", {2023:.036, 2024:.025, 2025:.021, 2026:.02, 2027:.02, 2028:.02, 2029:.02}, "2024.11"),
        ("2213574", "2026-01-23", {2023:.036, 2024:.023, 2025:.02, 2026:.019, 2027:.02, 2028:.02, 2029:.02, 2030:.02}, "2025.11"),
    ]
    for bill, available, rates, vintage in versions:
        common = dict(source_bill_no=bill, available_at=available,
            source_ref=f"의안{bill} 공무직위원회 비용추계서; 2020~2022년 운영비 평균과 {vintage} CPI 전망",
            source_url=f"backend/generated/assembly_22_pdfs/by_bill/{bill}/cost_estimate.pdf",
            agency="고용노동부", policy_domain="공공부문 노무관리",
            scope="기획단·발전협의회를 포함한 공무직위원회 연간 운영",
            service_function="과거 운영실적 기반 위원회 운영", reuse_policy="comparable",
            allowed_routes=["committee_annual_operation"], obtained_from="reviewed_answer")
        rows.extend([
            evidence_row(evidence_key=f"{bill}:committee_operating_average:2020-2022",
                variable_key="annual_operating_amount", value=1_040_000_000, unit="KRW/year",
                variable_role="historical_average", **common),
            evidence_row(evidence_key=f"{bill}:committee_cpi_forecast:{vintage}",
                variable_key="growth_rates_by_year", value=rates, unit="ratio/year",
                variable_role="forecast_assumption", **common),
            evidence_row(evidence_key=f"{bill}:committee_operating_base_year:2022",
                variable_key="base_year", value=2022, unit="year",
                variable_role="reference_year", **common),
        ])
    return rows
