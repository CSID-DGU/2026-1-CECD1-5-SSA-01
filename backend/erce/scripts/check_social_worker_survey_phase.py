import dataclasses
import json
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.scripts.check_social_worker_rights_survey import rights_payload


def phase_payloads():
    rights = rights_payload()
    rights.update(bill_no="2205165", evidence_mode="development_review", start_year=2025)
    rights["explicit_inputs"]["recurrence_interval_years"] = dict(value=2, unit="year", source_ref="2205165 원문PDF3쪽3년→2년")
    rights["method_confirmations"]["2203955:separate_rights_survey"]["recurrence_phase_note"] = "공포후3개월·시행후1년내 조사와 심사기간을 고려해2025첫조사·2025~2029시나리오 승인"
    wages = []
    for cycle in (3, 2):
        keys = ["2205985:social_worker_wage_survey:2023", "2205985:wage_survey_price_freeze"]
        p = dict(bill_no="2205165", evidence_mode="development_review", cutoff_date="2026-10-10",
                 route_key="research_survey", payer="government", start_year=2025, years=5,
                 research_service_function="social_worker_wage_survey", research_cost_scope="research_contract_only",
                 selected_evidence_keys=keys, evidence_selection_reasons={key: "사회복지사 보수·지급실태 과업단가와 동결 가정" for key in keys},
                 explicit_inputs={"recurrence_interval_years": dict(value=cycle, unit="year", source_ref="2205165 원문PDF3·5쪽 현행3년·개정2년")})
        if cycle == 3:
            key = "2205165:wage_survey:last_occurrence_year"
            method = "2205165:wage_survey_historical_phase"
            p["selected_evidence_keys"].append(key)
            p["evidence_selection_reasons"][key] = "2023실시 이력에 원문 현행3년 주기를 적용"
            p.update(selected_method_keys=[method], method_selection_reasons={method: "기존 조사 일정을 개정 첫조사와 분리"},
                     method_confirmations={method: dict(historical_phase_note="2023조사 이력→현행2026·2029실시",
                                                        amended_start_note="개정2025첫조사·2년주기 후보 승인, 기존 일정을2025로 당기지 않음")})
        wages.append(p)
    return [rights, *wages]


def run_regression():
    payloads = phase_payloads()
    engines = [dataclasses.asdict(estimate_routed_item(p)) for p in payloads]
    web = [calculate_erce_web_item({**p, "bill_no": "SIMILAR_SURVEY_CYCLE_CHANGE", "evidence_mode": "holdout"}) for p in payloads]
    if any(list(e["annual_amounts_thousand"]) != w["annualAmountsThousand"] for e, w in zip(engines, web)):
        raise ValueError("개발 회귀와 웹 계산 불일치")
    violence, old, new = [w["annualAmountsThousand"] for w in web]
    annual = [v + n - o for v, n, o in zip(violence, new, old)]
    gold = [228000, -178000, 228000, 0, 50000]
    return dict(bill_no="2205165", post_answer_regression=True, independent_evaluation=False,
                payloads=payloads, engine_parts=engines, web_parts=web, start_year=2025,
                annual_thousand=annual, total_won=sum(annual) * 1000, gold_total_won=328000000,
                error_percent=abs(sum(annual) * 1000 - 328000000) / 328000000 * 100,
                annual_matches=sum(a == g for a, g in zip(annual, gold)),
                official_scope_complete=annual == gold and all(w["status"] == "computed_review" for w in web))


if __name__ == "__main__":
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
