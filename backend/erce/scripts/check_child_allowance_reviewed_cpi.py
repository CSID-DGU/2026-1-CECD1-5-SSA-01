import dataclasses
import json
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.child_allowance_reviewed_cpi import PROFILE


def reviewed_payload():
    method="2212685:child_allowance_reviewed_cpi"
    keys=["kosis_202312:under13_population:total:2026-2030:common",
        "kosis_202312:under8_population:total:2026-2030:common",
        "2208381:child_execution_factor:2025:reviewed_cpi","2212685:child_cpi:2026-2030:202507"]
    return dict(bill_no="2212685",evidence_mode="development_review",cutoff_date="2026-10-06",
        route_key="transfer_population_amount_delta",support_derivation=PROFILE,start_year=2026,years=5,
        benefit_index_base_year=2025,cpi_application_confirmed=True,cpi_first_year_included=True,
        existing_benefit_price_policy="freeze",population_geography="전국",statistical_sex="total",population_vintage="2023-12",
        child_population_geography="전국",payer="government",
        cpi_application_note="정답의 물가반영 시나리오를 확인. 원문검토보고의무가 법정자동인상을 확정한 것은 아님",
        population_proxy_note="국적/실수급자와 다른2023.12전국중위 인구준용;집행계수99.6%한번",
        support_derivation_note="0~12세 확대와월20만원인상,확인된CPI전망 신규금액만 누적반영",
        estimation_start_note="원문2026년1월1일시행,첫해부터2025월액에2026물가반영",
        explicit_inputs=dict(base_monthly_benefit=dict(value=200000,unit="KRW/person/month",source_ref="원문PDF3쪽월20만원"),
            existing_benefit_per_recipient=dict(value=100000,unit="KRW/person/month",source_ref="원문PDF3·5쪽현행10만원"),
            payments_per_year=dict(value=12,unit="month/year",source_ref="원문2026년1월시행·월급여12개월")),
        selected_evidence_keys=keys,selected_method_keys=[method],
        evidence_selection_reasons={k:"연령·전망기간·집행계수·물가반영가정을확인한사후준용" for k in keys},
        method_selection_reasons={method:"13세미만 아동수당 확대,물가반영시나리오확인됨"},
        method_confirmations={method:dict(cpi_application_note="정답시나리오물가반영검토완료",
            population_proxy_note="전국연령인구준용",estimation_start_note="2026첫해부터물가2%반영")})


def run_regression():
    p=reviewed_payload();r=estimate_routed_item(p)
    web=calculate_erce_web_item({**p,"bill_no":"SIMILAR_REVIEWED_CHILD_CPI","evidence_mode":"holdout"})
    amount=sum(r.annual_amounts_thousand)/1e9
    return dict(bill_no="2212685",post_answer_regression=True,independent_evaluation=False,
        result=dataclasses.asdict(r),trace=web["derivationTrace"],reusable_web_status=web["status"],
        total_trillion=amount,gold_partial_total_trillion=35.2,difference_percent=abs(amount-35.2)/35.2*100,
        regional_supplement=None,whole_bill_total=None,
        limitation="물가시나리오확인 후 재실행,최초7.589%결과를덮어쓰지않음")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
