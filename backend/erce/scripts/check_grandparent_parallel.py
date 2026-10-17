import dataclasses
import json
from backend.erce.scripts.check_grandparent_care import care_payload
from backend.erce.grandparent_care_evidence import PARALLEL
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.method_evidence_store import validate_non_estimation_review


def parallel_payload():
    p = care_payload()
    keys = ["official:kosis:age0_5:2025-2029:grandparent_parallel"] + [f"2200629:{key}:parallel" for key in
        ("grandparent_care_shares", "supported_care_hours", "public_care_hour_rate", "foregone_allowance_by_age",
         "registration_take_up", "care_payment_months")]
    method = "2200629:grandparent_allowance_parallel"
    notes = dict(registration_scope_note="0~5세 낮시간 조부모양육 아동 단위, 전원 교육이수·연초등록·연중유지 참고 가정.",
                 allowance_overlap_note="원문 제34조의2제2항은 양육수당 병행 허용. 기존수당 변화 없음으로 차감0, 국비·지방비 총액.",
                 estimation_start_note="공포즉시 시행이지만 심사·공포 준비기간을 고려한2025~2029 정답 시나리오.",
                 care_population_proxy_note="시설 미이용·등록 실제수 부족. 정답처럼2021 낮시간 친조부모+외조부모 양육비율을 각세인구에 적용하는 대리추계. 정확한 법정 모집단 집계가 아니며 시간제 서비스 중복이용 감액은 불확실해 미반영.")
    p.update(bill_no="2200629", evidence_mode="development_review", cutoff_date="2026-10-10",
             support_derivation=PARALLEL, start_year=2025, grandparent_allowance_mode="allowance_parallel",
             care_proxy_confirmed=True, **notes, selected_evidence_keys=keys,
             evidence_selection_reasons={key: "2021돌봄비율·당시80시간 지원, 수당 병행 및 대리모집단의 조건부 적용 승인" for key in keys},
             selected_method_keys=[method], method_selection_reasons={method: "시간한도·수당병행 구조를 별도 선택"},
             method_confirmations={method: notes})
    return p


def recovery_review():
    return dict(bill_no="2200629", evidence_mode="development_review", cutoff_date="2026-10-10",
                decision_evidence_key="2200629:care_recovery_penalty_not_estimated", reliable_estimation_basis_available=False,
                decision_facts=dict(new_program_implemented=False, violation_forecast_available=False,
                                    recovery_forecast_available=False, fine_forecast_available=False),
                decision_confirmations=dict(care_violation_scope_note="2024정답의 신규 손자녀돌보미 부정수급·벌칙 규정, 위반인원 실적 부재 확인",
                                            recovery_forecast_note="당시 환수 규모 예측 어려움, 급여와 상계하지 않음",
                                            fine_forecast_note="당시 위반·벌금 규모 예측 어려움, 수입효과0원으로 표시하지 않음"))


def run_regression():
    p = parallel_payload()
    engine = estimate_routed_item(p)
    web = calculate_erce_web_item({**p, "bill_no": "SIMILAR_GRANDPARENT_ALLOWANCE_PARALLEL", "evidence_mode": "holdout"})
    annual = list(engine.annual_amounts_thousand)
    if annual != web["annualAmountsThousand"]:
        raise ValueError("개발 회귀와 웹 계산 불일치")
    displayed = [round(v / 100000) for v in annual]
    gold = [2157, 2060, 2012, 1992, 2002]
    amount = sum(annual) / 100000
    review = recovery_review()
    decision = validate_non_estimation_review(review)
    return dict(bill_no="2200629", post_answer_regression=True, independent_evaluation=False,
                payload=p, result=dataclasses.asdict(engine), web_result=web,
                annual_eok=[v / 100000 for v in annual], displayed_annual_eok=displayed,
                raw_total_eok=amount, gold_display_total_eok=10223,
                raw_error_percent=abs(amount - 10223) / 10223 * 100,
                annual_matches=sum(a == g for a, g in zip(displayed, gold)),
                sum_displayed_annual_eok=sum(displayed), recovery_review_payload=review, recovery_decision=decision,
                official_scope_complete=displayed == gold and sum(displayed) == 10223 and decision["decision"] == "not_estimated",
                limitation="연간 억원표시와 그 합계로 정답표를 비교하며 계산 원값을 조정하지 않음. 정답 확인 후 참고 시나리오 보강 회귀.")


if __name__ == "__main__":
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
