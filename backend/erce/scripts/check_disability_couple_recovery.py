"""Post-answer candidate scenario; not a reproduction of target population trends."""
import dataclasses
import json

from backend.erce.disability_couple_evidence import PROFILE, SCOPE, disability_couple_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def payload():
    rows = disability_couple_rows()
    return dict(bill_no="2204018",route_key="transfer_recipient_delta",
        cutoff_date="2026-10-04", evidence_mode="development_review",start_year=2025,years=5,
        support_derivation=PROFILE, disability_benefit_scope=SCOPE,
        disability_population_basis="freeze_2023_cohort",benefit_index_base_year=2024,
        supplementary_benefit_unchanged=True,
        population_proxy_note="가정 후보:2023년18~64세재가수급자 집단동결. 정답의 인구·수급권자비율 추세전망과 다르고 사용자 확정 전 시나리오임",
        support_derivation_note="기초급여 부부20%감액 폐지; 명단위; 부가급여 유지; 전년도 물가 적용",
        estimation_start_note="원문3쪽2025-01-01시행, 정답2025~2029년",
        selected_evidence_keys=[r["evidence_key"] for r in rows],
        evidence_selection_reasons={r["evidence_key"]:"해당 역사적 대상집단의 사후 비교 및 동결 후보 시나리오" for r in rows},
        explicit_inputs={"repealed_reduction_rate":dict(value=.2,unit="ratio",source_ref="원문5쪽제6조제3항100분의20감액 삭제"),
            "payments_per_year":dict(value=12,unit="month/year",source_ref="원문2025-01-01시행 및 매월지급")})


def run_regression():
    p=payload()
    result=estimate_routed_item(p)
    synthetic=calculate_erce_web_item({**p,"bill_no":"SYNTHETIC_DISABILITY_COUPLE_SCENARIO","evidence_mode":"holdout"})
    total=sum(result.annual_amounts_thousand)
    return dict(bill_no="2204018",post_answer_regression=True,independent_evaluation=False,
        scenario_only=True,payload=p,result=dataclasses.asdict(result),total_thousand=total,
        gold_total_thousand=18400000,difference_percent=abs(total-18400000)/18400000*100,
        required_variables_filled=3,required_variable_count=3,
        synthetic_web_status=synthetic["status"],synthetic_derivation_trace=synthetic["derivationTrace"],
        unresolved="정답의18세이상 인구·수급권자비율추세·연령구성 전망 원자료 미확보; 2023집단동결 후보만 계산. 이 후보를 사용자 확정값 또는 정답 재현으로 취급하지 않음")


if __name__=="__main__":
    print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
