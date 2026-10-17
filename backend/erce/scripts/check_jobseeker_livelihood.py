import dataclasses
import json
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.method_evidence_store import validate_non_estimation_review
from backend.erce.jobseeker_livelihood_evidence import PROFILE


def allowance_payload():
    keys=[f"2207706:{k}:reviewed" for k in ("recognized_jobseekers","iap_completion_rate","average_payment_months","livelihood_floor_history")]
    keys.append("official:mohw:livelihood_floor:2025:single")
    method="2207706:jobseeker_livelihood_previous_year"
    return dict(bill_no="2207706",evidence_mode="development_review",cutoff_date="2026-10-06",payer="government",
        route_key="transfer_recipient_delta",support_derivation=PROFILE,start_year=2026,years=5,
        livelihood_floor_base_year=2025,jobseeker_cohort="recognized_I_type",
        livelihood_floor_projection="historic_cagr_2019_2023",
        support_derivation_note="정답확인후I유형인정인원평균·IAP·실지급개월·전년도생계급여시차 연결",
        payment_scope_note="2022~2023평균인정인원224228명×IAP98%,평균5.2개월.법정서비스2년과구분",
        floor_projection_note="2025생계최저액765444원을공식확인,2019~2023기준액으로CAGR파생;미래값은가정",
        estimation_start_note="정답의심사기간가정을준용한2026~2030.공포날시행이자동2026을정하는것아님",
        explicit_inputs=dict(existing_benefit_per_recipient=dict(value=500000,unit="KRW/person/month",source_ref="원문PDF1쪽당시월50만원")),
        selected_evidence_keys=keys,evidence_selection_reasons={k:"해당시점·인정I유형·시차/지급범위검토후사후준용" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"전년도생계최저액연동 구직수당"},
        method_confirmations={method:dict(payment_scope_note="실지급평균5.2개월·참여동결",
            floor_projection_note="2025공식기준·과거CAGR전망가정",estimation_start_note="법안심사기간고려2026시작가정")})


def service_review():
    return dict(bill_no="2207706",evidence_mode="development_review",cutoff_date="2026-10-06",
        decision_evidence_key="2207706:service_duration_not_estimated",reliable_estimation_basis_available=False,
        decision_facts=dict(service_duration_extended=True,cash_payment_duration_extended=False,
            reliable_incremental_staffing_available=False,reliable_incremental_operating_cost_available=False),
        decision_confirmations=dict(service_cash_period_separation="원문서비스기간조항과수당기간변경구분;정답의업무매뉴얼인용확인",
            incremental_staffing_review="역사적정답의장래충원자료미확정을확인.현재모든부처계획부재를전수확인했다는주장아님",
            operating_plan_review="당시추가관리수요·운영비의합리적근거미확정.후속계획확보시재추계"))


def run_regression():
    p=allowance_payload();r=estimate_routed_item(p)
    web=calculate_erce_web_item({**p,"bill_no":"SIMILAR_JOBSEEKER_LIVELIHOOD","evidence_mode":"holdout"})
    decision=validate_non_estimation_review(service_review())
    similar=validate_non_estimation_review({**service_review(),"bill_no":"SIMILAR_SERVICE_EXTENSION","evidence_mode":"holdout"})
    total=sum(r.annual_amounts_thousand)/100000
    return dict(bill_no="2207706",post_answer_regression=True,independent_evaluation=False,
        result=dataclasses.asdict(r),trace=web["derivationTrace"],reusable_web_status=web["status"],
        service_decision=decision,synthetic_service_decision=similar,
        annual_eok=[v/100000 for v in r.annual_amounts_thousand],
        partial_total_eok=total,gold_partial_total_eok=19800,difference_percent=abs(total-19800)/19800*100,
        required_lower_filled=5,required_lower_count=5,whole_bill_total=None,
        excluded_scope="서비스추가인건비/기관운영비미추계.기존위원회심의는정답상기존예산범위,신규회의수당임의생성안함",
        limitation="기준2025/현행50만원의역사적정답재현.최신현행정책은별도시나리오.일부추계하한,정답열람후회귀")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
