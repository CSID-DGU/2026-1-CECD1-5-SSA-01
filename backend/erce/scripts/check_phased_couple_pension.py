"""Observed-data reinforcement; compare models without fitting the gold total."""
import dataclasses
import json
from backend.erce.phased_couple_pension import PROFILE,phased_couple_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def payload(mode="ols_2021_2024"):
    rows=phased_couple_rows()
    def v(value,ref):return dict(value=value,unit="ratio",source_ref=ref)
    return dict(bill_no="2211669",route_key="transfer_population_amount_delta",cutoff_date="2026-10-06",
        evidence_mode="development_review",start_year=2026,years=5,support_derivation=PROFILE,
        pension_standard_vintage="2025_03_reviewed_forecast",pension_trend_model=mode,
        couple_recovery_model="standard_amount_proxy",
        support_derivation_note="원문75%확대·2026~2030부부감액10·5·0·0·0% 일정.단독수급과부부1인에부부감액적용금지",
        pension_trend_note="공식2021~2024관측비율의명시적OLS또는동결후보.정답의구체추세방식은미확인",
        couple_recovery_note="기준액×부부수급비율×감액률회복의후보.국민연금연계·소득역전감액으로제한되는실제차액은아직미확인",
        selected_evidence_keys=[r["evidence_key"] for r in rows],
        evidence_selection_reasons={r["evidence_key"]:"동일연령·급여사업의관측이력및동일추계기간전망버전 재사용" for r in rows},
        explicit_inputs=dict(new_eligibility_share=v(.75,"원문제3조75%"),old_eligibility_share=v(.7,"현행제3조70%"),
            old_couple_reduction=v(.2,"원문신구대비표현행20%"),new_couple_reduction=v([.1,.05,0,0,0],"원문부칙2026년10%·2027년5%이후폐지"),
            payments_per_year=dict(value=12,unit="month/year",source_ref="2026-01-01시행·월급여")))


def run_regression():
    runs=[]
    for mode in ("ols_2021_2024","freeze_2021_2024"):
        p=payload(mode);r=estimate_routed_item(p)
        web=calculate_erce_web_item({**p,"bill_no":"SYNTHETIC_PHASED_PENSION","evidence_mode":"holdout"})
        total=sum(r.annual_amounts_thousand)
        runs.append(dict(model=mode,payload=p,result=dataclasses.asdict(r),total_thousand=total,
            difference_percent=abs(total-30100000000)/30100000000*100,
            derivation_trace=web["derivationTrace"],synthetic_web_status=web["status"]))
    return dict(bill_no="2211669",post_answer_regression=True,independent_evaluation=False,
        required_variables_filled=5,required_variable_count=5,gold_total_thousand=30100000000,runs=runs,
        unresolved="정답의유형별감액·실제회복액교차정보와정확한추세모형미재현.정답예측기준액및2024실적보강만으로정확한순증을보장하지않음.결과에맞춰모형선택/계수조정하지않음")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
