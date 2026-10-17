import dataclasses
import json
from backend.erce.levy_sector_evidence import PROFILE,EXPENSE,RECEIPTS,levy_sector_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.method_evidence_store import validate_non_estimation_review


def sector_payload(route=EXPENSE):
    kind="expense" if route==EXPENSE else "reference_receipts"
    method=f"2208360:sector_levy:{kind}"
    notes=dict(levy_sector_scope_note="2024공무원·비공무원·공공기관·민간 직접구간인원. 지출은공무원+비공무원, 참고수입은4부문. 정부지출과상계금지",
        levy_band_allocation_note="기초60→80%·차이가산0.5. 정답표의 차이기준60%를 사용, 고시원단가/월최저임금의 비중 유지. 무고용구간 인상수준 미정은 별도제외",
        levy_sector_timing_note="2025월최저임금2096270원·2024.11정밀전망, 전년도고용분을다음해납부해2026에는2025가격 사용. 감면·고용행태변화 미반영",
        levy_unpriced_zero_band_note="무고용 최저임금이상 인상배수 미확정이라 그효과는 미추계하고 기본80%변경계산에서는 현행1배 유지")
    keys=[r["evidence_key"] for r in levy_sector_rows()]
    p=dict(bill_no="2208360",evidence_mode="development_review",cutoff_date="2026-10-11",
        route_key=route,support_derivation=PROFILE,payer="government",start_year=2026,years=5,
        levy_sector_model="direct_sector_counts",levy_sector_scenario_confirmed=True,
        levy_tariff_basis="published_unit_price_card",levy_price_card_reuse_confirmed=True,
        levy_price_card_scope_note="동일60→80%·가산0.5·무고용1배유지 구조에서 표8 월기초액 차액을 단가후보로 선택. 2024.11전망·2026가격 기준이며 다른개정율·최신공식단가로 전용금지",
        fiscal_reporting="separate_revenue_and_expenditure",**notes,
        selected_evidence_keys=keys,evidence_selection_reasons={k:"2024부문별직접인원·2025고시·2024.11가격전망·가산배분 가정 확인" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"직접부문별 산정 및 정부지출/참고수입 구분"},method_confirmations={method:notes})
    if route==RECEIPTS:
        p.update(estimate_purpose="reference_scenario",reference_notice="법적 비용추계 첨부대상 여부와 별도인 부담금수입 참고추계. 정부지출과 합산·상계하지 않음")
    return p


def zero_band_review():
    return dict(bill_no="2208360",evidence_mode="development_review",cutoff_date="2026-10-11",
        decision_evidence_key="2208360:zero_employment_floor_change_not_estimated",reliable_estimation_basis_available=False,
        decision_facts=dict(zero_employment_floor_changed=True,zero_employment_new_multiplier_confirmed=False),
        decision_confirmations=dict(zero_band_scope_note="제33조 단서 최저임금이상 변경의 증분만 분리, 기본80%인상은 계산",
            zero_band_rate_basis_note="정답PDF5·13쪽의 구체인상수준미정 근거. 원문2배등 확정배수없으며0원증분이라는뜻아님"))


def run_regression(db_path=None):
    options={"variable_db_path":db_path} if db_path else {}; parts=[]
    for route,g,annual_gold in ((EXPENSE,2596,[481,500,519,538,558]),(RECEIPTS,11383,[2110,2191,2274,2360,2449])):
        p=sector_payload(route)
        if db_path:
            p["variable_db_path"]=str(db_path)
        result=estimate_routed_item(p)
        web=calculate_erce_web_item({**p,"bill_no":"SIMILAR_SECTOR_LEVY","evidence_mode":"holdout"},**options)
        annual=list(result.annual_amounts_thousand);total=sum(annual)/100000
        parts.append(dict(route=route,payload=p,result=dataclasses.asdict(result),web_result=web,total_eok=total,
            gold_display_total_eok=g,error_percent=abs(total-g)/g*100,annual_display_eok=[round(x/100000) for x in annual],
            annual_display_matches=sum(round(x/100000)==a for x,a in zip(annual,annual_gold)),
            displayed_total_matches=round(total)==g,engine_and_web_same=annual==web["annualAmountsThousand"]))
    review=zero_band_review()
    decision=validate_non_estimation_review(review,**({"db_path":db_path} if db_path else {}))
    return dict(bill_no="2208360",post_answer_regression=True,independent_evaluation=False,parts=parts,
        zero_band_review_payload=review,zero_band_decision=decision,
        limitation="정답확인후 공개구간 월단가를 저장한 회귀. 표시금액 일치와 원시합계 반올림차이를 구분. 선례 단가카드는 같은개정구조·전망시점에서만 승인후 재사용")


if __name__=="__main__":
    print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
