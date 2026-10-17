import json
from pathlib import Path
from backend.erce.education_training_budget_evidence import PROFILE, NOTES
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item

FIRST_RUN = Path(__file__).resolve().parents[3]/"docs/erce/first_runs/ERCE_FIRST_RUN_2209738.json"


def training_payload():
    method = "2209738:education_training_package_freeze"
    key = "2209738:education_training_annual_budget:2025"
    notes = dict(zip(NOTES, [
        "금융교육의 콘텐츠제작·강사육성·교재·교육을 동일 교육통합과업으로 준용",
        "장애인교육과 아동금융교육 대상은 다르나 같은 연간사업규모를 준용하는 정답의 가정",
        "적립금과는 별도, 콘텐츠·강사·교재·교육비는 패키지내부로 중복합산하지 않음",
        "2025교육사업7억원을2026~2030 매년실시·가격동결하는 선례. 최신공식 단가 아님"
    ]))
    return dict(bill_no="2209738",route_key=PROFILE,support_derivation=PROFILE,
        evidence_mode="development_review",cutoff_date="2026-10-12",start_year=2026,years=5,
        payer="government",training_package_confirmed=True,training_price_mode="freeze_reference_budget",
        **notes,explicit_inputs={},selected_evidence_keys=[key],
        evidence_selection_reasons={key:"강사육성·콘텐츠·교재·교육이 포함된 전체사업 선례"},
        selected_method_keys=[method],method_selection_reasons={method:"통합교육과업·매년시행·가격동결 확인"},
        method_confirmations={method:notes})


def run_regression(db_path=None):
    first = json.loads(FIRST_RUN.read_text())
    primary = first["primary_payload"]
    # Keep the already-correct pre-answer quantity and monthly formula unchanged.
    options = {"variable_db_path":db_path} if db_path else {}
    cash = calculate_erce_web_item(primary,**options)
    p = training_payload()
    if db_path:
        p["variable_db_path"] = str(db_path)
    education = estimate_routed_item(p)
    edu = list(education.annual_amounts_thousand)
    annual = [x+y for x,y in zip(cash["annualAmountsThousand"],edu)]
    total = sum(annual)/100000
    web = calculate_erce_web_item({**training_payload(),"bill_no":"SYNTHETIC_TRAINING_PACKAGE"},**options)
    gold = [57571,55612,53737,51709,49075]
    return dict(bill_no="2209738",post_answer_regression=True,independent_evaluation=False,
        primary_payload_unchanged=True,primary_payload=primary,primary_result=cash,
        education_payload=p,education_annual_thousand=edu,education_total_eok=sum(edu)/100000,
        combined_annual_thousand=annual,total_eok=total,gold_display_total_eok=267705,
        raw_error_percent=abs(total-267705)/267705*100,
        annual_eok_display=[round(x/100000) for x in annual],
        annual_display_matches=sum(round(x/100000)==g for x,g in zip(annual,gold)),
        whole_scope_complete_against_gold=True,reusable_web_interface_result=web,
        limitation="정부적립금은 최초정답미열람에서 맞았지만 교육은 정답확인후보강. 전체독립성과 아님")


if __name__ == "__main__":
    print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
