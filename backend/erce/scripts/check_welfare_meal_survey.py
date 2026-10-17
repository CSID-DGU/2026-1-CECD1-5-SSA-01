"""Regression against a version-unverified attached estimate, not a gold eval."""
import dataclasses
import json
from backend.erce.care_worker_survey_evidence import welfare_meal_safety_survey_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def meal_survey_payload():
    method = "2208199:meal_safety_integrated_survey_reference"
    keys = [r["evidence_key"] for r in welfare_meal_safety_survey_rows()]
    mismatch = "첨부 회답2025-02-03이 발의2025-02-17보다 앞서고 의안번호 공란. 동일 원문버전 미확인, 참고 추계로만 사용"
    notes = dict(meal_survey_scope_note="전국 사회복지급식소 운영·위생·영양 조사에 어린이 식생활안전 통합조사를 참고. 대상집단은 달라 과업·표본범위 검토할 가정. 전체 조사예산에 시설수를 중복 곱하지 않음",
        cycle_assumption_note="원문 주기는 총리령 위임. 어린이 통합조사의3년주기를 참고 가정으로 승인하며 법정 확정값 아님",
        price_projection_note="2023예산7.6억원에2024.12전망CPI를2024부터 매년 반영. 예산은 최신공식가격 아니며 조사비에 임금상승을 중복 반영하지 않음",
        first_survey_note="공포후3개월과 준비기간 고려2026첫조사 참고 가정. 기존조사 실적이나 확정시행연도로 단정하지 않음",
        unmatched_source_reference_note=mismatch)
    return dict(bill_no="2208199", evidence_mode="development_review", cutoff_date="2026-10-11",
        route_key="research_survey", payer="government", agency="식품의약품안전처", start_year=2026, years=5,
        research_service_function="social_welfare_meal_safety_survey", research_cost_scope="integrated_survey_budget",
        implementation_model="national_integrated_meal_safety_survey", estimate_purpose="reference_scenario",
        reference_notice=mismatch, use_unmatched_source_as_reference=True, unmatched_source_reference_note=mismatch,
        selected_evidence_keys=keys, evidence_selection_reasons={k: notes["meal_survey_scope_note"] for k in keys},
        selected_method_keys=[method], method_selection_reasons={method:"전국 식품위생·영양 통합조사 비용구조의 참고 재현"},
        method_confirmations={method:notes})


def run_regression(db_path=None):
    p = meal_survey_payload()
    if db_path:
        p["variable_db_path"] = str(db_path)
    r = estimate_routed_item(p)
    options = {"variable_db_path":db_path} if db_path else {}
    web = calculate_erce_web_item({**p,"bill_no":"SIMILAR_WELFARE_MEAL_SURVEY","evidence_mode":"holdout"}, **options)
    annual = list(r.annual_amounts_thousand); total = sum(annual)/100000
    return dict(bill_no="2208199", post_answer_regression=True, independent_evaluation=False,
        source_bill_version_match=False, evaluation_type="version_unverified_reference_regression",
        payload=p, engine_result=dataclasses.asdict(r), reusable_web_result=web,
        annual_amounts_thousand=annual, reference_total_eok=total, attached_display_total_eok=16.72,
        attached_display_error_percent=abs(total-16.72)/16.72*100,
        annual_million_display=[round(x/1000) for x in annual],
        annual_display_matches=sum(round(x/1000)==g for x,g in zip(annual,[811,0,0,861,0])),
        limitation="첨부 참고자료의 산식·가정 재현이지 동일 원문 정답의 독립 추계 성과가 아님. 재량 개선지원비는 조사비와 별도 검토")


if __name__ == "__main__":
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
