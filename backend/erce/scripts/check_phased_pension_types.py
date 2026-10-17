"""Observed payment types and additive ablations; no answer-budget replay."""
import dataclasses
import json
from backend.erce.phased_pension_types import PROFILE,phased_pension_type_rows
from backend.erce.scripts.check_phased_couple_pension import payload as pooled_payload
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def payload(recovery="shared_unreduced_proxy"):
    p=pooled_payload();rows=phased_pension_type_rows()
    p.update(support_derivation=PROFILE,pension_distribution_basis="payment_household_types_2021_2024",
        reduced_couple_recovery=recovery,
        pension_type_trend_note="공식전액/감액×부부수급4집단의2021~2024구성비를각각OLS전망.정답미공개NR별교차표와동일분류라는주장아님",
        reduced_group_split_note="감액수급자의단독/부부각평균급여미공개.관측총지급액과전액집단실적으로공통감액전지급비율을조건부식별.같은NR/소득역전제약비율준용가정")
    p["selected_evidence_keys"]=[r["evidence_key"] for r in rows]
    p["evidence_selection_reasons"]={r["evidence_key"]:"유형별공식관측실적·기간·전망버전일치.감액집단급여분리는명시적가정" for r in rows}
    return p


def run_regression():
    pooled=estimate_routed_item(pooled_payload());runs=[]
    for recovery in ("standard_amount_ablation","shared_unreduced_proxy"):
        p=payload(recovery);r=estimate_routed_item(p)
        web=calculate_erce_web_item({**p,"bill_no":"SYNTHETIC_PENSION_TYPES","evidence_mode":"holdout"})
        total=sum(r.annual_amounts_thousand)
        runs.append(dict(model=recovery,payload=p,result=dataclasses.asdict(r),total_thousand=total,
            difference_percent=abs(total-30100000000)/30100000000*100,
            group_trace=web["derivationTrace"],synthetic_web_status=web["status"]))
    old=sum(pooled.annual_amounts_thousand);mix=runs[0]["total_thousand"];typed=runs[1]["total_thousand"]
    effects=runs[1]["group_trace"][-1]
    expansion=sum(effects["eligibility_expansion_won"])/1e12
    recovery=sum(effects["reduction_recovery_won"])/1e12
    return dict(bill_no="2211669",post_answer_regression=True,independent_evaluation=False,
        published_answer_budget_used_as_input=False,pooled_total_thousand=old,runs=runs,
        decomposition=dict(type_trend_and_price_mixture_effect_thousand=mix-old,
            reduced_group_retention_effect_thousand=typed-mix,total_change_thousand=typed-old),
        gold_effect_comparison=dict(eligibility_expansion_trillion=expansion,reduction_recovery_trillion=recovery,
            gold_display_expansion_trillion=13.4,gold_display_recovery_trillion=16.7,
            expansion_gap_trillion=expansion-13.4,recovery_gap_trillion=recovery-16.7,
            limitation="정답표4항목별연도표시값합계와비교,0.1조원표시반올림불확실성있음"),
        limitation="우리모형교체효과및정답표의재정요인2개별차이는분해했으나인원·단가각각의유일한오차기여도는미확정.전액/감액유형은NR원인별교차유형과다름.감액집단별가격은공통감액전비율가정")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
