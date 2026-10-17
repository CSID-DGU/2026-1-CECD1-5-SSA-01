"""Scoped policy/media monitoring benchmark, separate from household surveys."""
from backend.erce.reviewed_variable_rows import evidence_row


def media_monitoring_survey_rows():
    common = dict(source_bill_no="2209797",available_at="2025-04-28",reviewed_at="2026-10-12",
        source_ref="2209797 비용추계서25C2159 PDF2~3쪽;2025장애인정책모니터링 사업예산",
        agency="보건복지부",policy_domain="정책·언론보도 모니터링",
        scope="정책 및 언론 모니터링·권고기준 점검·개선사항 조사분석",
        service_function="policy_media_monitoring_survey",
        research_service_function="policy_media_monitoring_survey",
        research_cost_scope="monitoring_research_package",support_derivation="",
        allowed_routes=["research_survey"],requires_applicability_note=True,
        independently_verified=False,obtained_from="reviewed_answer",
        limitation="2025선례 사업예산5천만원을 조사1회 비용으로 준용·가격동결하는 가정. 최신계약요율 아님. 현장방문·인구설문 과업으로 자동전용 금지")
    return [
        evidence_row(**common,evidence_key="2209797:media_monitoring:2025_unit_cost",
            variable_key="survey_unit_cost",value=50000000,unit="KRW/survey",
            variable_role="comparable_monitoring_budget",price_year=2025),
        evidence_row(**common,evidence_key="2209797:media_monitoring:price_freeze",
            variable_key="growth_rate",value=0,unit="ratio/year",
            variable_role="price_projection_assumption")]
