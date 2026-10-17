import json
from dataclasses import asdict
from backend.erce.scripts.check_qualification_exam import exam_payload
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.method_evidence_store import validate_non_estimation_review


def later_exam_payload(include_target_projection=True):
    p = exam_payload(False)
    method = "2210347:qualification_exam_stock_flow"
    p.update(bill_no="2210347",cutoff_date="2026-10-12",exam_linked_dependency_present=False,
        exam_linked_bill_assumed_passed=False,selected_method_keys=[method],
        method_selection_reasons={method:"원문특례3년과국가시험 전환에 맞는 재고·신규·재응시 구조"},
        exam_population_note="현재원문에는2207049연계전제 없음. 정답의 제공인원51.3%초기응시·후속언어/발달순증전체를 조건부추계가정으로 승인. 의무가입 확정아님",
        exam_transition_note="현재원문PDF7~8쪽 특례3년. 최초재고 첫해응시·특례전원합격·4년차정규실패32%재응시는 선례가정",
        exam_start_note="현재원문공포후2년.2025공포 가정2027~2031. 실제공포일 확인아님")
    p["explicit_inputs"] = {"exam_special_duration_years":dict(value=3,unit="year",
        source_ref="2210347 원문PDF7~8쪽 시행이후3년이내 특례.3년연속운영은 선례가정")}
    if include_target_projection:
        p["selected_evidence_keys"].append("2210347:service_provider_forecast:2027-2031:target_only")
    p["evidence_selection_reasons"] = {k:"공통시험단가·가정은준용.인원전망은2210347자기정답사후회귀에만사용" for k in p["selected_evidence_keys"]}
    p["method_confirmations"] = {method:{k:p[k] for k in (
        "exam_scope_note","exam_population_note","exam_transition_note","exam_price_note","exam_start_note")}}
    return p


def association_payload():
    return dict(bill_no="2210347",evidence_mode="development_review",cutoff_date="2026-10-12",
        decision_evidence_key="2210347:association_existing_operations",
        reliable_estimation_basis_available=True,
        decision_confirmations=dict(existing_association_note="정답PDF2쪽2023동일협회설립 근거 확인. 현재현황독립검증아님",
            association_scope_overlap_note="전문영역교육·행사를 이미수행. 새정부위탁·순증확정 없는 동일사업 설립근거"),
        decision_facts=dict(same_association_already_established=True,
            same_training_events_already_provided=True,new_scope_or_public_funding_confirmed=False))


def run_regression(db_path=None):
    p = later_exam_payload()
    if db_path:
        p["variable_db_path"] = str(db_path)
    result = estimate_routed_item(p)
    options = {"variable_db_path":db_path} if db_path else {}
    association = validate_non_estimation_review(association_payload(),**({"db_path":db_path} if db_path else {}))
    missing = calculate_erce_web_item({**later_exam_payload(False),"bill_no":"NEW_LATER_EXAM"},**options)
    annual = list(result.annual_amounts_thousand)
    total = sum(annual)/100000
    return dict(bill_no="2210347",post_answer_regression=True,independent_evaluation=False,
        payload=p,result=asdict(result),association_review=association,association_payload=association_payload(),
        total_eok=total,gold_display_total_eok=58.93,raw_error_percent=abs(total-58.93)/58.93*100,
        annual_million_display=[round(x/1000) for x in annual],
        annual_display_matches=sum(round(x/1000)==g for x,g in zip(annual,[4848,279,251,229,286])),
        new_bill_missing_projection_result=missing,
        limitation="시험표와협회별도추계제외는 재현. 협력체계는 정답추계범위에 없으나 금액0이나 법정미추계로 단정하지 않음. 새의안인원 자동전망은 미완성")


if __name__ == "__main__":
    print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
