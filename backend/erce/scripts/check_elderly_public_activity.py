import dataclasses
import json
from backend.erce.elderly_public_activity_evidence import elderly_public_activity_rows, PROFILE, ROUTE
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def activity_payload():
    method = "2203550:public_activity_minimum_wage_reference"
    notes = dict(unmatched_source_reference_note="첨부24C2515 회답2024-08-08이발의2024-09-03보다빠르고표지번호공란. 동일 조문·시행일 참고시나리오로만 승인.",
                 public_activity_scope_note="공익활동형만 최저시급 적용 참고 가정. 사회서비스·민간형 이미최저임금 이상으로 제외.",
                 activity_projection_note="참여자2019~2023·최저시급2021~2025 CAGR, 월29만원·30시간·11개월 동결, 부대경비 양쪽 동일.",
                 activity_timing_note="원문2024-11-01시행. 첫2024년2개월·2025이후11개월, 2024~2028참고기간.")
    keys = [r["evidence_key"] for r in elderly_public_activity_rows()]
    return dict(bill_no="2203550", evidence_mode="development_review", cutoff_date="2026-10-10",
        route_key=ROUTE, support_derivation=PROFILE, payer="government", start_year=2024, years=5,
        elderly_job_type="public_activity", law_effective_date="2024-11-01", use_unmatched_source_as_reference=True,
        **notes, selected_evidence_keys=keys, evidence_selection_reasons={k: "버전불일치를 명시한 동일 공익활동형 과업 참고" for k in keys},
        selected_method_keys=[method], method_selection_reasons={method: "확정대상정답이아닌 공익활동형 임금증분 참고"},
        method_confirmations={method: notes})


def run_regression():
    p = activity_payload(); result = estimate_routed_item(p)
    web = calculate_erce_web_item({**p, "bill_no": "SIMILAR_PUBLIC_ACTIVITY_REFERENCE", "evidence_mode": "holdout"})
    annual = list(result.annual_amounts_thousand)
    if annual != web["annualAmountsThousand"]:
        raise ValueError("개발회귀·웹참고경로 불일치")
    total = sum(annual) / 100000
    return dict(bill_no="2203550", post_answer_regression=True, independent_evaluation=False,
        attached_reference_identity_verified=False, payload=p, result=dataclasses.asdict(result), web_result=web,
        total_eok=total, reference_display_total_eok=9574, reference_error_percent=abs(total - 9574) / 9574 * 100,
        annual_display_matches=sum(round(v / 100000) == g for v, g in zip(annual, [79, 861, 1787, 2834, 4012])),
        limitation="버전불일치 첨부자료 참고시나리오 재현. 확정대상 정답 정확도 및 독립 성과 아님")


if __name__ == "__main__":
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
