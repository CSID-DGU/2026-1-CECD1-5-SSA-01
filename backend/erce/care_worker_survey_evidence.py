"""Comparable wage-survey budget, reviewed after case 2205985's answer."""
from backend.erce.reviewed_variable_rows import evidence_row


def care_worker_survey_rows():
    common = dict(
        source_bill_no="2205985", available_at="2024-12-02",
        source_ref="의안 2205985 비용추계서(24C5258), PDF p.5; 보건복지부 2023년 사회복지사 보수 등 실태조사",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2205985/cost_estimate.pdf",
        agency="보건복지부", policy_domain="돌봄·사회복지 종사자 보수 실태조사",
        scope="중앙정부와 지방자치단체가 협력하는 전국 보수·지급실태 조사 1회",
        service_function="종사자 보수수준·지급실태·기준 준수율 조사",
        reuse_policy="comparable", source_class="precedent_assumption",
        allowed_routes=["research_survey", "annual_research_survey"],
        reviewed_at="2026-10-02", obtained_from="reviewed_answer",
        requires_applicability_note=True, price_year=2023,
        survey_population="사회복지사; 요양보호사 보수조사에 준용한 사례",
        implementation_model="central_local_cooperative_single_survey",
        scale_basis="전국 1회 통합조사 사업비; 표본 규모는 출처에 미기재",
        independently_verified=False,
    )
    cost = evidence_row(
        **common, evidence_key="2205985:social_worker_wage_survey:2023",
        variable_key="survey_unit_cost", value=178000000, unit="KRW/survey",
        variable_role="comparable_unit_rate",
        limitation="공식 고정요금이 아닌 2023년 유사 조사 사업비. 대상 직종·조사항목·전국 범위·수행방식을 확인한 뒤 사용. 지자체마다 별도 조사 시 개별 단가로 전용 금지; 시행 주기는 새 법안에서 추출")
    frozen = evidence_row(
        **common, evidence_key="2205985:wage_survey_price_freeze",
        variable_key="growth_rate", value=0, unit="ratio/year",
        variable_role="price_projection_assumption",
        limitation="해당 추계서의 추계기간 단가 동결 가정. 물가상승률 공식값이 아니며 새 추계에서도 동결할지 별도 확인 필요")
    return [cost, frozen]
