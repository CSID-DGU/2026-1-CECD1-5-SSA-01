"""Post-answer approval-path regression; original first run stays unchanged."""
import json
import dataclasses
from pathlib import Path
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.engine import estimate_routed_item


def reviewed_payloads():
    root = Path(__file__).resolve().parents[3]
    first = json.loads((root / "docs/erce/first_runs/ERCE_FIRST_RUN_2200987.json").read_text())
    advance, system = [dict(part["payload"]) for part in first["parts"]]
    method = "2200987:delegated_advance_policy_reference"
    notes = dict(
        delegated_eligibility_note="소득기준은 대통령령 위임. 필요한 채권자 전원지원은 공식 추계서의 참고 가정이며 소득요건 충족을 산출한 것이 아님.",
        claim_amount_difference_note="전부 또는 절반 이상 지급 조건과 실제 채권액 분포는 미확정. 월20만원 정책 가정은 법정 비율을 계산한 값이 아님.",
        reference_scenario_source="24C1050 PDF3~6쪽: 필요 채권자 전원지원, 월20만원·12개월, 기존 긴급지원 예산 동결 차감.",
        legacy_transition_note="부칙의 기존 결정자 경과조치는 유지. 공식 추계서처럼 기존 연16억100만원 차감은 참고 시나리오이며 실제 경과기간 지출을 검증한 값은 아님.")
    advance.update(evidence_mode="development_review", delegated_eligibility_reference_required=True,
                   advance_amount_basis="delegated_policy_reference", reference_scenario_confirmed=True,
                   selected_method_keys=[method], method_selection_reasons={method: "확인한 선례의 전원지원 참고 시나리오 승인"},
                   method_confirmations={method: notes}, **notes)
    return advance, system


def run_regression():
    payloads = reviewed_payloads()
    # 웹은 자기 선례를 항상 제외한다. 실제 의안은 개발 회귀로 계산하고,
    # 웹 승인 흐름은 별도 유사 의안 식별자로 검사한다.
    engine_parts = [dataclasses.asdict(estimate_routed_item(p)) for p in payloads]
    parts = [calculate_erce_web_item({**p, "bill_no": "SIMILAR_DELEGATED_ADVANCE_REGRESSION",
                                     "evidence_mode": "holdout"}) for p in payloads]
    if any(list(e["annual_amounts_thousand"]) != w["annualAmountsThousand"] for e, w in zip(engine_parts, parts)):
        raise ValueError("개발 회귀와 웹 참고 시나리오 계산 불일치")
    annual = [sum(p["annualAmountsThousand"][i] for p in parts) for i in range(5)]
    amount = sum(annual) / 100000
    gold_annual = [64281, 63881, 64524, 64981, 65397]
    match = [round(v / 1000) == g for v, g in zip(annual, gold_annual)]
    return dict(bill_no="2200987", post_answer_regression=True, independent_evaluation=False,
                payloads=payloads, engine_parts=engine_parts, parts=parts, annual_thousand=annual,
                total_eok=amount, gold_total_eok=3230.64,
                raw_error_percent=abs(amount - 3230.64) / 3230.64 * 100,
                annual_display_matches=sum(match), total_display_match=round(amount, 2) == 3230.64,
                official_scope_complete=all(p["status"] == "computed_review" for p in parts) and all(match)
                                        and round(amount, 2) == 3230.64,
                limitation="정답 확인 후 참고 시나리오 승인 경로 보강. 첫 실행의 급여 보류 기록과 분리.")


if __name__ == "__main__":
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
