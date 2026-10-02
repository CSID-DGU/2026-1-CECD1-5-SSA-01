"""Meeting-event budgets, distinct from individual attendance allowances."""
from backend.erce.reviewed_variable_rows import evidence_row


def interagency_meeting_rows():
    # Non-target bill opened before reading 2200936's answer. Its footnote
    # identifies a 2024 education/police standing-body budget, not a tariff.
    common = dict(
        source_bill_no="2214485", available_at="2026-02-10",
        agency="경찰청", policy_domain="학교폭력예방",
        scope="교육부·경찰청 중앙부처 상설협의체 회의 개최",
        service_function="관계 중앙부처 교육정책 협의체 운영",
        source_ref="의안 2214485, 25D6366, 비용추계서 PDF p.5 표2·각주1; 경찰청 2024년 학교폭력 상설협의체 예산 인용",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2214485/cost_estimate.pdf",
        obtained_from="non_target_source", reuse_policy="comparable",
        allowed_routes=["interagency_meeting_operation","goods_service_activity"],
        limitation="회의 개최비 총액 선례. 참석수당·개별 인원 단가가 아니며 내부 세부 지출명세는 독립 확보하지 않음",
    )
    return [
        evidence_row(evidence_key="2214485:interagency_meeting_unit_cost:2024",
            variable_key="service_unit_cost", value=12000000, unit="KRW/body/event",
            variable_role="unit_rate", price_year=2024,
            pricing_basis="per_event",
            price_policy="선례의 추계기간 동결 가정. 전국 협의체의 공식 표준 단가 아님",
            reference_annual_budget_won=48000000, reference_annual_events=4, **common),
        evidence_row(evidence_key="2214485:interagency_meeting_frequency:2026",
            variable_key="frequency_per_year", value=4, unit="event/year",
            variable_role="assumption", recurrence_policy="중앙부처 분기1회 가정; 법안 명시 주기가 있으면 우선 적용", **common),
    ]


def unification_council_annual_rows():
    """Post-answer supplementation: keep self-answer exclusion in blind runs."""
    common = dict(
        source_bill_no="2200936", available_at="2024-07-09",
        agency="통일부", policy_domain="북한이탈주민교육",
        scope="북한이탈주민 보호·정착지원협의회와 유사한 중앙부처 협의 업무",
        service_function="북한이탈주민 지원 관련 중앙행정기관 협의체 운영",
        source_ref="의안2200936, 24D0791, 비용추계서 PDF p.4; 현행법 제6조 협의회 연간운영비·각주2 소비자물가 전망 인용",
        source_url="backend/generated/assembly_22_validation_holdout_v1/by_bill/2200936/cost_estimate.pdf",
        obtained_from="reviewed_answer", reuse_policy="comparable",
        allowed_routes=["interagency_annual_operation"],
        limitation="해당 기관 협의회의 연간 운영비를 인용한 선례 가정. 원 예산서·세부 지출명세는 독립 확보하지 않음",
    )
    return [
        evidence_row(evidence_key="2200936:unification_council_annual_budget:2024",
            variable_key="annual_operating_amount", value=10800000, unit="KRW/body/year",
            variable_role="annual_budget_comparable", pricing_basis="annual_total",
            included_costs=["유관기관 업무협의 국내여비","법률자문·사례비","회의 준비비"],
            comparison_scope="통일부, 같은 북한이탈주민 지원 업무, 협의회1개",
            price_year_status="문서작성연도2024 기준액으로 해석. 인용 예산의 기준연도가 본문에 명시되지는 않음", **common),
        evidence_row(evidence_key="2200936:unification_council_base_year:2024",
            variable_key="base_year", value=2024, unit="year", variable_role="reference_year_assumption",
            basis_note="2024년 작성 문서의 현행 운영비로 해석한 가정; 정답 합계에 맞추려고 연도를 보정하지 않음", **common),
        evidence_row(evidence_key="2200936:consumer_price_forecast:2024-06-28",
            variable_key="growth_rates_by_year", value={"2025":.022,"2026":.022,"2027":.021,"2028":.021,"2029":.021},
            unit="ratio/year", variable_role="forecast_assumption", value_years=[2025,2026,2027,2028,2029],
            forecast_published_at="2024-06-28", forecast_vintage="nabo_consumer_price_2024_06_28",
            source_status="공식 전망을 정답에서 인용한 값. 원 전망 자료를 독립 확인한 공식값으로 승격하지 않음", **common),
    ]
