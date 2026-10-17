"""Official population + explicit linear ratio scenario, not exact gold fitting."""
import dataclasses
import json
from backend.erce.disability_expansion_evidence import projected_recipient_row
from backend.erce.scripts.check_disability_expansion import payload
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def projected_payload():
    p=payload();row=projected_recipient_row()
    p.update(disability_population_basis="official_population_linear_ratio_trend",
        population_proxy_note="공식18세이상전망×수급권자비율OLS추세.동결아님.정답의구체추세모형은미확인")
    p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if not any(n in k for n in
        ("expanded_eligible_reference","existing_eligible_reference"))]+[row["evidence_key"]]
    p["evidence_selection_reasons"][row["evidence_key"]]="공식인구전망과실적비율로구한검토용OLS추세후보"
    return p


def run_regression():
    p=projected_payload();r=estimate_routed_item(p)
    web=calculate_erce_web_item({**p,"bill_no":"SYNTHETIC_OFFICIAL_POPULATION","evidence_mode":"holdout"})
    total=sum(r.annual_amounts_thousand)
    return dict(bill_no="2203497",post_answer_regression=True,independent_evaluation=False,
        payload=p,result=dataclasses.asdict(r),population_evidence=projected_recipient_row(),
        total_thousand=total,gold_total_thousand=5472400000,
        difference_percent=abs(total-5472400000)/5472400000*100,
        synthetic_web_status=web["status"],
        unresolved="2018~2022년연령구성평균·정답의구체비율추세모형·지급단가표/주석불일치 미확인.정답확인후 시나리오 비교,독립평가아님")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
