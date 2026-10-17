import dataclasses
import json
from backend.erce.disabled_worker_wage_evidence import direct_worker_wage_rows, PROFILE, DIRECT_MODEL
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def direct_worker_payload(scenario="share100",basis="reviewed_2024_11_levels"):
    method=f"2207871:direct_wage_gap:{basis}"
    keys=[r["evidence_key"] for r in direct_worker_wage_rows() if r.get("wage_gap_scenario") in (None,scenario)
          and r.get("worker_forecast_basis") in (None,basis)]
    keys.append("official:moel:minimum_hourly:2025:disabled_gap")
    notes=dict(worker_scope_note="시설 적용제외 근로자만 산출, 다른사업체·원문훈련자 미분리 인원 자동가산 금지",
        worker_proxy_note="가용자료 한계로 전체시설 시급·시간을 적용제외집단 대리 사용. 이 범위는 정답과 같지만 모든 법정대상을 포함한 수치아님",
        worker_projection_note="2020~2024 인원·시급 각각CAGR, 원자료평균113.4시간 유지. 표시113·3.47%·3.86%를 계산원시값으로 쓰지 않음",
        worker_scenario_note=f"{scenario} 보조율은 정책시나리오, 재량지원 예산편성 가정이며 시행령 확정률 아님",
        worker_start_note="공포후6개월과 준비기간 고려2026~2030. 직접 차액보조이므로2200660통과 조건 없음",
        worker_forecast_vintage_note="정답표시2025.4률과 별도로 기존2207081의2024.11 월최저임금 전망단가를209시간으로 환산하는 대안 참조. 같은2025.4전망 원자료라고 확정하지 않음")
    return dict(bill_no="2207871",evidence_mode="development_review",cutoff_date="2026-10-11",
        route_key=PROFILE,support_derivation=PROFILE,payer="government",start_year=2026,years=5,
        disabled_worker_scope="vocational_facility_exempt_workers",worker_support_model=DIRECT_MODEL,
        worker_forecast_basis=basis,wage_gap_scenario=scenario,worker_scenario_confirmed=True,
        linked_minimum_wage_bill_assumed_passed=False,**notes,
        selected_evidence_keys=keys,evidence_selection_reasons={k:notes["worker_projection_note"]+";"+notes["worker_forecast_vintage_note"] for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"직접시급차액보조·법안연계없이 별도거시전망 선택"},method_confirmations={method:notes})


def run_regression(db_path=None):
    gold=dict(share30=(990,[171,184,197,211,227]),share50=(1650,[285,306,328,352,378]),share100=(3299,[571,612,656,704,756]))
    parts=[]; options={"variable_db_path":db_path} if db_path else {}
    for scenario,(g,annual_gold) in gold.items():
        p=direct_worker_payload(scenario)
        if db_path:
            p["variable_db_path"]=str(db_path)
        r=estimate_routed_item(p)
        web=calculate_erce_web_item({**p,"bill_no":"SIMILAR_DIRECT_WORKER_GAP","evidence_mode":"holdout"},**options)
        annual=list(r.annual_amounts_thousand); total=sum(annual)/100000
        published=calculate_erce_web_item({**direct_worker_payload(scenario,"published_2025_04_rates"),"bill_no":"SIMILAR_PUBLISHED_WORKER_GAP","evidence_mode":"holdout"},**options)
        parts.append(dict(scenario=scenario,payload=p,result=dataclasses.asdict(r),web_result=web,
            total_eok=total,gold_display_total_eok=g,error_percent=abs(total-g)/g*100,
            annual_display_eok=[round(x/100000) for x in annual],annual_display_matches=sum(round(x/100000)==a for x,a in zip(annual,annual_gold)),
            published_rate_result=published,published_rate_total_eok=sum(published["annualAmountsThousand"])/100000))
    return dict(bill_no="2207871",post_answer_regression=True,independent_evaluation=False,parts=parts,
        forecast_vintage_match_unverified=True,limitation="시설집단 정답표시 재현·과거거시전망 대안선택. 다른사업체 제외 유지,2025.4 원전망 정밀도 독립확인 전이며 최초독립정확도 성과 아님")


if __name__=="__main__":
    print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
