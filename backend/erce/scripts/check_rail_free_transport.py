import dataclasses
import json
from backend.erce.rail_free_transport_evidence import rail_free_transport_rows, PROFILE, ROUTE
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def rail_payload():
    method = "2204465:disabled_urban_rail_compensation"
    keys = [r["evidence_key"] for r in rail_free_transport_rows()]
    notes = dict(rail_scope_note="장애인·동행보호자 도시철도 승차 연인원, 등록장애인 고유수와 노인무임비용 제외.",
                 korail_exclusion_note="코레일은 이미PSO 공공운임감면 보상. 나머지 도시철도 운영기관 손실만 신규지원 참고.",
                 rail_trend_note="정답의 최근추세 표를 사후 비교하여 승차연인원 선형OLS·회당손실단가 로그OLS 선택. 원문/추계서에 회귀식 명시된 것은 아님.",
                 rail_fiscal_share_note="정답처럼 장애인 도시철도 무임손실 국가전액보전 가정. 실제지원율 확정근거가 있으면 우선.",
                 rail_start_note="공포후3개월·심사기간 고려2025~2029 정답 시나리오.")
    return dict(bill_no="2204465", evidence_mode="development_review", cutoff_date="2026-10-10",
        route_key=ROUTE, support_derivation=PROFILE, payer="government", start_year=2025, years=5,
        rail_beneficiary_scope="disabled_and_one_companion", rail_operator_scope="urban_rail_excluding_korail_pso",
        rail_compensation_scenario_confirmed=True, rail_volume_trend="linear_ols", rail_fare_trend="log_ols", **notes,
        selected_evidence_keys=keys, evidence_selection_reasons={k: "동일 장애인 도시철도 승차·손실 실적, 전액보전 참고 가정 검토" for k in keys},
        selected_method_keys=[method], method_selection_reasons={method: "교통수단·기존지원·추세를 분리한 참고 모델"},
        method_confirmations={method: notes})


def run_regression():
    p = rail_payload(); result = estimate_routed_item(p)
    web = calculate_erce_web_item({**p, "bill_no": "SIMILAR_DISABLED_URBAN_RAIL", "evidence_mode": "holdout"})
    annual = list(result.annual_amounts_thousand)
    if annual != web["annualAmountsThousand"]:
        raise ValueError("개발회귀·웹재사용 계산 불일치")
    total = sum(annual) / 100000
    return dict(bill_no="2204465", post_answer_regression=True, independent_evaluation=False,
        payload=p, result=dataclasses.asdict(result), web_result=web, total_eok=total,
        gold_display_total_eok=18418, error_percent=abs(total - 18418) / 18418 * 100,
        annual_display_matches=sum(round(v / 100000) == g for v, g in zip(annual, [2950, 3328, 3693, 4048, 4399])),
        limitation="과거실적과 사후선택 추세모델 보강회귀. 미래정답대상수를 DB에 넣지 않았으며 첫실행 성과가 아님")


if __name__ == "__main__":
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
