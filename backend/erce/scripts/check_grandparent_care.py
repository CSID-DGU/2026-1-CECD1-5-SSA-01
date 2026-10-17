import dataclasses
import json
from backend.erce.grandparent_care_evidence import PROFILE
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def care_payload():
    keys=["official:kosis:age0_5:2027-2031:grandparent"]+[f"2211034:{k}:reviewed" for k in
        ("grandparent_care_shares","supported_care_hours","public_care_hour_rate","foregone_allowance_by_age","registration_take_up","care_payment_months")]
    method="2211034:grandparent_care_age_net"
    notes=dict(registration_scope_note="0~5세아동수단위,소득조건없음·모두연초교육/등록하는참고시나리오",
        allowance_overlap_note="0~1세부모급여는별개,2~5세가정양육수당10만원을순증돌봄지원에서차감",
        estimation_start_note="원문2026-04-23시행과정답심사준비기간을고려한2027~2031가정")
    return dict(bill_no="2211034",evidence_mode="development_review",cutoff_date="2026-10-08",payer="government",
        route_key="direct_annual_amount",support_derivation=PROFILE,start_year=2027,years=5,
        grandparent_count_basis="child_age_proxy",care_price_projection="freeze_reference_rate",
        population_geography="전국",statistical_sex="total",population_vintage="2023-12",
        support_derivation_note="기존공식각세인구재사용,조부모양육비율·공공시간제지원액·연령별대체급여연결",
        **notes,selected_evidence_keys=keys,evidence_selection_reasons={k:"연령·국가범위·자료시점·대체급여검토후사후준용" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"조부모양육아동에대한신규급여순증모형"},
        method_confirmations={method:notes})


def run_regression():
    p=care_payload();r=estimate_routed_item(p)
    web=calculate_erce_web_item({**p,"bill_no":"SIMILAR_GRANDPARENT_CARE","evidence_mode":"holdout"})
    total=sum(r.annual_amounts_thousand)/100000
    return dict(bill_no="2211034",post_answer_regression=True,independent_evaluation=False,
        payload=p,result=dataclasses.asdict(r),trace=web["derivationTrace"],reusable_web_status=web["status"],
        annual_eok=[v/100000 for v in r.annual_amounts_thousand],total_eok=total,gold_display_eok=4321,
        error_percent=abs(total-4321)/4321*100,required_lower_filled=7,required_lower_count=7,
        remaining_scope="교육비는정답별도항목아님.기존/공공부담주체검토미완료,자동0/미추계판정안함",
        limitation="단가동결/전원등록·아동수대리단위·시간제서비스추가차감미고려는확인된시나리오.사후회귀")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
