"""Post-answer regression; retain the unchanged pre-answer first run."""
import dataclasses
import json
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def treatment_plan_payload():
    method = "2207435:separate_treatment_basic_plan"
    keys = ["2207435:treatment_plan:2022_unit_cost", "2207435:treatment_plan:price_freeze"]
    notes = dict(separate_plan_scope_note="전국 사회복지사 처우개선 방향·보수·근로환경·재원규모·조달방안의 별도 연구용역. 기존 보수실태조사에는 근로여건도 포함되어 기존 조사비를 가산하지 않음",
        price_freeze_note="2022 처우개선 지원방안 연구7,950만원을 약8,000만원으로 준용, 추계기간 동결 확인. 최신 공식요금 아님",
        recurrence_phase_note="원문3년주기, 기존2023조사 이후2026조사에 맞춰 첫기본계획 수립 가정. 2026·2029, 확정 공포일 아님")
    return dict(bill_no="2207435", evidence_mode="development_review", cutoff_date="2026-10-11",
        route_key="research_plan", payer="government", start_year=2026, years=5,
        research_service_function="social_worker_treatment_basic_plan", research_cost_scope="research_contract_only",
        implementation_model="separate_national_treatment_plan",
        explicit_inputs={"recurrence_interval_years": dict(value=3, unit="year", source_ref="2207435 원문PDF3쪽 제3조의2제1항")},
        selected_evidence_keys=keys, evidence_selection_reasons={k: notes["separate_plan_scope_note"] for k in keys},
        selected_method_keys=[method], method_selection_reasons={method: "동일 직종 처우개선의 별도 기본계획 정책연구 과업"},
        method_confirmations={method: notes})


def run_regression(db_path=None):
    p = treatment_plan_payload()
    if db_path:
        p["variable_db_path"] = str(db_path)
    engine = estimate_routed_item(p)
    db_options = {"variable_db_path": db_path} if db_path else {}
    web = calculate_erce_web_item({**p, "bill_no": "SIMILAR_TREATMENT_PLAN", "evidence_mode": "holdout"}, **db_options)
    annual = list(engine.annual_amounts_thousand)
    total = sum(annual) / 100000
    return dict(bill_no="2207435", post_answer_regression=True, independent_evaluation=False,
        payload=p, engine_result=dataclasses.asdict(engine), reusable_web_result=web,
        annual_amounts_thousand=annual, total_eok=total, gold_total_eok=1.6,
        error_percent=abs(total-1.6)/1.6*100,
        annual_matches=sum(a==g for a,g in zip(annual,[80000,0,0,80000,0])),
        regression_scope_complete=annual==[80000,0,0,80000,0] and annual==web.get("annualAmountsThousand"),
        limitation="정답 확인 후 단가를 저장한 회귀시험. 원문 새 의안의 독립 정확도가 아님; 가상 유사 의안은 재사용 연결 점검")


if __name__ == "__main__":
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
