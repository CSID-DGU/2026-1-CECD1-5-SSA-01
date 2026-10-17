import dataclasses
import json
from backend.erce.mobile_identity_evidence import mobile_identity_rows, PROFILE, ROUTE
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def mobile_payload():
    method = "2205097:mobile_identity_lifecycle"
    keys = [r["evidence_key"] for r in mobile_identity_rows()]
    notes = dict(mobile_build_scope_note="2025장애인등록증 발급·접수등록·전자회수, 개발HW/SW·3586주민센터장비·감리 등6개구성 참고. 다른신분증 규모에자동적용하지않음.",
                 mobile_operation_scope_note="2023모바일공무원증 본인확인·콜센터·보안운영837백만원, 유지관리233백만원을 각각 준용.",
                 mobile_warranty_note="2025구축·2026운영시작과무상유지관리·2027유지관리시작. 운영과 유지관리는 다른비용.",
                 mobile_price_timing_note="2023단가를2024부터발생연도까지전망CPI 적용, 2025~2029정답기간. 구축비는2025예산안이므로중복물가가산없음.")
    return dict(bill_no="2205097", evidence_mode="development_review", cutoff_date="2026-10-10",
        route_key=ROUTE, support_derivation=PROFILE, payer="government", start_year=2025, years=5,
        mobile_plan_scope_confirmed=True, **notes, selected_evidence_keys=keys,
        evidence_selection_reasons={k: "발급플랫폼·과업·규모·가격년·무상보수 기간 검토한 참고 가정" for k in keys},
        selected_method_keys=[method], method_selection_reasons={method: "모바일등록증 구축운영생애주기 선택"},
        method_confirmations={method: notes})


def run_regression():
    p = mobile_payload(); result = estimate_routed_item(p)
    web = calculate_erce_web_item({**p, "bill_no": "SIMILAR_MOBILE_DISABILITY_ID", "evidence_mode": "holdout"})
    annual = list(result.annual_amounts_thousand)
    if annual != web["annualAmountsThousand"]:
        raise ValueError("개발회귀·웹재사용 계산 불일치")
    amount = sum(annual) / 100000
    # 공식 표는 구축·운영·유지관리 각 행을 백만원 표시한 뒤 연간 합계를 낸다.
    displayed = [sum(round(t[k] / 1000000) for k in ("build_won", "operation_won", "maintenance_won"))
                 for t in web["derivationTrace"]]
    return dict(bill_no="2205097", post_answer_regression=True, independent_evaluation=False,
        payload=p, result=dataclasses.asdict(result), web_result=web, total_eok=amount, gold_display_total_eok=112.37,
        error_percent=abs(amount - 112.37) / 112.37 * 100,
        displayed_annual_million=displayed,
        annual_display_matches=sum(a == g for a, g in zip(displayed, [6778, 893, 1165, 1189, 1212])),
        raw_annual_rounding_matches=sum(round(v / 1000) == g for v, g in zip(annual, [6778, 893, 1165, 1189, 1212])),
        limitation="정답 확인 후 사업계획·운영사례 준용 보강회귀. 새의안의 독립 자동성능아님.")


if __name__ == "__main__":
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
