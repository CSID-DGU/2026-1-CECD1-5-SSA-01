import dataclasses
import json
from backend.erce.medical_standard_workplace import medical_workplace_rows,PROFILE
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.method_evidence_store import validate_non_estimation_review


def medical_payload(cumulative=True):
    method="2204655:medical_workplace_reference"
    notes=dict(medical_workplace_scope_note="의료법인 자회사형 설립허용의 기존설립지원 신청증가. 국가의 병원출자금이 아님.",
        medical_application_note="2024.3의료법인1617개 중 매년0.1%참여를 올림해 신규2개. 실제신청 예측치가 아닌 참고가정.",
        medical_budget_note="인증유지100%·예산확대 참고가정, 고정예산내배분과 세제감면 추가효과는 별도.",
        medical_support_basis_note="정답표2·4·6·8·10 누적지원은 기존설립보조 설명과 일관성미확인, 자기정답참고재현만. 새의안은 매년신규지원 기본으로 검토.")
    keys=[r["evidence_key"] for r in medical_workplace_rows()]
    return dict(bill_no="2204655",evidence_mode="development_review",cutoff_date="2026-10-10",
        route_key=PROFILE,support_derivation=PROFILE,payer="government",start_year=2026,years=5,
        workplace_form="medical_corporation_subsidiary",standard_grant_price_year=2025,
        medical_reference_confirmed=True,budget_expansion_assumed=True,medical_certification_retention=1,
        medical_support_mode="cumulative_support_reference" if cumulative else "annual_new_establishments",
        cumulative_source_replay_confirmed=cumulative,**notes,selected_evidence_keys=keys,
        evidence_selection_reasons={k:"의료법인모집단·신청률·설립보조 과업·2025가격과2024.11전망 참고가정 확인" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"공식미첨부와 별도로 제시한 참고시나리오 선택"},
        method_confirmations={method:notes})


def formal_review():
    return dict(bill_no="2204655",evidence_mode="development_review",cutoff_date="2026-10-10",
        decision_evidence_key="2204655:medical_workplace_formal_not_estimated",reliable_estimation_basis_available=False,
        decision_facts=dict(actual_new_application_volume_confirmed=False,additional_support_budget_committed=False),
        decision_confirmations=dict(medical_application_forecast_review="신청물량을특정하기어려운당시조건과0.1%참여참고가정 구분",
                                    medical_budget_forecast_review="확정추가예산아님, 기존예산내집행이면 지출증가없을수있음"))


def run_regression():
    p=medical_payload();result=estimate_routed_item(p)
    annual=list(result.annual_amounts_thousand);total=sum(annual)/100000
    q={**medical_payload(False),"bill_no":"SIMILAR_MEDICAL_STANDARD_WORKPLACE","evidence_mode":"holdout"}
    reusable=calculate_erce_web_item(q)
    return dict(bill_no="2204655",post_answer_regression=True,independent_evaluation=False,
        formal_review_payload=formal_review(),formal_decision=validate_non_estimation_review(formal_review()),
        reference_payload=p,reference_result=dataclasses.asdict(result),reference_total_eok=total,
        gold_summary_reference_eok=97,summary_error_percent=abs(total-97)/97*100,
        gold_displayed_detail_sum_eok=96.8,detail_display_error_percent=abs(total-96.8)/96.8*100,
        annual_display_matches=sum(round(v/1000)==g for v,g in zip(annual,[612,1248,1910,2598,3312])),
        reusable_new_grants_payload=q,reusable_new_grants_result=reusable,
        limitation="공식판단은3호미첨부. 누적97억원참고는자기회귀만, 새의안재사용에는 누적지원금복사금지.")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
