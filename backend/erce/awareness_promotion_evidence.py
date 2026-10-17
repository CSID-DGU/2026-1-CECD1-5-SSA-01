"""Comparable annual campaign packages, not official advertising tariffs."""
from backend.erce.reviewed_variable_rows import evidence_row

PACKAGES={
    "public_awareness_campaign":200000000,
    "awareness_video_production_distribution":150000000,
}


def awareness_promotion_rows():
    rows=[]
    for package,amount in PACKAGES.items():
        common=dict(source_bill_no="2200879",available_at="2024-06-27",reviewed_at="2026-10-06",
            source_ref="2200879 비용추계서24C1330 PDF3~4쪽;2023보건복지부장애인식개선·차별학대예방홍보예산준용",
            source_url="backend/generated/assembly_22_pdfs/by_bill/2200879/cost_estimate.pdf",
            agency="보건복지부",policy_domain="장애인식개선",scope="전국대국민인식개선 연간패키지",
            service_function=package,service_cost_basis=package,
            awareness_price_projection="freeze_2023_package",
            awareness_scale_profile="national_disability_awareness_annual_package",
            allowed_routes=["quantity_unit"],requires_applicability_note=True,
            source_class="precedent_assumption",obtained_from="reviewed_answer",independently_verified=False)
        rows.append(evidence_row(evidence_key=f"2200879:{package}:unit_cost:2023",
            variable_key="unit_cost",value=amount,unit="KRW/package",variable_role="annual_package_budget",**common,
            price_year=2023,includes_production_and_distribution=package=="awareness_video_production_distribution",
            limitation="역사적사업예산준용패키지,최신공식광고요율아님.원2023예산서독립검증미완료.대상·규모·제작물·매체범위다르면재검토.영상송출비중복추가금지"))
        rows.append(evidence_row(evidence_key=f"2200879:{package}:annual_quantity:reviewed",
            variable_key="quantity",value=1,unit="package/year",variable_role="frequency_assumption",**common,
            limitation="매년한연간사업패키지실시·단가동결은정답의가정.법률에횟수1이명시된것아님.신규법안에자동빈도확정금지"))
    return rows
