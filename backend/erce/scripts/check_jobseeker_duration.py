import copy
import dataclasses
import json
from pathlib import Path
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.method_evidence_store import validate_non_estimation_review
from backend.erce.jobseeker_duration_evidence import PROFILE


def price_payload():
    return copy.deepcopy(json.loads(Path("docs/erce/first_runs/ERCE_FIRST_RUN_2208052.json").read_text())["price_increase_payload"])


def extension_payload():
    p=price_payload()
    p.update(route_key="transfer_recipient",support_derivation=PROFILE,evidence_mode="development_review",
        payment_behavior_rule="proportional_existing_payment_utilization",
        payment_period_projection_note="정답의수령행태비례유지가정확인.실평균5.2/상한6×연장6=추가5.2개월",
        cash_component_separation_note="기존5.2개월은단가인상항목,추가개월에만개정단가적용",
        estimation_start_note="공포후6개월의정답2026~2030시작가정")
    p["explicit_inputs"]["old_statutory_months"]=dict(value=6,unit="month",source_ref="원문PDF5쪽현행6개월")
    p["explicit_inputs"]["new_statutory_months"]=dict(value=12,unit="month",source_ref="원문PDF5쪽1년을12개월환산")
    p["selected_evidence_keys"]=[k+":cash_duration" if k.startswith("2207706:") else k for k in p["selected_evidence_keys"]]
    p["evidence_selection_reasons"]={k:"기존고용실적·생계연동값유지,기간연장하위산식용별칭" for k in p["selected_evidence_keys"]}
    method="2208052:cash_duration_utilization"
    p.update(selected_method_keys=[method],method_selection_reasons={method:"단가·기간동시변경의비례수령행태확인"},
        method_confirmations={method:dict(payment_period_projection_note=p["payment_period_projection_note"],
            cash_component_separation_note=p["cash_component_separation_note"],estimation_start_note=p["estimation_start_note"])})
    return p


def service_payload():
    return dict(bill_no="2208052",cutoff_date="2026-10-06",evidence_mode="development_review",
        decision_evidence_key="2208052:service_component_not_estimated",reliable_estimation_basis_available=False,
        decision_facts=dict(service_duration_extended=True,cash_duration_change_separately_estimated=True,
            reliable_incremental_staffing_available=False,reliable_incremental_operating_cost_available=False),
        decision_confirmations=dict(service_component_scope="제15조상담서비스추가인건비/운영비범위에한정",
            cash_component_separation="제19·20조수당단가와기간증가는별도추계;법안전체수당기간불변이라고판단안함",
            staffing_operating_basis_review="당시정답의장래상담사/운영계획자료미확정확인.최신모든후속자료부재를전수확인한것아님"))


def run_regression():
    p=price_payload();q=extension_payload()
    a=estimate_routed_item(p);b=estimate_routed_item(q)
    web=calculate_erce_web_item({**q,"bill_no":"SIMILAR_CASH_DURATION","evidence_mode":"holdout"})
    decision=validate_non_estimation_review(service_payload())
    similar=validate_non_estimation_review({**service_payload(),"bill_no":"SIMILAR_CONCURRENT_SERVICE","evidence_mode":"holdout"})
    annual=[x+y for x,y in zip(a.annual_amounts_thousand,b.annual_amounts_thousand)]
    total=sum(annual)/100000
    return dict(bill_no="2208052",post_answer_regression=True,independent_evaluation=False,
        price_result=dataclasses.asdict(a),extension_result=dataclasses.asdict(b),
        extension_payload=q,extension_trace=web["derivationTrace"],reusable_web_status=web["status"],
        annual_eok=[x/100000 for x in annual],partial_total_eok=total,gold_partial_total_eok=68167,
        error_percent=abs(total-68167)/68167*100,
        actual_extra_payment_months=b.resolved_variables["payments_per_year"].value,
        service_review=decision,synthetic_service_review=similar,whole_bill_total=None,
        limitation="수당비용일부추계와서비스미추계사후재현.최초8.3개월후보의28.65%오차기록유지")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
