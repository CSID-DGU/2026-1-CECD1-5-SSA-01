import dataclasses
import json
from backend.erce.foreign_childcare_evidence import foreign_childcare_rows, PROFILE
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.method_evidence_store import validate_non_estimation_review


def fee_payload(basis="reviewed_target"):
    rows = foreign_childcare_rows()
    method = f"2201907:foreign_parent_fee:{basis}"
    notes = dict(foreign_eligibility_note="2024정답처럼 합법 장기체류 외국국적 아동. 기존지원 재외국민·기관보육료·누리·교사인건비 제외. 지방 기존 자체지원 미차감 참고 가정.",
                 foreign_use_proxy_note="외국아동 이용률 부재로2023.12 전체 반연령 이용률 준용. 이용증가 미반영. 자기정답 전망수는 검증 전용, 새의안에 못 씀.",
                 parent_fee_price_note="2024부모보육료54·47.5·39.4만원, 2024.3NABO CPI를2025부터 적용, 12개월·국비69.4%동결.",
                 foreign_estimation_start_note="공포후6개월·심사 및 준비기간을 고려한 정답2026~2030 참고 시나리오.")
    keys = [r["evidence_key"] for r in rows if (r["variable_key"] not in
        {"child_population_base_by_age", "child_population_future_by_age"} if basis == "reviewed_target"
        else r["reuse_policy"] != "target_only")]
    return dict(bill_no="2201907", evidence_mode="development_review", cutoff_date="2026-10-10",
        route_key="direct_annual_amount", support_derivation=PROFILE, payer="government", start_year=2026, years=5,
        parent_fee_base_year=2024, foreign_population_base_year=2023, foreign_parent_fee_basis=basis,
        foreign_scope_confirmed=True, **notes, selected_evidence_keys=keys,
        evidence_selection_reasons={k: "같은 반연령·기준년도·공공 지원과업의 참고 근거 검토" for k in keys},
        selected_method_keys=[method], method_selection_reasons={method: "외국아동 부모보육료 순증, 양육수당 및 기존지원 중복 제외"},
        method_confirmations={method: notes})


def non_estimation_payload(kind):
    home = kind == "home"
    return dict(bill_no="2201907", evidence_mode="development_review", cutoff_date="2026-10-10",
        decision_evidence_key="2201907:foreign_home_allowance_not_estimated" if home else "2201907:childcare_principle_not_estimated",
        reliable_estimation_basis_available=False,
        decision_facts=dict(institution_nonuse_basis_available=False) if home else dict(concrete_payment_obligation=False),
        decision_confirmations=dict(foreign_home_scope_note="2024정답 양육수당 대상 연령·기관미이용요건 검토, 부모급여와 구분",
                                    foreign_nonuse_review_note="당시 외국아동 유치원·어린이집·아이돌봄 미이용 확률 예측근거 부족") if home else
                               dict(principle_only_scope_note="제3조 차별금지 이념만 분리, 제34조의8 구체지원은 별도 계산"))


def run_regression():
    p = fee_payload(); engine = estimate_routed_item(p)
    annual = list(engine.annual_amounts_thousand); total = sum(annual) / 100000
    decisions = [validate_non_estimation_review(non_estimation_payload(k)) for k in ("home", "principle")]
    generic = calculate_erce_web_item({**fee_payload("stock_share"), "bill_no": "NEW_FOREIGN_CHILDCARE", "evidence_mode": "holdout"})
    return dict(bill_no="2201907", post_answer_regression=True, independent_evaluation=False,
        target_only_payload=p, result=dataclasses.asdict(engine), annual_eok=[v / 100000 for v in annual],
        total_eok=total, gold_detail_total_eok=3827.84, detail_error_percent=abs(total - 3827.84) / 3827.84 * 100,
        annual_summary_matches=sum(round(v / 100000) == g for v, g in zip(annual, [745, 732, 741, 779, 830])),
        decisions=decisions, reusable_web_status=generic["status"],
        reusable_missing=generic.get("missingDerivationVariables"),
        limitation="금액은 대상 정답 전망량을 쓴 자기회귀. 재사용 구조는 각세 외국인 기준실적 부재로 입력 필요. 공개2023연보는0~4세 묶음이라 임의 분해하지 않음.")


if __name__ == "__main__":
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
