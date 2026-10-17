"""Post-answer scenario regression; source table discrepancies remain visible."""
import json
from dataclasses import asdict
from pathlib import Path

from backend.erce.child_allowance_birth_order_evidence import PROFILE, SCENARIOS, evidence_keys
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def reviewed_payload(scenario):
    return dict(bill_no="2208381",route_key="transfer_population_amount_delta",
        evidence_mode="development_review",cutoff_date="2026-10-04",start_year=2026,years=5,
        support_derivation=PROFILE,support_derivation_note="정답열람후 인구·집행계수·순위비율 근거 적재 및 하위변수 연결, 회귀검증",
        child_population_geography="전국",parent_benefit_unchanged=True,
        birth_order_population_basis="birth_share_proxy",birth_order_share_scenario=scenario,
        birth_order_scope_note="첫째·둘째·셋째이상 가중월액, 전체연령에 같은출생순위비율준용. 실제형제순위 관측아님. 가족인정범위 미확정은 선례가정으로검토",
        birth_order_scenario_note="표3연도별전망과표4암시2026비율동결을 구분. 표시총액에맞춰값수정하지않음",
        estimation_start_note="원문2026-01-01시행,2026~2030년각12개월",
        explicit_inputs={
            **{f"birth_amount_{rank}":dict(value=amount,unit="KRW/person/month",source_ref=f"원문3쪽{rank}월액") for rank,amount in zip(("first","second","third_plus"),(100000,150000,200000))},
            "existing_benefit_per_recipient":dict(value=100000,unit="KRW/person/month",source_ref="원문5쪽현행월10만원"),
            "payments_per_year":dict(value=12,unit="month/year",source_ref="원문2026-01-01시행·월지급")},
        selected_evidence_keys=evidence_keys(scenario),
        evidence_selection_reasons={key:"정답열람후확인한출처·기간·연령·집행계수동결및순위대리가정.자기정답이므로개발검토모드에한정" for key in evidence_keys(scenario)})


def run_regression():
    runs=[]
    for scenario in SCENARIOS:
        p=reviewed_payload(scenario);e=estimate_routed_item(p)
        # No relaxation of the public web bridge's own-answer exclusion.
        web=calculate_erce_web_item({**p,"bill_no":"SYNTHETIC_BIRTH_ORDER_REUSE"})
        annual=list(e.annual_amounts_thousand);assert web["annualAmountsThousand"]==annual
        total=sum(annual)
        runs.append(dict(scenario=scenario,payload=p,annual_amounts_thousand=annual,total_thousand=total,
            display_total_difference_percent=abs(total-31800000000)/31800000000*100,
            resolved_variables={k:asdict(v) for k,v in e.resolved_variables.items()},
            synthetic_web_reuse_check=True,synthetic_web_result=web))
    return dict(bill_no="2208381",post_answer_regression=True,independent_evaluation=False,
        target_answer_numeric_rows_added=True,gold_display_total_thousand=31800000000,
        gold_display_annual_thousand=[6900000000,6700000000,6300000000,6100000000,5800000000],runs=runs,
        remaining="비율설명·계산인원표·반올림합계 불일치의 원시계산자료 미확인. 국비분리·실제연령별순위준용 검증 미포함",
        limitation="정답열람후자료적재회귀검증. 정답표시금액에맞추기위한반올림·비율조정없음.표시총액차이는원시금액정밀오차율아님")


if __name__=="__main__":
    r=run_regression()
    Path("docs/erce/cases/ERCE_REGRESSION_2208381.json").write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps([{k:x[k] for k in ("scenario","total_thousand","display_total_difference_percent")} for x in r["runs"]],ensure_ascii=False))
