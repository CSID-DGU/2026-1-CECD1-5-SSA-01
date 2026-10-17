"""Reviewed under19 population and indexed-benefit references; not live statistics."""
from backend.erce.child_allowance_evidence import child_allowance_rows
from backend.erce.reviewed_variable_rows import evidence_row

PROFILE = "child_allowance_indexed_population"
ALIAS_KEYS = (
    "2200147:under8_population:2025-2029:child_indexed",
    "2200147:child_allowance_payment_rate:2024:child_indexed",
)
NEW_KEYS = (
    "2204028:under19_population:2025-2029",
    "2204028:index_base_monthly_amount:2024",
    "2204028:child_cpi_rates:2025-2029",
)


def child_allowance_indexed_rows():
    common = dict(allowed_routes=["transfer_population_amount_delta"],
        support_derivation=PROFILE, child_allowance_scenario="all_under19_indexed",
        child_population_geography="전국", reviewed_at="2026-10-04")
    source = {r["evidence_key"]: r for r in child_allowance_rows()}
    rows = []
    for alias, variable in zip(ALIAS_KEYS, ("under8_population", "child_payment_rate")):
        original = source[alias.removesuffix(":child_indexed")]
        rows.append({**original, **common, "evidence_key": alias,
            "variable_key": variable, "unit": "person" if variable == "under8_population" else "ratio",
            "alias_of": original["evidence_key"],
            "limitation": original["limitation"] + ";19세미만 기본급여 유지·물가연동 시나리오에만 사용"})
    for key, variable, value, unit, pages, metadata in (
        (NEW_KEYS[0], "under19_population", [7082000,6843000,6587000,6375000,6180000], "person", "PDF4쪽 표2",
         dict(value_years=list(range(2025,2030)), population_age_min=0, population_age_max=18,
              forecast_version="통계청2023.12 장래인구추계 중위(2022 기준)",
              precision_note="천명 단위 표시값을 명으로 환산. 1명 단위 원통계 독립 확인 없음")),
        (NEW_KEYS[1], "index_base_monthly_amount", 100000, "KRW/person/month", "PDF3쪽 상세 추계 전제",
         dict(child_index_base_year=2024, price_year=2024,
              precision_note="2024년 월10만원을 기준으로 사용하는 선례 가정. 다른 기준연도의 단가 아님")),
        (NEW_KEYS[2], "child_cpi_rates", [.022,.022,.021,.021,.021], "ratio/year", "PDF3쪽 각주1",
         dict(value_years=list(range(2025,2030)), forecast_version="24C3796 인용 NABO 물가전망",
              precision_note="전망 원본 발표일은 별도 미확인. 2024-10-02 회답에서 확인한 과거 전망; 최신 전망 아님")),
    ):
        rows.append(evidence_row(evidence_key=key, variable_key=variable, value=value, unit=unit,
            source_bill_no="2204028", available_at="2024-10-02",
            source_ref=f"의안2204028 비용추계서24C3796 {pages}",
            agency="국회예산정책처", policy_domain="아동수당", scope="전국 아동수당19세미만 확대 및 물가연동",
            service_function=PROFILE, variable_role="target_quantity" if variable == "under19_population" else "assumption",
            reuse_policy="comparable", obtained_from="reviewed_answer", independently_verified=False,
            geography="전국", source_url="backend/generated/assembly_22_pdfs/by_bill/2204028/cost_estimate.pdf",
            limitation="같은 연령·전국·기간·기준연도·통계 버전 조건 확인 후 재사용. 인구는 수급자가 아니므로 지급률1회 적용. 최신 공식 통계 직접 검증값 아님",
            **common, **metadata))
    return rows
