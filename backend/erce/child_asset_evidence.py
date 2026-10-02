"""Child asset-deposit inputs reviewed after reading bill 2200486's answer.

The age-specific population is not a unit price. The monthly amount is a
maximum-payment scenario, not an official universal benefit tariff.
"""
from backend.erce.reviewed_variable_rows import evidence_row


def child_asset_rows():
    common = dict(
        source_bill_no="2200486", available_at="2024-06-18",
        source_ref="의안 2200486 비용추계서(24C0887), PDF p.3~4, 표 2",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2200486/cost_estimate.pdf",
        agency="정부", policy_domain="아동 자산형성지원",
        scope="전국 18세 미만 아동, 2026~2030년",
        service_function="보편적 아동 자산형성 계좌 월 적립",
        reuse_policy="comparable", source_class="precedent_assumption",
        allowed_routes=["transfer_child_asset_monthly"],
        reviewed_at="2026-10-02", obtained_from="reviewed_answer",
        requires_applicability_note=True,
    )
    population = evidence_row(
        **common, evidence_key="2200486:under18_population:2026-2030",
        variable_key="recipient_count", value=[6358000,6136000,5931000,5700000,5486000],
        unit="person/year", variable_role="target_quantity",
        value_years=[2026,2027,2028,2029,2030], population_age_min=0, population_age_max=17,
        geography="전국", forecast_version="통계청 2023.12 장래인구추계 중위",
        precision_note="정답 표 2에 천명 단위로 표시된 전망 인구; 원 통계 미세 단위는 별도 미검증",
        limitation="다른 연령·지역·기간에 전용 금지. 원 통계의 공개일이 아닌 이 추계서 확인일로 시점 제한")
    amount = evidence_row(
        **common, evidence_key="2200486:monthly_deposit_maximum_scenario:2026-2030",
        variable_key="benefit_per_recipient", value=100000, unit="KRW/person/month",
        variable_role="assumed_payment", value_kind="scenario_assumption",
        scenario_key="child_asset_monthly_maximum_100000", legal_upper_limit_won=100000,
        limitation="상한 10만원을 전액 지급하는 선례 가정. 현재 법안에도 같은 상한이 있을 때만 확인 후 선택; 확정 공식 단가 아님")
    months = evidence_row(
        **common, evidence_key="2200486:support_months:full_year",
        variable_key="payments_per_year", value=12, unit="month/year",
        variable_role="schedule_assumption",
        limitation="매년 전원에게 12개월 지급하는 가정. 첫해 부분 시행·월별 출생과 연령 이탈을 반영하는 경우 수정 필요")
    cap = evidence_row(
        **{**common, "reuse_policy": "target_only"},
        evidence_key="2200486:monthly_deposit_legal_upper_limit",
        variable_key="monthly_deposit_limit", value=100000, unit="KRW/person/month",
        variable_role="constraint", value_kind="upper_limit",
        limitation="의안 제42조제1항의 상한. 계산 입력으로 직접 선택 불가")
    return [population, amount, months, cap]
