import json
from dataclasses import asdict
from backend.erce.protected_child_insurance_evidence import PROFILE,NOTES,protected_child_insurance_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.method_evidence_store import validate_non_estimation_review


def insurance_payload(answer_reference=False):
    method = "2216665:protected_child_insurance_population_share"
    notes = dict(zip(NOTES,[
        "기존가정위탁보험지원분 제외. 시설·공동생활 보호아동을 비중대리로 산출하는 가정",
        "본문2020~2024평균비중0.17%의 표시값 준용. 원관측·실제평균의추가자릿수미검증. 정밀도를맞춰역산하지 않음",
        "공식2025보험료연68500원내외 시설아동준용·연1회전액·가격동결. 실제단체보험견적 아님"
    ]))
    p = dict(bill_no="2216665",route_key=PROFILE,support_derivation=PROFILE,payer="government",
        evidence_mode="development_review",cutoff_date="2026-10-14",start_year=2027,years=5,
        protected_child_model_confirmed=True,protected_child_premium_mode="freeze_reference_premium",
        protected_child_age_basis="under18_law",**notes,explicit_inputs={},
        selected_evidence_keys=[r["evidence_key"] for r in protected_child_insurance_rows()],
        selected_method_keys=[method],method_selection_reasons={method:"고정인원 대신 비중과장래인구를 분리"},
        method_confirmations={method:notes})
    p["evidence_selection_reasons"] = {k:"법적연령기준과표시비중·공식보험료 준용가정 확인" for k in p["selected_evidence_keys"]}
    if answer_reference:
        p.update(estimate_purpose="reference_scenario",protected_child_age_basis="under19_answer_reference",
            protected_child_age_conflict_approved=True,
            protected_child_age_conflict_note="정답5개년인원은0~18세×0.17%로모두재현되나 본문은18세미만.참고재현만하고법적연령기준바꾸지않음")
    return p


def survey_review_payload():
    return dict(bill_no="2216665",evidence_mode="development_review",cutoff_date="2026-10-14",
        decision_evidence_key="2216665:protected_child_survey_expansion_not_estimated",
        reliable_estimation_basis_available=False,
        decision_confirmations=dict(protected_survey_scope_note="제11조대상추가에추가조사원·기간비용가능성",
            protected_survey_design_review_note="정답PDF2쪽표본크기·선정·문항 미확정 근거확인.새설계확보되면재추계"),
        decision_facts=dict(expanded_sample_size_confirmed=False,sampling_design_confirmed=False,
                           additional_survey_items_confirmed=False))


def run_regression(db_path=None):
    runs = {}
    for mode in (False,True):
        p = insurance_payload(mode)
        if db_path:
            p["variable_db_path"] = str(db_path)
        r = estimate_routed_item(p)
        runs["answer_reference" if mode else "law_under18"] = dict(payload=p,result=asdict(r))
    annual = list(runs["answer_reference"]["result"]["annual_amounts_thousand"])
    total = sum(annual)/100000
    review = validate_non_estimation_review(survey_review_payload(),**({"db_path":db_path} if db_path else {}))
    web = calculate_erce_web_item({**insurance_payload(True),"bill_no":"SYNTHETIC_PROTECTED_CHILD_INSURANCE"},
        **({"variable_db_path":db_path} if db_path else {}))
    return dict(bill_no="2216665",post_answer_regression=True,independent_evaluation=False,
        reference_scenario=True,runs=runs,total_eok=total,gold_display_total_eok=35.93,
        raw_error_percent=abs(total-35.93)/35.93*100,
        annual_million_display=[round(x/1000) for x in annual],
        annual_display_matches=sum(round(x/1000)==g for x,g in zip(annual,[767,742,720,694,670])),
        law_under18_total_eok=sum(runs["law_under18"]["result"]["annual_amounts_thousand"])/100000,
        survey_expansion_review=review,web_interface_result=web,
        limitation="정답숫자는0~18세대리와재현되지만본문18세미만과불일치. 원평균비중미검증.참고재현을법적기준완성·독립성과로주장안함")


if __name__ == "__main__":
    print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
