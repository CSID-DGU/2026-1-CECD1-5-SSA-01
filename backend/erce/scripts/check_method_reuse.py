"""2217718 plan-only integration regression; manual AI, no target answer/API.

The optional amount is a deliberately confirmed historical-price scenario,
NOT an independently validated cost or a whole-bill estimate.
"""
import argparse
import base64
import json
from pathlib import Path

import fitz

from backend.erce.ai_pdf_analysis import analyze_erce_pdf
from backend.erce.draft_report import generate_draft
from backend.erce.method_evidence_store import find_method_candidates
from backend.erce.variable_evidence_store import DEFAULT_VARIABLE_DB
from backend.erce.web_bridge import calculate_erce_web_item


def run_plan_reuse(db_path=DEFAULT_VARIABLE_DB):
    path = Path("backend/generated/assembly_22_pdfs/by_bill/2217718/bill_text.pdf")
    with fitz.open(path) as pdf:
        text = pdf[6].get_text()
        quote = text[text.index("제5조"):text.index("②")].strip()
    draft = dict(bill_name="인공지능 데이터센터 구축 및 운영 활성화에 관한 법률안",
        document_type="제정", bill_no="2217718", propose_date="2026-03-24", articles=[
            dict(article_ref="제5조제1항", change_summary="5년마다 기본계획 수립 의무 신설",
                cost_trigger=True, estimation_decision="estimate_now",
                decision_reason="기본계획 수립의 비용 후보. 외부 용역 실시 여부는 가정으로 확인 필요",
                route_key="research_plan", route_reason="매년 시행계획과 구별해 5년 주기 기본계획만 계산",
                source_quote=quote, source_page=7, variables=[
                    dict(key="recurrence_interval_years", value_json="5", unit="year",
                         source_quote="5년마다", source_page=7)])])
    analysis = analyze_erce_pdf(path.name, base64.b64encode(path.read_bytes()).decode(), ai_draft=draft)
    item = analysis["erce"]["items"][0]
    methods = find_method_candidates(query=quote, cutoff_date="2026-03-24",
                                     target_bill_no="2217718", db_path=db_path)
    base = dict(route_key="research_plan", bill_no="2217718", cutoff_date="2026-03-24",
                years=5, explicit_inputs=item["explicitInputs"], method_query=quote)
    pending = calculate_erce_web_item(base, variable_db_path=db_path)
    method_key = "2200039:periodic_plan_research"
    unit_key = "2200039:mois_plan_research_unit_cost:2021-2023"
    # This confirmation is a development scenario, not an assertion that an
    # AI data-center plan has the same workload as the earlier MOIS plan.
    scenario = {**base, "payer": "government", "start_year": 2027,
        "selected_method_keys": [method_key],
        "method_selection_reasons": {method_key:
            "5년 주기 기본계획의 수립연도에 연구용역을 계상하는 방법을 재사용. 부처·분야가 달라 실제 과업 검증은 남음"},
        "method_confirmations": {method_key: {"external_research_scope":
            "개발 연결 검증용으로 외부 용역 1회를 가정. 법안이 외부 용역을 명시한 것으로 해석하지 않음"}},
        "selected_evidence_keys": [unit_key],
        "evidence_selection_reasons": {unit_key:
            "연결 검증용 과거 가격 동결 시나리오만 채택. AI 데이터센터 과업·규모와 일치한다고 검증된 단가가 아님"}}
    calculation = calculate_erce_web_item(scenario, variable_db_path=db_path)
    # Draft uses the default DB in production, just like the existing HTTP API.
    if Path(db_path) != DEFAULT_VARIABLE_DB:
        report = None
    else:
        report = generate_draft(dict(bill_name=draft["bill_name"], start_year=2027, years=5,
            items=[{**scenario, "name": "기본계획 연구용역(가정 시나리오)", "trigger_ref": "제5조제1항"}],
            exclusions=["제5조 기본계획만 연결 검증. 나머지 조문은 이번 실행에서 분석·추계하지 않음",
                        "2027년 첫 수립 및 2023년 기준 과거 용역단가 동결은 개발 시나리오. 현재 적정가격 검증 필요"]))
    return dict(independent_evaluation=False, target_answer_read=False, paid_api_calls=0,
        scope="2217718 기본계획 항목만의 연결 회귀검증", ai_draft=draft,
        quote_verified=analysis["articles"][0]["quote_verified"],
        method_candidates=[row["method_key"] for row in methods],
        initial_result=pending, confirmed_development_scenario=scenario,
        scenario_calculation=calculation, draft=report,
        limitation="산식·근거 검색·웹 계산·초안 연결만 검증. 실제 적정단가·시작연도·총비용 정확도는 검증하지 않음")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_VARIABLE_DB)
    parser.add_argument("--output", type=Path,
        default=Path("docs/erce/cases/ERCE_METHOD_REUSE_2217718.json"))
    args = parser.parse_args()
    result = run_plan_reuse(args.db)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(dict(output=str(args.output), quote_verified=result["quote_verified"],
        method_candidates=result["method_candidates"],
        initial_missing=result["initial_result"].get("missingVariables"),
        scenario_annual_thousand=result["scenario_calculation"]["annualAmountsThousand"],
        draft_status=(result["draft"] or {}).get("status"), independent_evaluation=False), ensure_ascii=False))


if __name__ == "__main__":
    main()
