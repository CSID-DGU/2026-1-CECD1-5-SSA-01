import dataclasses
import json
from backend.erce.hospital_interpreter_increment import PROFILE, NOTES, interpreter_increment_rows
from backend.erce.engine import estimate_routed_item


def interpreter_payload(route="personnel_average"):
    component = "salary" if route == "personnel_average" else "initial_asset"
    method = f"2205811:interpreter_increment:{component}"
    keys = [r["evidence_key"] for r in interpreter_increment_rows() if route in r["allowed_routes"]]
    notes = dict(zip(NOTES, [
        "서울대병원 포함 국립대학병원18개, 2023.12현황 준용. 상급종합병원47개와 다름",
        "이미 배치된 병원도 추가1명씩, 총18명 증원. 기존지원병원 차감 없음",
        "2024 사회복지시설 종사자 연봉2568만원·집기674만원 준용. 임금전망과 CPI 각각 적용; 최신 공식보수표 아님",
        "공포후1년 준비기간을 고려2026~2030, 인건비 반복·자산2026년만",
    ]))
    return dict(bill_no="2205811", evidence_mode="development_review", cutoff_date="2026-10-11",
        route_key=route, support_derivation=PROFILE, payer="government", start_year=2026, years=5,
        interpreter_increment_confirmed=True, existing_interpreters_subtracted=False, **notes,
        selected_evidence_keys=keys, evidence_selection_reasons={k: notes["interpreter_price_note"] for k in keys},
        selected_method_keys=[method], method_selection_reasons={method: "기관별1명 추가 인건비와 첫해 집기 구분"},
        method_confirmations={method: notes})


def run_regression(db_path=None):
    parts = {}
    for route in ("personnel_average", "personnel_asset"):
        p = interpreter_payload(route)
        if db_path:
            p["variable_db_path"] = str(db_path)
        parts[route] = dataclasses.asdict(estimate_routed_item(p))
    annual = [sum(r["annual_amounts_thousand"][i] for r in parts.values()) for i in range(5)]
    total = sum(annual) / 100000
    return dict(bill_no="2205811", post_answer_regression=True, independent_evaluation=False,
        components=parts, annual_amounts_thousand=annual, total_eok=total, gold_total_eok=28.1,
        error_percent=abs(total - 28.1) / 28.1 * 100,
        annual_million_display=[round(x / 1000) for x in annual],
        annual_display_matches=sum(round(x / 1000) == g for x, g in zip(annual, [624,516,536,556,578])),
        limitation="정답 확인 후 보강한 자기회귀. 신규 의안에 대한 독립 정확도가 아님. 기관수·증원수·과거 임금전망은 확인할 가정")


if __name__ == "__main__":
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
