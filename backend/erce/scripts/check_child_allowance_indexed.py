"""Post-answer regression for reviewed indexed-benefit scenario, not first run."""
import json
from dataclasses import asdict
from pathlib import Path

from backend.erce.child_allowance_indexed_evidence import ALIAS_KEYS, NEW_KEYS
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.engine import estimate_routed_item


def reviewed_payload():
    keys = list(ALIAS_KEYS + NEW_KEYS)
    return dict(bill_no="2204028", route_key="transfer_population_amount_delta",
        evidence_mode="development_review", cutoff_date="2026-10-04", start_year=2025, years=5,
        support_derivation="child_allowance_indexed_population",
        support_derivation_note="24C3796의2024년 월10만원 기준·당해연도 물가 누적 적용 선례를 확인한 사후 회귀검증",
        child_allowance_scenario="all_under19_indexed", child_population_geography="전국",
        child_index_base_year=2024, parent_benefit_unchanged=True,
        child_allowance_scope_note="0~18세 개정 기본급여−0~7세 현행 기본급여. 부모급여는 유지,2세미만 제외 안 함",
        estimation_start_note="원문2025-01-01시행·월지급에 따라2025~2029년 완전연도12개월",
        explicit_inputs={
            "existing_benefit_per_recipient":dict(value=100000,unit="KRW/person/month",source_ref="원문5쪽 현행 월10만원"),
            "payments_per_year":dict(value=12,unit="month/year",source_ref="2025-01-01 시행·매월지급 완전연도 시나리오")},
        selected_evidence_keys=keys, evidence_selection_reasons={key:
            "전국·같은 연령·2025~2029년·같은 통계 버전 확인; 물가는 과거전망, 지급률은 동결 가정. 자기 정답 신규근거는 사후 회귀검증에서만 사용" for key in keys})


def run_regression():
    p = reviewed_payload()
    estimate = estimate_routed_item(p)
    r = dict(status="computed_review", formulaKey=estimate.formula_key,
        annualAmountsThousand=list(estimate.annual_amounts_thousand),
        resolvedVariables={key:asdict(value) for key,value in estimate.resolved_variables.items()},
        sourceRefs=list(estimate.source_refs))
    # The public web bridge must keep rejecting a bill's own answer, even in
    # requested review mode. Only a labelled synthetic reuse checks that bridge.
    synthetic_web = calculate_erce_web_item({**p, "bill_no":"SYNTHETIC_INDEXED_REUSE"})
    assert synthetic_web["annualAmountsThousand"] == r["annualAmountsThousand"]
    annual = r.get("annualAmountsThousand")
    if annual is None:
        raise AssertionError(r)
    total = sum(annual)
    return dict(bill_no="2204028",post_answer_regression=True,independent_evaluation=False,
        target_answer_numbers_selected=True,payload=p,result=r,total_thousand=total,
        synthetic_web_reuse_check=True,synthetic_web_result=synthetic_web,
        gold_display_total_thousand=29500000000,
        display_total_difference_percent=abs(total-29500000000)/29500000000*100,
        gold_display_annual_thousand=[5900000000,6000000000,5900000000,5900000000,5800000000],
        limitation="정답 열람 후 인구·물가 전제 추가 및 하위 계산 연결. 독립 예측 성과 아님. 정답0.1조원 표시값 대비 차이이며 원시금액 정밀오차율 아님")


if __name__ == "__main__":
    r=run_regression()
    Path("docs/erce/cases/ERCE_REGRESSION_2204028.json").write_text(
        json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"annual":r["result"]["annualAmountsThousand"],
        "total":r["total_thousand"],"difference_percent":r["display_total_difference_percent"],
        "monthly":r["result"]["resolvedVariables"]["benefit_per_recipient"]["value"]},ensure_ascii=False))
