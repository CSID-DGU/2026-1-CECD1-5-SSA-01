import dataclasses
import json
from backend.erce.disabled_child_allowance_evidence import disabled_child_allowance_rows, PROFILE, SCOPE
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def child_allowance_payload():
    method = "2205274:child_allowance_mandatory_delta"
    keys = [r["evidence_key"] for r in disabled_child_allowance_rows()]
    notes = dict(child_allowance_scope_note="생계·의료급여 수급 만18세미만 등록아동만. 재학18~20세는 정답 행정자료 추출한계로 제외.",
        child_allowance_baseline_note="4집단별 적격자−현재수급자, 총10,615−10,314=미신청301명만 신규지급.",
        child_allowance_freeze_note="2024.11행복이음 대상·수급분포와2024집단별월단가·연12개월 동결 참고 가정.",
        child_allowance_start_note="공포즉시시행이지만 심사기간 고려2025~2029 정답 시나리오.")
    return dict(bill_no="2205274", evidence_mode="development_review", cutoff_date="2026-10-10",
        route_key=PROFILE, support_derivation=PROFILE, payer="government", start_year=2025, years=5,
        disability_child_scope=SCOPE, child_allowance_scenario_confirmed=True,
        child_allowance_projection="freeze_202411_cohort_and_2024_rate", **notes,
        selected_evidence_keys=keys, evidence_selection_reasons={k: "동일 만18세미만 생계·의료수급4집단의 기준실적과 지급액 검토" for k in keys},
        selected_method_keys=[method], method_selection_reasons={method: "기존급여 의무화의 미신청자 순증만 계산"},
        method_confirmations={method: notes})


def run_regression():
    p = child_allowance_payload(); result = estimate_routed_item(p)
    web = calculate_erce_web_item({**p, "bill_no": "SIMILAR_CHILD_ALLOWANCE_MANDATORY", "evidence_mode": "holdout"})
    annual = list(result.annual_amounts_thousand)
    if annual != web["annualAmountsThousand"]:
        raise ValueError("개발회귀·웹재사용 계산 불일치")
    total = sum(annual) * 1000
    return dict(bill_no="2205274", post_answer_regression=True, independent_evaluation=False,
        payload=p, result=dataclasses.asdict(result), web_result=web, total_won=total, gold_total_won=2325000000,
        error_percent=abs(total - 2325000000) / 2325000000 * 100,
        annual_matches=sum(x == 465000 for x in annual), official_scope_complete=annual == [465000] * 5)


if __name__ == "__main__":
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
