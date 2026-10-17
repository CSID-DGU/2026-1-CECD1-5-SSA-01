import json
from dataclasses import asdict
from backend.erce.prefunded_annual_survey_evidence import PROFILE,NOTES,prefunded_survey_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def survey_payload(lagged_reference=True):
    method = "2216008:prefunded_annual_survey_delta"
    notes = dict(zip(NOTES,[
        "유아사교육비 조사표에 어린이집특별활동 별도항목 포함. 같은연간전체조사 예산을 준용",
        "2026기편성8.7억원 차감.2027~2030정례조사 재원은 새로소요된다는 정답의 가정. 기존재원영구자동계속 가정안함",
        "공식예산8.7억원 유지. 확보된2025.9 전망과정답표를비교. 적용시점미기재를확정공식산식으로주장안함"
    ]))
    keys = [r["evidence_key"] for r in prefunded_survey_rows()]
    p = dict(bill_no="2216008",evidence_mode="development_review",cutoff_date="2026-10-13",
        route_key=PROFILE,support_derivation=PROFILE,payer="government",start_year=2026,years=5,
        prefunded_survey_confirmed=True,future_unfunded_survey_assumption_confirmed=True,
        **notes,explicit_inputs={},selected_evidence_keys=keys,
        evidence_selection_reasons={k:"유사과업·공식2026예산·기편성분 및 물가시점 검토" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"총조사비 아닌 기편성연도 차감 추가재정"},
        method_confirmations={method:notes},survey_price_rate_year_offset=0)
    if lagged_reference:
        p.update(estimate_purpose="reference_scenario",survey_price_rate_year_offset=-1,
            survey_lagged_cpi_assumption_confirmed=True,
            survey_cpi_timing_note="2027가격에2026전망1.9%,이후2027~2029전망2%적용시 정답표와대응. 표에서검토한시차가정이며 원NABO계산시점확인아님")
    return p


def run_regression(db_path=None):
    p = survey_payload()
    if db_path:
        p["variable_db_path"] = str(db_path)
    result = estimate_routed_item(p)
    options = {"variable_db_path":db_path} if db_path else {}
    web = calculate_erce_web_item({**survey_payload(),"bill_no":"SYNTHETIC_PREFUNDED_SURVEY"},**options)
    standard = calculate_erce_web_item({**survey_payload(False),"bill_no":"SYNTHETIC_CALENDAR_SURVEY"},**options)
    annual = list(result.annual_amounts_thousand)
    total = sum(annual)/100000
    return dict(bill_no="2216008",post_answer_regression=True,independent_evaluation=False,
        reference_scenario=True,payload=p,result=asdict(result),web_interface_result=web,
        calendar_cpi_missing_result=standard,total_eok=total,gold_display_total_eok=36.54,
        raw_error_percent=abs(total-36.54)/36.54*100,
        annual_million_display=[round(x/1000) for x in annual],
        annual_display_matches=sum(round(x/1000)==g for x,g in zip(annual,[0,887,904,922,941])),
        first_run_official_budget_preserved=True,
        limitation="단가와기편성연도차감은검증. 물가1년시차는조건부재현가정이며실제정답계산시점미확인.동일달력연도방식은2030전망미확보로추가입력필요")


if __name__ == "__main__":
    print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
