"""Comparable yearly policy-impact package, not a per-policy evaluation price."""
from backend.erce.reviewed_variable_rows import evidence_row


def policy_impact_research_rows():
    common = dict(source_bill_no="2201364", available_at="2024-07-11", reviewed_at="2026-10-10",
        source_ref="2201364 비용추계서24C1610 PDF3~4쪽; 과기정통부2024 기술영향평가 정책연구용역 예산",
        agency="과학기술정보통신부", policy_domain="정책영향평가 연구용역", scope="연간 정책영향평가 연구용역 패키지",
        service_function="policy_impact_annual_contract", research_service_function="policy_impact_annual_contract",
        research_cost_scope="research_contract_only", support_derivation="",
        variable_role="comparable_research_operand", allowed_routes=["policy_impact_annual_contract"],
        requires_applicability_note=True, independently_verified=False, obtained_from="reviewed_answer",
        price_year=2024, limitation="2024 기술영향평가 연간 예산 준용. 정책별 건당 평가단가·실태조사 가격·최신 고시값 아님. 보고공표 포함범위 검토 필요")
    values = [("service_quantity", 1, "contract"), ("service_unit_cost", 200000000, "KRW/contract"),
              ("frequency_per_year", 1, "contract/year"), ("growth_rate", 0, "ratio/year")]
    return [evidence_row(evidence_key=f"2201364:annual_policy_impact:{key}", variable_key=key,
                         value=value, unit=unit, **common) for key, value, unit in values]
