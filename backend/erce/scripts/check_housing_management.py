import dataclasses
import json
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.housing_management_evidence import PROFILE


def housing_payload(scenario):
    fields=["tenant_households","management_cpi_forecast"]
    fields += ["arrears_share","management_public_share","kapt_stock_2023","kapt_monthly_common_fees_2023"] if scenario=="arrears_shared" else ["flat_monthly_fee"]
    keys=[f"2207600:management:{k}:reference" for k in fields]
    if scenario=="arrears_shared":keys.append("official:kostat:cpi_actual_2024:housing")
    method="2207600:management_fee:"+scenario
    return dict(bill_no="2207600",evidence_mode="development_review",cutoff_date="2026-10-08",
        route_key="transfer_recipient",support_derivation=PROFILE,payer="government",start_year=2026,years=5,
        management_fee_scenario=scenario,housing_income_cutoff="median_income_48_percent",
        management_scope="common_fee_excluding_utilities",
        support_derivation_note="발의이전회답인첨부추계서를과거유사관리비사례로만준용",
        housing_scenario_note="체납10.8%·공용관리비50%지원" if scenario=="arrears_shared" else "전체임차가구월3만원정액의유사사례",
        price_year_note="2023Kapt총월공용관리비/호수,2024실제CPI2.3%+2025부터첨부전망" if scenario=="arrears_shared" else "정액월3만원을2024기준가격으로가정,2025부터첨부전망적용",
        estimation_start_note="참고추계서2026~2030기간준용,확정시행일아님",
        use_unmatched_source_as_reference=True,
        unmatched_source_reference_note="회답2024-12-23/발의2025-01-17.동일버전공식전체정답아닌참고급여시나리오",
        selected_evidence_keys=keys,evidence_selection_reasons={k:"단가·기간·대상·시나리오범위와버전불일치검토후사후준용" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"새법안일치확정이아닌관리비기존시나리오재사용"},
        method_confirmations={method:dict(housing_scenario_note="두시나리오범위분리",
            unmatched_source_reference_note="참고추계서원문버전일치미확인",
            price_year_note="가격기준연도와물가중복여부확인",estimation_start_note="2026~2030참고기간")})


def run_regression():
    results=[]
    for scenario,gold in (("arrears_shared",3323.34),("all_tenants_flat",28262.31)):
        p=housing_payload(scenario);r=estimate_routed_item(p)
        web=calculate_erce_web_item({**p,"bill_no":"SIMILAR_HOUSING_MANAGEMENT","evidence_mode":"holdout"})
        amount=sum(r.annual_amounts_thousand)/100000
        results.append(dict(scenario=scenario,payload=p,result=dataclasses.asdict(r),trace=web["derivationTrace"],
            reusable_web_status=web["status"],total_eok=amount,gold_reference_eok=gold,
            difference_percent=abs(amount-gold)/gold*100))
    return dict(bill_no="2207600",post_answer_regression=True,independent_evaluation=False,
        runs=results,source_version_match=False,whole_bill_total=None,
        pending_items=["전산연계과업비","지자체순증발굴조사비","중앙운영실태점검증분"],
        limitation="원문전체정답이아닌관리비참고시나리오비교.가격연도·물가실측/전망차이는그대로유지,총액역산안함")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
