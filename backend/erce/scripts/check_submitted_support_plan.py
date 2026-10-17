"""Post-answer component regression; monthly activity period remains unresolved."""
import dataclasses
import json
from backend.erce.submitted_support_plan import PROFILE, SLOTS
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def plan_payload(kind, replay=False):
    method = "2200482:submitted_elder_protection_plan"
    keys = [f"2200482:plan:{k}:reviewed" for k in SLOTS[kind] if k != "activity_months"]
    p = dict(bill_no="2200482", evidence_mode="development_review", route_key="direct_annual_amount",
        cutoff_date="2026-10-06", start_year=2025, years=5, support_derivation=PROFILE,
        plan_cost_item=kind, fiscal_scope="national_and_local_combined", payer="government",
        support_derivation_note="정답에 인용된 부처사업계획의 범위로 사후 계산",
        plan_applicability_note="중앙1·지역38개 보호기관, 81명 충원이라는 해당 계획만 반영; 유사기관 법정정원 아님",
        estimation_start_note="해당 정답의 2025~2029년 가정, 모든 법안에 다음해 시작 적용하지 않음",
        selected_evidence_keys=keys, selected_method_keys=[method],
        evidence_selection_reasons={k:"해당 사업계획 범위와 연도 검토 후 사후 준용" for k in keys},
        method_selection_reasons={method:"외부 제출계획이 인용된 경제적노인학대 대응사업"},
        method_confirmations={method:dict(plan_applicability_note="정답PDF3~5쪽 인용계획. 계획원본 별도확보 미완료",
            estimation_start_note="역사적 2025~2029 시나리오")})
    if replay:
        p["activity_period_basis"] = "historical_table_unresolved_monthly_unit"
    return p


def run_regression():
    items = {}
    for kind in SLOTS:
        p = plan_payload(kind, replay=kind=="project")
        items[kind] = dataclasses.asdict(estimate_routed_item(p))
    annual = [sum(r["annual_amounts_thousand"][i] for r in items.values()) for i in range(5)]
    total = sum(annual)
    synthetic = {**plan_payload("project"), "bill_no":"SYNTHETIC_ELDER_PLAN", "evidence_mode":"holdout"}
    missing = calculate_erce_web_item(synthetic)
    return dict(bill_no="2200482",post_answer_regression=True,independent_evaluation=False,
        items=items, annual_thousand=annual, total_thousand=total,gold_total_thousand=26277000,
        difference_percent=abs(total-26277000)/26277000*100,
        covered_items=5, gold_items=5, production_activity_status=missing["status"],
        production_missing_variables=missing.get("missingDerivationVariables"),
        production_whole_bill_total=None,
        limitation="정답표 재현이지 독립추계 성공 아님. 사업비 월단가/연간표 불일치 미해결; 지급기간 확인 전 전체금액 확정 금지")


if __name__ == "__main__":
    print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
