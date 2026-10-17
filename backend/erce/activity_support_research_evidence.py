"""Contract-only survey and plan comparables, not whole field-survey budgets."""
from backend.erce.reviewed_variable_rows import evidence_row


def activity_support_research_rows():
    rows=[]
    for kind,route,key,value,cycle,unit_year in (
        ("survey","research_survey","survey_unit_cost",90000000,3,2023),
        ("plan","research_plan","plan_unit_cost",40000000,5,2018)):
        common=dict(source_bill_no="2212766",available_at="2025-10-22",reviewed_at="2026-10-08",
            agency="보건복지부",policy_domain="장애인활동지원",scope="전국장애인활동지원 연구용역",
            service_function="activity_support_"+kind,research_service_function="activity_support_"+kind,
            research_cost_scope="research_contract_only",support_derivation="",
            variable_role="comparable_research_operand",allowed_routes=[route],
            requires_applicability_note=True,independently_verified=False,obtained_from="reviewed_answer",
            source_ref="2212766 비용추계서25C4872 PDF4~5쪽",
            limitation="당시유사연구용역비를기간동결한가정.공식고정가격/최신예산/현장조사전체비아님")
        rows.append(evidence_row(evidence_key=f"2212766:{kind}:{key}:reviewed",
            variable_key=key,value=value,unit="KRW/survey" if kind=="survey" else "KRW/plan",
            price_year=unit_year,**common,**(dict(original_contract_cost=89500000,excluded_field_survey_budget=750000000,
                price_derivation="2023장기요양실태조사연구용역8950만원을9000만원으로준용")
                if kind=="survey" else dict(price_derivation="2018장애인활동지원신규서비스개발연구4000만원준용"))))
        rows.append(evidence_row(evidence_key=f"2212766:{kind}:recurrence:reviewed",
            variable_key="recurrence_interval_years",value=cycle,unit="year",**common))
    return rows
