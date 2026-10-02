"""Versioned child populations and payment assumptions, reviewed after answer.

Population is a quantity, not a tariff. These rounded values are transcribed
from the official cost report, not independently downloaded KOSIS microdata.
"""
from backend.erce.reviewed_variable_rows import evidence_row

OFFICIAL_FORECAST_URL = "https://www.kostat.go.kr/board.es?act=view&bid=207&list_no=428476&mid=a10301020100"


def child_allowance_rows():
    common = dict(
        source_bill_no="2200147", available_at="2024-06-13",
        source_ref="의안 2200147 비용추계서(24C0335), PDF p.3~4, 표 2·3",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2200147/cost_estimate.pdf",
        agency="보건복지부", policy_domain="아동수당",
        scope="전국 아동수당, 2025~2029년", service_function="연령 확대 및 월 급여 인상",
        reuse_policy="comparable", source_class="precedent_assumption",
        reviewed_at="2026-10-02", obtained_from="reviewed_answer",
        requires_applicability_note=True, independently_verified=False,
    )
    under18 = [6625000, 6358000, 6136000, 5931000, 5700000]
    under8 = [2177000, 2046000, 1953000, 1898000, 1872000]
    rows = []
    for name, lower, upper, values, routes in (
        ("under18", 0, 17, under18, ["transfer_recipient", "transfer_child_asset_monthly", "transfer_recipient_subsidy"]),
        ("under8", 0, 7, under8, ["transfer_recipient_delta", "transfer_recipient", "transfer_recipient_subsidy"]),
        ("age8to17", 8, 17, [a-b for a,b in zip(under18, under8)], ["transfer_recipient", "transfer_recipient_subsidy"]),
    ):
        rows.append(evidence_row(
            **common, evidence_key=f"2200147:{name}_population:2025-2029",
            variable_key="recipient_count", value=values, unit="person/year",
            variable_role="target_quantity", allowed_routes=routes,
            value_years=[2025,2026,2027,2028,2029], geography="전국",
            population_age_min=lower, population_age_max=upper,
            forecast_version="통계청 2023.12 장래인구추계 중위(2022 기준)",
            official_reference_url=OFFICIAL_FORECAST_URL,
            derivation="표 2의 18세 미만 인구 − 표 3의 8세 미만 인구" if lower == 8 else "추계서 표의 천명 값을 명으로 환산",
            precision_note="천명 단위 반올림 표시값; 원 통계의 1명 단위 값은 별도 미검증",
            limitation="인구이지 실제 수급자 수가 아님. 연령·지역·기간·통계 버전 확인 후 지급률 별도 적용. 최신 통계라고 간주하지 않음",
        ))
    rows.append(evidence_row(
        **common, evidence_key="2200147:child_allowance_payment_rate:2024",
        variable_key="participation_rate", value=0.972, unit="ratio",
        variable_role="take_up_assumption", observation_year=2024,
        valid_from_year=2025, valid_to_year=2029,
        allowed_routes=["transfer_recipient", "transfer_recipient_delta", "transfer_recipient_subsidy"],
        limitation="2024년 아동수당 지급률을 추계기간에 유지하는 선례 가정. 다른 복지사업의 지급률로 전용 금지. 실제 수급자 수에 중복 적용 금지",
    ))
    rows.append(evidence_row(
        **common, evidence_key="2200147:child_allowance_treasury_share:2024",
        variable_key="subsidy_rate", value=0.7555, unit="ratio",
        variable_role="financing_share_assumption", observation_year=2024,
        valid_from_year=2025, valid_to_year=2029,
        allowed_routes=["transfer_recipient_subsidy"],
        limitation="2024년 평균 국고보조율을 동결하는 선례 가정. 총재정소요에는 곱하지 않으며 국비 분리 시에만 사용. 최신 보조율은 아님",
    ))
    return rows
