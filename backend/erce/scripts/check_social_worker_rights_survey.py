import dataclasses
import json
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def rights_payload():
    method = "2203955:separate_rights_survey"
    keys = ["2203955:rights_survey:2021_unit_cost", "2203955:rights_survey:price_freeze"]
    notes = dict(separate_survey_scope_note="기존 보수조사와 성격이 다른 인권·폭력경험 조사. 중앙·지방 협력의 전국1회 별도 연구용역 가정을 승인, 지자체 수 중복 곱셈 없음.",
                 price_freeze_note="2021 사회복지사 폭력경험 종합실태조사 연구용역5천만원 준용, 2026~2030 동결 가정.",
                 recurrence_phase_note="원문3년 주기 유지. 공포후6개월 및 심사기간을 고려한 정답2026~2030 첫해 실시 시나리오로2026·2029 조사.")
    return dict(bill_no="2203955", evidence_mode="development_review", cutoff_date="2026-10-10",
                route_key="research_survey", payer="government", start_year=2026, years=5,
                research_service_function="social_worker_rights_violence_survey", research_cost_scope="research_contract_only",
                implementation_model="central_local_cooperative_separate_survey",
                explicit_inputs={"recurrence_interval_years": dict(value=3, unit="year", source_ref="2203955 원문PDF1·5쪽 기존3년주기")},
                selected_evidence_keys=keys, evidence_selection_reasons={key: "동일 인권·폭력경험 과업과 전국협력 수행범위를 검토한 참고 후보" for key in keys},
                selected_method_keys=[method], method_selection_reasons={method: "보수조사 전체비 아닌 별도 인권조사 과업 준용"},
                method_confirmations={method: notes})


def run_regression():
    payload = rights_payload()
    engine = estimate_routed_item(payload)
    web = calculate_erce_web_item({**payload, "bill_no": "SIMILAR_SOCIAL_WORKER_RIGHTS_SURVEY", "evidence_mode": "holdout"})
    annual = list(engine.annual_amounts_thousand)
    if annual != web["annualAmountsThousand"]:
        raise ValueError("개발 회귀와 웹 계산 불일치")
    amount = sum(annual) * 1000
    return dict(bill_no="2203955", post_answer_regression=True, independent_evaluation=False,
                payload=payload, result=dataclasses.asdict(engine), web_result=web,
                total_won=amount, gold_total_won=100000000, error_percent=abs(amount - 100000000) / 100000000 * 100,
                annual_matches=sum(a == g for a, g in zip(annual, [50000, 0, 0, 50000, 0])),
                official_scope_complete=annual == [50000, 0, 0, 50000, 0] and web["status"] == "computed_review")


if __name__ == "__main__":
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
