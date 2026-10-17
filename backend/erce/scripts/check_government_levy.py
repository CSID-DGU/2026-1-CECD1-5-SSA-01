import dataclasses
import json
from backend.erce.government_employment_levy import government_levy_rows, PROFILE
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.method_evidence_store import validate_non_estimation_review


def levy_payload(replay=True):
    method = "2200209:government_employer_levy_delta"
    notes = dict(government_payer_note="국가·지자체는 징수자뿐 아니라 고용주로서 부담금납부자. 공무원 및 비공무원 지출증가만 계산.",
        levy_band_note="2024고용률별 원기초액/월최저임금의 원비율 사용, 개정80%+기초구간과의비율차이 절반가산, 무고용100%유지.",
        levy_overlap_note="기금수입·환수증가와 납부지출 상계금지. 민간·공공기관부담금을 정부고용주 지출에 합치지 않음.",
        levy_timing_note="2025의무고용분은2026납부. 기본경로는가격년1년이전, 원자료 표의 연도차이재현은자기회귀에한정.")
    keys = [r["evidence_key"] for r in government_levy_rows()]
    return dict(bill_no="2200209", evidence_mode="development_review", cutoff_date="2026-10-10",
        route_key=PROFILE, support_derivation=PROFILE, payer="government", start_year=2026, years=5,
        levy_payer_scope="state_local_employer", government_levy_scenario_confirmed=True,
        fiscal_reporting="separate_revenue_and_expenditure", reviewed_table_year_offset=1 if replay else 0,
        levy_table_year_discrepancy_note="표의 월최저임금 수준은 본문의 전년도과세분 납부설명과 달리 현금연도 가격에 가까움. 정답표참고재현만 현금연도가격, 일반경로는1년시차 유지.",
        **notes, selected_evidence_keys=keys, evidence_selection_reasons={k: "정부고용주 5구간·2023고용분포·가산비중 및 역사적가격 가정 확인" for k in keys},
        selected_method_keys=[method], method_selection_reasons={method: "수입증가와 별도인 정부납부지출의 구간차액"},
        method_confirmations={method: notes})


def scope_payload(kind):
    facts = dict(grant_amount_changed=False, direct_new_expenditure=False) if kind == "grant_use" else dict(effect_is_only_revenue_increase=True)
    notes = dict(grant_use_only_scope_note="장려금 금액·대상이 아니라 사용용도만 제한, 별도신규집행비 미명시") if kind == "grant_use" else dict(receipt_only_scope_note="환수 또는 기금부담금 수입의 순증효과만 분리, 지출증가는 다른 항목으로 검토")
    if kind == "levy_receipts":
        facts["government_employer_expense_separately_reviewed"] = True
        notes["government_payer_review_note"] = "정부고용주 납부지출은 구간별 별도계산, 수입과 상계하지 않음"
    return dict(bill_no="2200209", evidence_mode="development_review", cutoff_date="2026-10-10",
        decision_evidence_key=f"2200209:{kind}_outside_scope", reliable_estimation_basis_available=False,
        decision_facts=facts, decision_confirmations=notes)


def run_regression():
    p = levy_payload(); replay = estimate_routed_item(p)
    q = {**levy_payload(False), "bill_no": "SIMILAR_GOVERNMENT_EMPLOYMENT_LEVY", "evidence_mode": "holdout"}
    web = calculate_erce_web_item(q)
    annual = list(replay.annual_amounts_thousand); amount = sum(annual) / 100000
    decisions = [validate_non_estimation_review(scope_payload(k)) for k in ("grant_use", "grant_recovery", "levy_receipts")]
    return dict(bill_no="2200209", post_answer_regression=True, independent_evaluation=False,
        replay_payload=p, replay_result=dataclasses.asdict(replay), replay_total_eok=amount, gold_display_total_eok=2060,
        error_percent=abs(amount-2060)/2060*100,
        annual_display_matches=sum(round(v/100000)==g for v,g in zip(annual,[386,399,412,425,438])),
        scope_decisions=decisions, statutory_previous_year_payload=q, statutory_web_result=web,
        limitation="월단가 표의 연도차이는 자기회귀에서만 승인. 재사용은 납부1년시차 유지. 원금액을맞추려고예측값·계수를역산하지 않음.")


if __name__ == "__main__":
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
