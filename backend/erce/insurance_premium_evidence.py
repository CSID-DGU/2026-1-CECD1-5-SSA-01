"""Reviewed insurance-premium baselines; target-answer observations stay target-only."""
from backend.erce.reviewed_variable_rows import evidence_row


def insurance_premium_rows():
    common = dict(
        source_bill_no="2200116", available_at="2024-06-14",
        source_ref="의안 2200116 비용추계서(24B0449), PDF p.7~9, 표 4~6",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2200116/cost_estimate.pdf",
        agency="농림축산식품부·해양수산부", policy_domain="농어업재해보험",
        scope="농작물·가축·양식수산물 재해보험료 국비·지방비 지원",
        service_function="기존 보험료 지원율 대비 개정안 지원율 순증",
        reuse_policy="target_only", source_class="precedent_assumption",
        reviewed_at="2026-09-28", obtained_from="reviewed_answer",
        allowed_routes=["transfer_premium_subsidy_delta"],
        limitation="2021~2023년 평균을 2024년 기준선으로 사용한 정답 추계 가정. 다른 법안 또는 발의일 이전 추계에 자동 전용 금지",
    )
    rows = []
    baselines_million = {
        "crop": (945954, 463446, 360256),
        "livestock": (221126, 106569, 26455),
        "aquaculture": (24589, 12388, 7793),
    }
    for line, (premium, national, local) in baselines_million.items():
        rows.append(evidence_row(
            evidence_key=f"2200116:{line}:premium_base:2024", variable_key="premium_base",
            value=premium * 1_000_000, unit="KRW/year", variable_role="historical_premium_base",
            insurance_line=line, historical_period="2021~2023년 평균", base_year=2024,
            **common))
        for payer, amount in (("national", national), ("local", local)):
            rows.append(evidence_row(
                evidence_key=f"2200116:{line}:{payer}:existing_support_amount:2024",
                variable_key="existing_support_amount", value=amount * 1_000_000,
                unit="KRW/year", variable_role="historical_support_base",
                insurance_line=line, payer=payer, historical_period="2021~2023년 평균",
                base_year=2024, **common))
    for payer, rate in (("national", .7), ("local", .2)):
        rows.append(evidence_row(
            evidence_key=f"2200116:{payer}:new_support_rate:2025-2029",
            variable_key="new_support_rate", value=rate, unit="ratio",
            variable_role="scenario_assumption", payer=payer, legal_floor=rate,
            scenario_note="법안의 이상(하한) 비율을 정답 추계에서 적용한 시나리오. 실제 지원율 확정값 아님",
            **common))
    rows.append(evidence_row(
        evidence_key="2200116:crop:base_year:2024", variable_key="base_year",
        value=2024, unit="year", variable_role="reference_year",
        insurance_line="crop", **common))
    rows.append(evidence_row(
        evidence_key="2200116:crop:growth_rates_by_year:2025-2029",
        variable_key="growth_rates_by_year",
        value={str(year): .094 for year in range(2025, 2030)}, unit="ratio/year",
        variable_role="forecast_assumption", insurance_line="crop",
        value_years=[2025, 2026, 2027, 2028, 2029], base_year=2024,
        calculation_note="2018~2022년 주요작물 보험요율 평균증가율 9.40%를 2024년 기준 순증액에 매년 적용",
        **common))
    return rows
