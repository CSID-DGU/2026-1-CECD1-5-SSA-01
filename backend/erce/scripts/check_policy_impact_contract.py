import dataclasses
import json
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.policy_impact_research_evidence import policy_impact_research_rows


def impact_payload():
    method = "2201364:annual_policy_impact_contract"
    keys = [r["evidence_key"] for r in policy_impact_research_rows()]
    notes = dict(annual_package_scope_note="연간 정책영향평가 연구용역1개 패키지 가정. 개별 정책건수에2억원을 곱하지 않음.",
                 cross_domain_task_note="기술의 경제사회환경 영향 연구와 인구정책의 인구변화 영향 연구가 유사한 분석평가 과업이라는 정답의 준용 가정.",
                 price_freeze_note="2024 기술영향평가 정책연구예산2억원을 추계기간 동결, 최신 실적이나 공식 건당 단가 아님.",
                 estimation_start_note="공포후6개월 및 심사기간을 고려한2025~2029 정답 준비 시나리오. 보고공표는 연구결과 활용 작업으로 보고 별도 금액을 자동 가산하지 않음.")
    return dict(bill_no="2201364", evidence_mode="development_review", cutoff_date="2026-10-10",
        route_key="policy_impact_annual_contract", payer="government", start_year=2025, years=5,
        research_service_function="policy_impact_annual_contract", research_cost_scope="research_contract_only",
        selected_evidence_keys=keys, evidence_selection_reasons={k: "유사 연간영향평가 과업·패키지 범위와 예산 기준년 검토" for k in keys},
        selected_method_keys=[method], method_selection_reasons={method: "정책건별 미확정 단가 대신 승인한 연간 패키지 참고 가정"},
        method_confirmations={method: notes})


def run_regression():
    p = impact_payload(); result = estimate_routed_item(p)
    web = calculate_erce_web_item({**p, "bill_no": "SIMILAR_ANNUAL_POLICY_IMPACT", "evidence_mode": "holdout"})
    annual = list(result.annual_amounts_thousand)
    if annual != web["annualAmountsThousand"]:
        raise ValueError("개발 회귀와 웹 재사용 경로 계산 불일치")
    total = sum(annual) * 1000
    return dict(bill_no="2201364", post_answer_regression=True, independent_evaluation=False,
        payload=p, result=dataclasses.asdict(result), web_result=web, annual_thousand=annual,
        total_won=total, gold_total_won=1000000000, error_percent=abs(total - 1000000000) / 1000000000 * 100,
        annual_matches=sum(x == 200000 for x in annual),
        official_scope_complete=annual == [200000] * 5 and web["status"] == "computed_review")


if __name__ == "__main__":
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
