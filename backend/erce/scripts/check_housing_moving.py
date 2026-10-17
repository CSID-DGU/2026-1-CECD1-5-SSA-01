import dataclasses
import json
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def updated_payload(scenario):
    profile="housing_management_fee"
    fields=["tenant_households","management_cpi_forecast"]
    fields += ["arrears_share","management_public_share","reported_monthly_common_fee"] if scenario=="arrears_shared" else ["flat_monthly_fee"]
    method="2209844:management:"+scenario
    p=common_payload(profile,fields,method)
    p.update(management_fee_scenario=scenario,management_scope="common_fee_excluding_utilities",
        management_fee_unit_basis="reported_weighted_monthly",management_price_base_year=2024 if scenario=="arrears_shared" else 2027,
        housing_scenario_note="체납10.2%·공용비50%지원" if scenario=="arrears_shared" else "전체임차에2027기준월3만원",
        price_year_note="표5의2024가중평균월6.8만원/표7의2027월3만원.가격기준분리")
    p["method_confirmations"]={method:dict(housing_scenario_note=p["housing_scenario_note"],price_year_note=p["price_year_note"],
        estimation_start_note=p["estimation_start_note"])}
    return p


def common_payload(profile,fields,method):
    keys=[f"2209844:{profile}:{k}:reviewed" for k in fields]
    return dict(bill_no="2209844",cutoff_date="2026-10-08",evidence_mode="development_review",
        route_key="transfer_recipient",support_derivation=profile,payer="government",start_year=2027,years=5,
        housing_income_cutoff="median_income_48_percent",support_derivation_note="정답확인후기존상위산식과갱신된근거연결",
        estimation_start_note="정답의사업준비기간2027~2031가정확인,원문확정연도아님",
        selected_evidence_keys=keys,evidence_selection_reasons={k:"대상기간·자료연도·급여구성확인후사후준용" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"동일과업과제외기준검토후방법선택"})


def moving_payload():
    profile="housing_moving_brokerage_bundle";method="2209844:moving_brokerage_bundle"
    p=common_payload(profile,["tenant_households","management_cpi_forecast","moving_plan_share","baseline_supported_households","moving_bundle_unit"],method)
    p.update(moving_cost_bundle_confirmed=True,moving_repeat_exclusion_years=2,moving_price_base_year=2025,
        prior_moving_supported_households=[0,0],moving_scope_note="이사·중개비를합한회당40만원패키지1개",
        baseline_support_note="기존정부사업15000가구를매년차감,국가/지방합산",
        moving_history_note="정답신규프로그램첫2년지원재고0시나리오.기존사업은별도15000가구차감")
    p["method_confirmations"]={method:dict(moving_scope_note=p["moving_scope_note"],baseline_support_note=p["baseline_support_note"],
        moving_history_note=p["moving_history_note"])}
    return p


def run_regression():
    m=moving_payload();e=estimate_routed_item(m)
    mw=calculate_erce_web_item({**m,"bill_no":"SIMILAR_HOUSING_MOVE","evidence_mode":"holdout"})
    out=[]
    for scenario,gold in (("arrears_shared",3656.21),("all_tenants_flat",27558.86)):
        p=updated_payload(scenario);r=estimate_routed_item(p)
        web=calculate_erce_web_item({**p,"bill_no":"SIMILAR_HOUSING_MOVE","evidence_mode":"holdout"})
        total=(sum(r.annual_amounts_thousand)+sum(e.annual_amounts_thousand))/100000
        out.append(dict(scenario=scenario,payload=p,management_result=dataclasses.asdict(r),total_eok=total,
            gold_total_eok=gold,error_percent=abs(total-gold)/gold*100,reusable_web_status=web["status"]))
    return dict(bill_no="2209844",post_answer_regression=True,independent_evaluation=False,
        moving_payload=m,moving_result=dataclasses.asdict(e),moving_trace=mw["derivationTrace"],
        moving_eok=sum(e.annual_amounts_thousand)/100000,gold_moving_eok=288.24,runs=out,
        limitation="공개된가중평균/물가로재계산,정답단가표숨은정밀도차이는유지.정답총액역산안함")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
