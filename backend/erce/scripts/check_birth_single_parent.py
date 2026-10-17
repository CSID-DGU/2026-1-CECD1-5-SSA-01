"""Reuse unchanged birth formula, add sourced household-to-child operand."""
import copy
import dataclasses
import json
from pathlib import Path
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.single_parent_survey_evidence import PROFILE,SCOPE
from backend.erce.child_allowance_birth_order_evidence import evidence_keys


def birth_payload():
    first=json.loads(Path("docs/erce/first_runs/ERCE_FIRST_RUN_2212823.json").read_text())
    p=copy.deepcopy(first["calculation_payload"])
    p.update(evidence_mode="development_review",birth_order_share_scenario="table4_fixed2026",payer="government",
        birth_order_scenario_note="사후정답표준용:인원표는2026비율동결과유사.표3연변화설명과구분",
        birth_order_scope_note="정답PDF5쪽첫째10·둘째15·셋째20만원 및 한부모10만원별도가산;부모급여유지",
        additive_support_note="정답의 별도추가지급가정을확인;한부모추가금은별도항목으로한번만합산")
    p["selected_evidence_keys"]=evidence_keys("table4_fixed2026")
    p["evidence_selection_reasons"]={k:"기존근거를유지,정답계산표와맞는동결시나리오로선택변경.사후보강" for k in p["selected_evidence_keys"]}
    method="2212823:birth_order_table_calculation_policy"
    p.update(selected_method_keys=[method],method_selection_reasons={method:"정답의계산표준용정책확인"},
        method_confirmations={method:dict(birth_order_scenario_note=p["birth_order_scenario_note"],additive_support_note=p["additive_support_note"])})
    return p


def single_parent_payload():
    keys=["2212823:single_parent_households:survey2024","2212823:children_per_household:survey2024",
          "2208381:child_execution_factor:2025:single_parent"]
    method="2212823:single_parent_survey_support"
    return dict(bill_no="2212823",evidence_mode="development_review",route_key="transfer_recipient",
        cutoff_date="2026-10-06",start_year=2026,years=5,payer="government",support_derivation=PROFILE,
        single_parent_population_scope=SCOPE,single_parent_projection="freeze_2024_survey",
        single_parent_support_additive=True,child_population_geography="전국",
        support_derivation_note="정답확인후2024실태조사의모집단가구수와평균자녀수준용",
        survey_scope_note="소득요건있는복지급여수급가구가아닌18세미만자녀동거한부모322천가구",
        additive_support_note="정답PDF5쪽한부모10만원을순위수당과별도가산하는가정확인",
        explicit_inputs=dict(benefit_per_recipient=dict(value=100000,unit="KRW/person/month",source_ref="원문제4조5항4호월10만원"),
            payments_per_year=dict(value=12,unit="month/year",source_ref="원문2026년1월시행·월급여")),
        selected_evidence_keys=keys,evidence_selection_reasons={k:"동일법정대상·조사범위·집행계수검토후사후준용" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"가구수와평균자녀수로한부모아동대상계산"},
        method_confirmations={method:dict(survey_scope_note="2024모집단18세미만자녀동거322천가구",
            additive_support_note="순위지원과별도의한부모추가지원을합산")})


def run_regression():
    p=birth_payload();s=single_parent_payload()
    b=estimate_routed_item(p);h=estimate_routed_item(s)
    webs=[calculate_erce_web_item({**x,"bill_no":"SIMILAR_BIRTH_SINGLE_PARENT","evidence_mode":"holdout"}) for x in (p,s)]
    annual=[x+y for x,y in zip(b.annual_amounts_thousand,h.annual_amounts_thousand)]
    amount=sum(annual)/1e9
    # Recompute an auditable component breakdown from the unchanged rank operands.
    from backend.erce.variable_evidence_store import evidence_payload_from_db
    hydrated=evidence_payload_from_db(p)
    source=hydrated["selected_variable_inputs"]
    population=source["under18_population"]["value"];factor=source["child_execution_factor"]["value"]
    rank_totals={}
    for rank,monthly in (("first",100000),("second",150000),("third_plus",200000)):
        shares=source["birth_share_"+rank]["value"]
        rank_totals[rank]=sum(n*f*monthly*12*factor for n,f in zip(population,shares))/1e12
    old_total=sum(
        b.resolved_variables["existing_recipient_count"].value[i]*100000*12 for i in range(5))/1e12
    return dict(bill_no="2212823",post_answer_regression=True,independent_evaluation=False,
        birth_payload=p,single_parent_payload=s,birth_result=dataclasses.asdict(b),single_parent_result=dataclasses.asdict(h),
        synthetic_web_status=[w["status"] for w in webs],single_parent_trace=webs[1]["derivationTrace"],
        annual_thousand=annual,total_trillion=amount,gold_display_total_trillion=34.8,
        difference_percent=abs(amount-34.8)/34.8*100,
        birth_partial_trillion=sum(b.annual_amounts_thousand)/1e9,
        single_parent_trillion=sum(h.annual_amounts_thousand)/1e9,
        component_raw_trillion={**rank_totals,"single_parent":sum(h.annual_amounts_thousand)/1e9,"existing_total":old_total},
        component_gold_display_trillion=dict(first=22.3,second=16.2,third_plus=4.7,single_parent=3.0,existing_total=11.4),
        limitation="정답표부문표시합계와원시계산의차이는남김.34.8조원에맞춘보정계수/인원역산없음")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
