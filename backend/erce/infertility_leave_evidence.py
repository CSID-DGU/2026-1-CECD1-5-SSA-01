"""Reviewed population assumptions learned from 2200349; not legal rates."""
from backend.erce.reviewed_variable_rows import evidence_row


def infertility_leave_rows():
    common = dict(
        source_bill_no="2200349", available_at="2024-08-29",
        source_ref="2200349 고용보험법 비용추계서(24B0738, 2024-08-29), PDF p.7~12",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2200349/cost_estimate.pdf",
        agency="고용노동부", policy_domain="난임치료휴가 급여",
        scope="전국 우선지원대상기업 근로자; 2023년 통계 기준 난임치료휴가",
        service_function="난임치료휴가에 대한 고용보험기금 급여 신설",
        reuse_policy="comparable", requires_applicability_note=True,
        source_class="precedent_assumption", obtained_from="reviewed_answer",
        reviewed_at="2026-09-30",
        limitation="정답지에서 학습한 가정. 2200349 최초 검증에는 사용 금지. 후속 안에서도 대상·기준연도·사용행태 확인 필요",
    )
    civil = {
        "base_year": 2023, "priority_company_share": .595,
        "priority_share_growth_rate": .007,
        "insured_cohorts": [
            {"sex": "male", "insured_population": 8_481_000, "insured_growth_rate": .0187,
             "civil_leave_users": 514, "civil_staff": 226_282},
            {"sex": "female", "insured_population": 6_718_000, "insured_growth_rate": .0291,
             "civil_leave_users": 400, "civil_staff": 82_964},
        ],
    }
    budget = {
        "base_year": 2023, "priority_company_share": .595,
        "priority_share_growth_rate": .007,
        "historical_infertility_patients": [230_802, 228_382, 252_288, 243_347, 243_212],
        "employee_share": .799, "insurance_enrollment_share": .77,
        "leave_uptake_rate": .5,
    }
    rows = []
    for method, basis in (("civil_proxy", civil), ("budget_proxy", budget)):
        rows.append(evidence_row(
            evidence_key=f"2200349:infertility_population_basis:{method}:2023",
            variable_key="infertility_population_basis", value=basis, unit="population_basis",
            variable_role="population_method_assumptions", scenario_key=method,
            allowed_routes=[f"infertility_leave_{method}"],
            derivation_note="기준비율의 0.7%는 연간 상대 증가율(×1.007)이며 0.7%p 가산이 아님",
            **common,
        ))
    rows.append(evidence_row(
        evidence_key="2200349:infertility_daily_benefit:2024",
        variable_key="daily_leave_benefit", value=401_910 / 5,
        unit="KRW/person/day", variable_role="borrowed_payment_scenario",
        allowed_routes=["infertility_leave_civil_proxy", "infertility_leave_budget_proxy"],
        derivation="배우자 출산휴가 2024년 5일 상한액 401,910원 ÷ 5일",
        is_statutory_infertility_rate=False,
        limitation="난임급여의 공식 단가가 아님. 정답지의 배우자급여 상한 준용·동결 가정. 향후 비교안에서 준용 타당성을 확인해야 함",
        **{k: v for k, v in common.items() if k != "limitation"},
    ))
    return rows
