"""Post-answer regression; reuse existing sources, do not fit the printed total."""
import json
from pathlib import Path

from backend.erce.family_benefit_indexed_evidence import CHILD_KEYS, CHILD_PROFILE, PARENT_PROFILE, parent_keys
from backend.erce.web_bridge import calculate_erce_web_item


def reviewed_payloads():
    common=dict(bill_no="2206822",cutoff_date="2026-10-04",start_year=2025,years=5,
        child_index_base_year=2024,child_population_geography="전국",
        support_derivation_note="정답24C4317 확인 후 기존 인구·공식기준액·24C3796 물가전망 근거를 재사용하는 사후 회귀검증",
        estimation_start_note="원문2025-01-01시행·매월지급,2025~2029년 완전연도12개월",
        family_index_scope_note="기본 아동수당과 부모급여는 별도. 부모급여 현금·보육료를 두 급여로 중복가산하지 않고 같은 기본부모급여 기준액의 인상차액만 계산. 법정하한 반영")
    monthly=dict(value=12,unit="month/year",source_ref="원문2025-01-01시행·매월 지급 완전연도")
    child={**common,"route_key":"transfer_population_amount_delta","support_derivation":CHILD_PROFILE,
        "child_allowance_scenario":"all_under18_indexed_parent_changed","parent_benefit_unchanged":False,
        "selected_evidence_keys":list(CHILD_KEYS),
        "explicit_inputs":{"existing_benefit_per_recipient":dict(value=100000,unit="KRW/person/month",source_ref="원문5쪽 현행 월10만원"),
            "minimum_monthly_amount":dict(value=100000,unit="KRW/person/month",source_ref="원문3쪽 기본급여 월10만원 이상"),"payments_per_year":monthly}}
    items=[("기본 아동수당",child)]
    for age in (0,1):
        parent={**common,"route_key":"transfer_recipient_delta","support_derivation":PARENT_PROFILE,
            "child_allowance_scenario":"parent_age_indexed","parent_benefit_age":age,
            "parent_population_basis":"forecast_population_proxy",
            "parent_population_proxy_note":"24C4317 표5·6의같은연령 중위 전망인구 준용 방법을 확인. 실제 수급관측값 아님. 별도 아동수당 지급률 전용하지 않음",
            "selected_evidence_keys":list(parent_keys(age)),
            "explicit_inputs":{"minimum_monthly_amount":dict(value=500000,unit="KRW/person/month",source_ref="원문3쪽2세미만 추가급여 월50만원 이상"),"payments_per_year":monthly}}
        items.append((f"부모급여 {age}세",parent))
    for _,payload in items:
        payload["evidence_selection_reasons"]={k:"전국·같은 연령·기간·기준연도·통계버전 확인. 공식값과 선례가정 구분, 현재 최신통계로 주장하지 않음" for k in payload["selected_evidence_keys"]}
    return items


def run_regression():
    items=[dict(name=name,payload=p,result=calculate_erce_web_item(p)) for name,p in reviewed_payloads()]
    assert all(item["result"]["status"]=="computed_review" for item in items)
    totals=[sum(item["result"]["annualAmountsThousand"]) for item in items]
    annual=[sum(item["result"]["annualAmountsThousand"][i] for item in items) for i in range(5)]
    gold=[26600000000,939800000,454200000]
    return dict(bill_no="2206822",post_answer_regression=True,independent_evaluation=False,
        current_target_numeric_rows_added=False,items=items,component_totals_thousand=totals,
        gold_display_component_totals_thousand=gold,
        component_display_differences_percent=[abs(v-g)/g*100 for v,g in zip(totals,gold)],
        parent_total_thousand=sum(totals[1:]),gold_display_parent_total_thousand=1394000000,
        parent_display_difference_percent=abs(sum(totals[1:])-1394000000)/1394000000*100,
        annual_amounts_thousand=annual,total_thousand=sum(totals),gold_display_total_thousand=28000000000,
        display_total_difference_percent=abs(sum(totals)-28000000000)/28000000000*100,
        scope="기본급여·0세부모급여·1세부모급여 합계. 국비·지방비분할 미포함",
        limitation="정답을 본 뒤 전망인구 준용과 하위 계산을 보강한 회귀검증. 기존 원출처 수치 재사용이지만 독립검증 아님. 정답금액 표시단위가 달라 차이를 원시금액 정밀오차율로 해석하지 않음")


if __name__=="__main__":
    r=run_regression()
    Path("docs/erce/cases/ERCE_REGRESSION_2206822.json").write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:r[k] for k in ("component_totals_thousand","component_display_differences_percent",
        "parent_total_thousand","parent_display_difference_percent","total_thousand","display_total_difference_percent")},ensure_ascii=False))
