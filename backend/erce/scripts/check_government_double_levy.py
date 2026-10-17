"""Reviewed 100% floor / 200% zero-employment government levy regression."""
import dataclasses
import json
from backend.erce.government_employment_levy import PROFILE, DOUBLE_MODEL, government_double_levy_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def double_levy_payload(replay=True):
    method = "2207081:government_employer_double_levy"
    shared = [f"2200209:{k}:reviewed" for k in ("government_unfilled_by_band","government_non_civil_share","levy_payment_months")]
    keys = [r["evidence_key"] for r in government_double_levy_rows()] + shared
    notes = dict(government_payer_note="국가·지자체 고용주 납부지출만 계산. 공무원2023 미고용인원과 비공무원6.4% 역사적 참고 가정 유지",
        levy_band_note="개정기초100%·무고용200%, 중간구간은 현행비중과 기본구간의 차이에2.5가산. 2.5는 법정 상수가 아닌 정답의 구간분포 유지 가정",
        levy_overlap_note="기금수입과정부지출 상계금지, 민간·공공기관 지출 합산금지. 교육감·일시납감면 및 고용행태변화 미반영 시나리오",
        levy_timing_note="2025의무고용분은2026납부. 일반경로는가격년도1년시차. 원표의 현금연도 가격 재현은 자기회귀 한정")
    return dict(bill_no="2207081",evidence_mode="development_review",cutoff_date="2026-10-11",
        route_key=PROFILE,support_derivation=PROFILE,payer="government",start_year=2026,years=5,
        levy_band_model=DOUBLE_MODEL,levy_payer_scope="state_local_employer",government_levy_scenario_confirmed=True,
        fiscal_reporting="separate_revenue_and_expenditure",reviewed_table_year_offset=1 if replay else 0,
        levy_table_year_discrepancy_note="본문 전년도 고용분 납부 설명과 달리 표2026월최저임금은2025값에2026전망을 적용한 수준. 표연도재현만 자기회귀에서 허용",
        **notes,selected_evidence_keys=keys,evidence_selection_reasons={k:"기준년2025·5구간·정부미고용2023·비공무원비중과 과거전망 확인" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"기초100%·무고용200% 및 중간구간배분을 별도 모델로 선택"},
        method_confirmations={method:notes})


def run_regression(db_path=None):
    p = double_levy_payload()
    if db_path:
        p["variable_db_path"] = str(db_path)
    engine = estimate_routed_item(p)
    q = {**double_levy_payload(False),"bill_no":"SIMILAR_DOUBLE_GOVERNMENT_LEVY","evidence_mode":"holdout"}
    options = {"variable_db_path":db_path} if db_path else {}
    web = calculate_erce_web_item(q, **options)
    annual = list(engine.annual_amounts_thousand); total = sum(annual)/100000
    return dict(bill_no="2207081",post_answer_regression=True,independent_evaluation=False,
        replay_payload=p,replay_result=dataclasses.asdict(engine),replay_total_eok=total,gold_display_total_eok=6563,
        error_percent=abs(total-6563)/6563*100,
        annual_display_eok=[round(x/100000) for x in annual],
        annual_display_matches=sum(round(x/100000)==g for x,g in zip(annual,[1217,1263,1311,1360,1412])),
        statutory_previous_year_payload=q,statutory_web_result=web,statutory_total_eok=sum(web["annualAmountsThousand"])/100000,
        limitation="원표 가격연도·단가비중 반올림 및 전망 표기정밀도 차이를 숨기지 않음. 자기회귀와 일반 납부시차 결과를 분리; 최초 정확도 성과 아님")


if __name__ == "__main__":
    print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
