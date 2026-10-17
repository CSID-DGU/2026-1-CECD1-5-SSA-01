import dataclasses
import json
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.owner_energy_repair_evidence import PROFILE


def repair_payload():
    keys=[f"2211430:{k}:reviewed" for k in ("repair_household_history","old_building_share","repair_increment_base","repair_cpi")]
    method="2211430:owner_energy_repair_grouped"
    notes=dict(annual_flow_note="연간실제지원흐름에수선주기가반영됨,다시3/5/7로나누지않음",
        repair_income_scope_note="정답의소득별80~100%차등미고려·상한100%지원시나리오,실제법정차등폐지가아님",
        repair_price_year_note="유사사업추가단가60/180/300만원2025가격기준.2026전망1.9%부터보정",
        estimation_start_note="정답사업준비기간2027~2031가정확인")
    return dict(bill_no="2211430",evidence_mode="development_review",cutoff_date="2026-10-08",
        route_key="direct_annual_amount",support_derivation=PROFILE,payer="government",start_year=2027,years=5,
        repair_recipient_scope="owner_annual_repair_flow",repair_increment_base_year=2025,
        repair_payment_scenario="upper_bound_100",repair_counts_rounding="half_up",
        support_derivation_note="정답확인후자가보수등급별연간대상과추가단가를분리하여합산",
        **notes,selected_evidence_keys=keys,evidence_selection_reasons={k:"보수범위·최근연간실적·노후비중·가격연도조건검토후사후준용" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"자가주택고효율시설추가급여"},
        method_confirmations={method:notes})


def run_regression():
    p=repair_payload();r=estimate_routed_item(p)
    web=calculate_erce_web_item({**p,"bill_no":"SIMILAR_OWNER_REPAIR","evidence_mode":"holdout"})
    total=sum(r.annual_amounts_thousand)/100000
    return dict(bill_no="2211430",post_answer_regression=True,independent_evaluation=False,
        payload=p,result=dataclasses.asdict(r),trace=web["derivationTrace"],reusable_web_status=web["status"],
        annual_eok=[v/100000 for v in r.annual_amounts_thousand],total_eok=total,gold_total_eok=880.7,
        error_percent=abs(total-880.7)/880.7*100,required_lower_filled=4,required_lower_count=4,
        excluded_information_system="정답의국토부확인:현행시스템처리가능,미대상",
        remaining_scope_note="에너지조사는정답에별도사업비로열거안됨.자동추가용역비/사유3호미추계판정안함",
        limitation="원단가와지급상한가정의사후회귀.독립성과아님.순수금액집계상위산식사용")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
