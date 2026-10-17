import dataclasses
import json
from backend.erce.disabled_worker_wage_evidence import disabled_worker_wage_rows, PROFILE
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def worker_payload(scenario="share100"):
    method = "2200664:disabled_worker_wage_gap"
    keys = [r["evidence_key"] for r in disabled_worker_wage_rows() if r.get("wage_gap_scenario") in (None, scenario)]
    notes = dict(worker_scope_note="직업재활시설 최저임금적용제외 근로자, 다른사업체 제외 참고 범위.",
        worker_proxy_note="적용제외집단만의 시급·시간자료 부재로 시설전체평균 시급·시간을 대리 사용, 고용위축·변동 미반영.",
        worker_projection_note="2019~2023대상수와시급 각각CAGR, 월시간평균116·연12개월. 2025고시10030원 이후2024.7NABO 전망으로 계산, 최신2026실적 전망 아님.",
        worker_scenario_note=f"최저임금 차액의 {scenario} 보조가정. 실제법정확정률이 아니며 지원기준 확정 시 재검토.",
        worker_start_note="공포후6개월·준비기간을 고려한2026~2030 정답기간, 연계2200660 의결·시행을 가정.")
    return dict(bill_no="2200664", evidence_mode="development_review", cutoff_date="2026-10-10",
        route_key=PROFILE, support_derivation=PROFILE, payer="government", start_year=2026, years=5,
        disabled_worker_scope="vocational_facility_exempt_workers", wage_gap_scenario=scenario,
        worker_scenario_confirmed=True, linked_minimum_wage_bill_assumed_passed=True, **notes,
        selected_evidence_keys=keys, evidence_selection_reasons={k: "적용제외 대상·시급/시간 대리변수·역사적가격 및 지원률 확인" for k in keys},
        selected_method_keys=[method], method_selection_reasons={method: "사업주 최저임금 차액지원 시나리오"},
        method_confirmations={method: notes})


def run_regression():
    gold = dict(share30=(959, [169, 180, 191, 203, 215]), share50=(1598, [282, 300, 319, 338, 359]),
                share100=(3196, [565, 600, 637, 677, 717]))
    parts = []
    for scenario, (total_gold, annual_gold) in gold.items():
        p = worker_payload(scenario); result = estimate_routed_item(p)
        web = calculate_erce_web_item({**p, "bill_no": "SIMILAR_DISABLED_WORKER_WAGE", "evidence_mode": "holdout"})
        annual = list(result.annual_amounts_thousand)
        if annual != web["annualAmountsThousand"]:
            raise ValueError("개발회귀·웹재사용 불일치")
        total = sum(annual) / 100000
        parts.append(dict(scenario=scenario, payload=p, result=dataclasses.asdict(result), trace=web["derivationTrace"],
            web_status=web["status"], total_eok=total, gold_total_eok=total_gold,
            error_percent=abs(total-total_gold)/total_gold*100,
            annual_display_matches=sum(round(v/100000)==g for v,g in zip(annual,annual_gold))))
    return dict(bill_no="2200664", post_answer_regression=True, independent_evaluation=False, parts=parts,
        limitation="과거실적·공식2025시급·공개2024.7전망으로 재계산. 미래정답값을 입력하지 않음. 공개반올림전망과 상세차이는 유지.")


if __name__ == "__main__":
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
