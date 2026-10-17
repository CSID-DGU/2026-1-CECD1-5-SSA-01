import dataclasses
import json
from backend.erce.standard_workplace_evidence import standard_workplace_rows,PROFILE
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.method_evidence_store import validate_non_estimation_review


def workplace_payload(scenario="increase1"):
    method="2200200:standard_workplace_application_expansion"
    keys=[r["evidence_key"] for r in standard_workplace_rows() if r.get("application_growth_scenario") in (None,scenario)]
    notes=dict(workplace_indirect_scope_note="공동출자허용에 따른 기존설립지원 신청증가를 가정. 국가가 민간주식에 출자하는 비용이 아님.",
        workplace_quantity_note=f"자회사형79개 기준 {scenario} 매년고정증분. 신규신청을 복리·누적기존보조로 계산하지 않음.",
        workplace_budget_note="신청증가가 자동예산증가를 뜻하지는 않지만 정답처럼 예산제약을 완화해 추가지원하는 시나리오 승인.",
        workplace_price_note="2024평균지원2.95억원·2024.3CPI2025부터 적용. 투자액3/4나최대10억원을 다시 적용하지 않음.")
    return dict(bill_no="2200200",evidence_mode="development_review",cutoff_date="2026-10-10",
        route_key=PROFILE,support_derivation=PROFILE,payer="government",start_year=2025,years=5,
        workplace_form="subsidiary_joint_investment",application_growth_scenario=scenario,
        application_increase_mode="fixed_annual_increment_from_base",standard_grant_price_year=2024,
        workplace_scenario_confirmed=True,budget_expansion_assumed=True,**notes,
        selected_evidence_keys=keys,evidence_selection_reasons={k:"자회사형지원 과업·기준물량·평균단가·신청증분과 예산가정 확인" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"규제완화의 기존공공보조 수요증가 시나리오"},
        method_confirmations={method:notes})


def capacity_payload():
    return dict(bill_no="2200200",evidence_mode="development_review",cutoff_date="2026-10-10",
        decision_evidence_key="2200200:certification_existing_capacity",reliable_estimation_basis_available=False,
        decision_facts=dict(existing_administration_sufficient=True),
        decision_confirmations=dict(certification_capacity_note="정답PDF3의 당시기존행정력으로 인증·취소이행가능 판단을 준용, 새증원·위탁이 확인되면 재검토"))


def run_regression():
    gold=dict(increase1=(15.73,[301,308,315,321,328]),increase5=(62.93,[1206,1232,1258,1285,1312]),
              increase10=(125.87,[2412,2465,2517,2570,2624]))
    parts=[]
    for scenario,(total_gold,annual_gold) in gold.items():
        p=workplace_payload(scenario);result=estimate_routed_item(p)
        web=calculate_erce_web_item({**p,"bill_no":"SIMILAR_STANDARD_WORKPLACE_EXPANSION","evidence_mode":"holdout"})
        annual=list(result.annual_amounts_thousand)
        if annual!=web["annualAmountsThousand"]:raise ValueError("개발회귀·웹재사용 불일치")
        total=sum(annual)/100000
        parts.append(dict(scenario=scenario,payload=p,result=dataclasses.asdict(result),trace=web["derivationTrace"],
            total_eok=total,gold_total_eok=total_gold,error_percent=abs(total-total_gold)/total_gold*100,
            annual_display_matches=sum(round(v/1000)==g for v,g in zip(annual,annual_gold))))
    return dict(bill_no="2200200",post_answer_regression=True,independent_evaluation=False,parts=parts,
        capacity_review_payload=capacity_payload(),capacity_decision=validate_non_estimation_review(capacity_payload()))


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
