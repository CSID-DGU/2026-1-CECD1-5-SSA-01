import dataclasses
import json
from backend.erce.medical_communication_evidence import medical_communication_rows, PROFILE, ROUTE
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def communication_payload(basis="reviewed_monthly_replay"):
    method = f"2203688:communication:{basis}"
    keys = [r["evidence_key"] for r in medical_communication_rows()
            if r.get("medical_unit_basis") is None or r["medical_unit_basis"] == basis]
    notes = dict(communication_scope_note="상급종합병원 지원, 수어통역사1명·코디네이터2명 패키지. 일반병원 노력의무와 별도.",
                 communication_overlap_note="2024상급47개 중 기존 지역센터지원10개 제외→추가37개 동결 참고 가정. 새의안은 지정·겹침 갱신 필요.",
                 communication_unit_note="공식서울시 연차180백만원은 연패키지. 정답은45.8·42.6백만원을 월단가로 표시해 상충, 모드별로 분리.",
                 communication_timing_note="공포후1년·준비기간 고려2026~2030. 연간모드는 정상운영2차년도 패키지 동결 시나리오.")
    return dict(bill_no="2203688", evidence_mode="development_review", cutoff_date="2026-10-10",
        route_key=ROUTE, support_derivation=PROFILE, payer="government", start_year=2026, years=5,
        medical_unit_basis=basis, communication_scenario_confirmed=True, fiscal_scope="national_and_local_combined",
        communication_package_phase="full_year_following_year", communication_price_policy="freeze_reference",
        disputed_monthly_replay_confirmed=True,
        communication_source_discrepancy_note="정답월단가표기를재현하되일반단가로사용하지않음. 공식서울시연차패키지와단위/규모가상충. 2025예산기준액에2025임금률부터적용하는정답경로도명시.",
        **notes, selected_evidence_keys=keys,
        evidence_selection_reasons={k: "동일3명 의료접근 지원과업, 단위·기존지원·공공부담 범위검토" for k in keys},
        selected_method_keys=[method], method_selection_reasons={method: "공식연간패키지와 월단가재현을 분리해 선택"},
        method_confirmations={method: notes})


def run_regression():
    p = communication_payload(); replay = estimate_routed_item(p)
    q = communication_payload("official_annual_package")
    official = calculate_erce_web_item({**q, "bill_no": "SIMILAR_HOSPITAL_ANNUAL_PACKAGE", "evidence_mode": "holdout"})
    annual = list(replay.annual_amounts_thousand); amount = sum(annual) / 100000
    return dict(bill_no="2203688", post_answer_regression=True, independent_evaluation=False,
        replay_payload=p, replay_result=dataclasses.asdict(replay), replay_total_eok=amount,
        gold_detail_total_eok=4486.56, replay_error_percent=abs(amount - 4486.56) / 4486.56 * 100,
        annual_summary_matches=sum(round(v / 100000) == g for v, g in zip(annual, [846, 871, 896, 923, 951])),
        official_annual_payload=q, official_annual_web_result=official,
        official_annual_total_eok=sum(official["annualAmountsThousand"]) / 100000,
        limitation="정답월단가 금액은 자기회귀만. 일반재사용은 공식연간1.8억원 패키지, 추가원예산 세부단위는 미확정. 둘을 동일정답이라고표시하지않음.")


if __name__ == "__main__":
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
