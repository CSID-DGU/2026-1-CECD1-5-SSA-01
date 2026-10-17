"""Comparable national commemorative event, separate from campaigns/videos."""
from backend.erce.reviewed_variable_rows import evidence_row

BASIS="national_abuse_prevention_commemorative_event"


def commemorative_event_rows():
    common=dict(source_bill_no="2201850",available_at="2024-08-01",reviewed_at="2026-10-06",
        source_ref="2201850 비용추계서24C2064 PDF4쪽;아동권리보장원2023행사비8300만원·2024편성9700만원준용",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2201850/cost_estimate.pdf",
        agency="보건복지부·아동권리보장원",policy_domain="학대예방",scope="전국단위기념일행사 연간1회",
        service_function=BASIS,service_cost_basis=BASIS,
        commemorative_event_scale="national_single_day_event",
        event_price_projection="freeze_reviewed_event_package",
        allowed_routes=["quantity_unit"],requires_applicability_note=True,
        independently_verified=False,obtained_from="reviewed_answer")
    return [
        evidence_row(evidence_key="2201850:commemorative_event:unit_cost:reviewed",
            variable_key="unit_cost",value=100000000,unit="KRW/event",variable_role="event_unit_assumption",**common,
            historical_actual_2023=83000000,historical_budget_2024=97000000,
            limitation="연1억원은유사사례의8300/9700만원을참고한정답가정.공식고정요율·최신단가아님.원위탁예산서독립검증미완료.지자체별추가행사홍보비미포함"),
        evidence_row(evidence_key="2201850:commemorative_event:annual_quantity:reviewed",
            variable_key="quantity",value=1,unit="event/year",variable_role="frequency_assumption",**common,
            limitation="전국단위예방의날행사매년1회라는참조가정.노력규정이어서비용없다고단정하지않음.주간7일을7회행사로치환하지않음")
    ]
