import json
from dataclasses import asdict
from backend.erce.facility_survey_expansion_evidence import PROFILE, NOTES, facility_survey_expansion_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.method_evidence_store import validate_non_estimation_review


def expansion_payload():
    method = "2210775:facility_survey_scope_expansion_delta"
    notes = dict(zip(NOTES,[
        "기존국비시설526중약80표본 조사와 법제화대상범위를 비교. 확대실시를 선례시나리오로 가정, 원문전수명령 확정아님",
        "2023편의시설 실태전수조사5억원을 인권조사규모확대 비용으로 준용. 둘은 같은사업이 아니므로 유사예산 가정",
        "현행2025시설인권조사예산1억원은 같은조사 기존분이므로 차감. 새기관·인력은 추가하지 않음",
        "2026~2030매년실시·두예산모두가격동결 가정. 최신공식 단가로 주장하지 않음"
    ]))
    keys = [r["evidence_key"] for r in facility_survey_expansion_rows()]
    return dict(bill_no="2210775",evidence_mode="development_review",cutoff_date="2026-10-12",
        route_key=PROFILE,support_derivation=PROFILE,payer="government",start_year=2026,years=5,
        facility_expansion_scenario_confirmed=True,facility_price_mode="freeze_reference_budget",
        **notes,explicit_inputs={},selected_evidence_keys=keys,
        evidence_selection_reasons={k:"시설표본·기준범위 및 확대사업 예산·현행예산 차감 가정 확인" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"기존사업 중복제외 대신 표본확대 순증추계"},
        method_confirmations={method:notes})


def unchanged_review_payload():
    return dict(bill_no="SYNTHETIC_EXISTING_FACILITY_SURVEY",evidence_mode="holdout",cutoff_date="2026-10-12",
        decision_evidence_key="2210775:facility_survey_unchanged_scope_review",
        reliable_estimation_basis_available=True,
        decision_confirmations=dict(existing_survey_scope_evidence_note="검사입력: 비교근거 별도 확인",
            unchanged_scope_comparison_note="검사입력: 같은표본·주기·공표범위 유지 가정"),
        decision_facts=dict(existing_coverage_comparison_complete=True,survey_target_and_sample_unchanged=True,
            survey_frequency_unchanged=True,separate_publication_expansion_confirmed=False,
            new_service_scope_or_staffing_expansion_confirmed=False))


def run_regression(db_path=None):
    p = expansion_payload()
    if db_path:
        p["variable_db_path"] = str(db_path)
    result = estimate_routed_item(p)
    options = {"variable_db_path":db_path} if db_path else {}
    web = calculate_erce_web_item({**expansion_payload(),"bill_no":"SYNTHETIC_FACILITY_EXPANSION"},**options)
    annual = list(result.annual_amounts_thousand)
    if annual != web["annualAmountsThousand"]:
        raise ValueError("facility expansion engine/web mismatch")
    bad = unchanged_review_payload()
    bad["decision_facts"] = {**bad["decision_facts"],"existing_coverage_comparison_complete":False}
    try:
        validate_non_estimation_review(bad,**({"db_path":db_path} if db_path else {}))
    except ValueError:
        unverified_baseline_exclusion_blocked = True
    else:
        unverified_baseline_exclusion_blocked = False
    return dict(bill_no="2210775",post_answer_regression=True,independent_evaluation=False,
        payload=p,result=asdict(result),web_interface_result=web,total_eok=sum(annual)/100000,
        gold_total_eok=20,error_percent=abs(sum(annual)/100000-20)/20*100,
        annual_display_matches=sum(a==400000 for a in annual),
        unverified_baseline_exclusion_blocked=unverified_baseline_exclusion_blocked,
        limitation="정답의조사규모확대·유사예산·현행예산차감을 채택한 사후회귀. 법제화가 무조건전수확대된다는 규칙 아님")


if __name__ == "__main__":
    print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
