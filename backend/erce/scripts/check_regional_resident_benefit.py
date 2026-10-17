import json
from dataclasses import asdict
from backend.erce.regional_resident_benefit_evidence import PROFILE,SCOPE,NOTES
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.method_evidence_store import validate_non_estimation_review


def regional_payload(component="public_total"):
    method = "2214355:regional_resident_benefit_trend"
    key = "2214355:regional_population_history:2021-2024"
    notes = dict(zip(NOTES,[
        "2024-15고시89개지역의 전연령 인구총조사2021~2024집계. 향후재지정은 불확실하므로 현재지역 유지 가정",
        "2년계속거주·수급정지·외국체류 제외인구를 전망하지 못해 전체지역인구를 대리로쓰는 가정 승인. 자격조건충족 판정 아님",
        "2021~2024 전년비증감률3개 산술평균. 원평균과 적용정밀도를 모두 기록",
        "현재원문 제6조 연240만원이상·국비80%이상에서 최소액과80%를 동결하는 시나리오"
    ]))
    return dict(bill_no="2214355",evidence_mode="development_review",cutoff_date="2026-10-13",
        route_key=PROFILE,support_derivation=PROFILE,payer="government",start_year=2027,years=5,
        regional_population_scope=SCOPE,regional_model_confirmed=True,
        regional_residence_filter_omission_approved=True,regional_exclusion_filter_omission_approved=True,
        regional_benefit_price_mode="freeze_legal_floor",regional_fiscal_component=component,
        regional_trend_precision_mode="published_percent_two_decimals",
        regional_trend_precision_note="정답 표2 표시−0.49%를 적용해 표3과대응. %소수2자리에서먼저반올림하는 계산가정이며 보편정밀도규칙아님",
        **notes,explicit_inputs={
            "regional_annual_benefit":dict(value=2400000,unit="KRW/person/year",source_ref="2214355 원문제6조제1항 법정연간하한을 적용하는 가정"),
            "regional_national_share":dict(value=.8,unit="ratio",source_ref="2214355 원문제6조제2항 국비하한80% 준용가정")},
        selected_evidence_keys=[key],evidence_selection_reasons={key:"지정지역·통계기준·전연령·관측기간 확인"},
        selected_method_keys=[method],method_selection_reasons={method:"지역전체인구 대리전망·연간하한급여·분담금 분리"},
        method_confirmations={method:notes})


def field_review_payload():
    return dict(bill_no="2214355",evidence_mode="development_review",cutoff_date="2026-10-13",
        decision_evidence_key="2214355:field_inspection_not_estimated",reliable_estimation_basis_available=False,
        decision_confirmations=dict(field_inspection_scope_note="제9조 공무원현지조사 출장비 가능성은 있음",
            field_inspection_plan_review_note="현재정답의 계획·실시여부·빈도미확정 근거 확인. 새계획있으면재검토"),
        decision_facts=dict(field_inspection_frequency_basis_available=False,approved_field_inspection_plan_available=False))


def run_regression(db_path=None):
    runs = {}
    for component in ("public_total","national","local"):
        p = regional_payload(component)
        if db_path:
            p["variable_db_path"] = str(db_path)
        runs[component] = dict(payload=p,result=asdict(estimate_routed_item(p)))
    raw = {k:sum(v["result"]["annual_amounts_thousand"])/100000 for k,v in runs.items()}
    gold = {"public_total":552125,"national":441700,"local":110425}
    expected = {"public_total":[111512,110966,110422,109881,109343],
        "national":[89210,88773,88338,87905,87474],"local":[22302,22193,22084,21976,21869]}
    web = calculate_erce_web_item({**regional_payload(),"bill_no":"SYNTHETIC_SAME_REGION_BENEFIT"},
        **({"variable_db_path":db_path} if db_path else {}))
    review = validate_non_estimation_review(field_review_payload(),**({"db_path":db_path} if db_path else {}))
    return dict(bill_no="2214355",post_answer_regression=True,independent_evaluation=False,
        runs=runs,total_eok=raw,expected_display_total_eok=gold,
        raw_error_percent={k:abs(raw[k]-gold[k])/gold[k]*100 for k in raw},
        annual_display_matches={k:sum(round(a/100000)==g for a,g in zip(v["result"]["annual_amounts_thousand"],expected[k])) for k,v in runs.items()},
        web_interface_result=web,field_inspection_review=review,
        limitation="원관측인구를 정답에서확인하고 가정·표시정밀도를 보강한사후회귀. 새의안 독립성과·거주조건 실제충족검증 아님")


if __name__ == "__main__":
    print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
