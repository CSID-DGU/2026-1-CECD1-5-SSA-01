"""Partial post-answer regression; never fills absent payment coefficients."""
import dataclasses
import json
from backend.erce.basic_pension_staged_evidence import PROFILE,basic_pension_staged_rows
from backend.erce.variable_evidence_store import evidence_payload_from_db
from backend.erce.support_method_operands import prepare_support_operands
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs
from backend.erce.method_evidence_store import validate_non_estimation_review
from backend.erce.web_bridge import calculate_erce_web_item


def band_payload(band):
    rows=[r for r in basic_pension_staged_rows() if r["pension_income_band"]==band]
    return dict(bill_no="2203602",route_key="transfer_recipient_delta",cutoff_date="2026-10-06",
        evidence_mode="development_review",start_year=2026,years=5,support_derivation=PROFILE,
        pension_income_band=band,pension_payment_model="proportional_increment_reviewed",
        support_derivation_note="하위30%와추가20%분리;정답확인후역사적물가연동 가정",
        pension_payment_factor_note="실제감액을기준액차액의비례계수로표현할수있는지검토필요;근거미확보시입력필요",
        estimation_start_note="정답2026~2030시작가정.원문공포후1년의실제공포일을확인한것은아님",
        selected_evidence_keys=[r["evidence_key"] for r in rows],
        evidence_selection_reasons={r["evidence_key"]:"같은기간·소득구간의근거및공식65세전망" for r in rows},
        explicit_inputs={"payments_per_year":dict(value=12,unit="month/year",source_ref="정답의통년추계가정")})


def decision_payload():
    return dict(bill_no="2203602",cutoff_date="2026-10-06",evidence_mode="development_review",
        decision_evidence_key="2203602:residency_exclusion_not_estimated",reliable_estimation_basis_available=False,
        decision_facts=dict(residency_requirement=True,excluded_population_basis_available=False,exclusion_scope_delegated=True,exclusion_scope_confirmed=False),
        decision_confirmations=dict(residency_exclusion_scope="원문3~4쪽19세이후7년거주요건 신규신청자적용",
            population_basis_review="정답PDF3쪽의배제대상인원정보부재확인.현재외부자료전수조회완료라는주장아님",
            delegated_scope_review="원문대상대통령령위임 및당시정답정확범위미확정 확인;현재시행령존재여부와구별"))


def run_regression():
    runs=[]
    for band in ("lower30","between30_50"):
        p=band_payload(band);h=prepare_support_operands(evidence_payload_from_db(p))
        r,missing=resolve_formula_variables(("recipient_count","benefit_per_recipient","existing_benefit_per_recipient"),
            target_explicit=h.get("explicit_inputs"),official_standard=h.get("official_inputs"),
            calculated_estimate=h.get("calculated_inputs"),precedent_assumption=selected_precedent_inputs(h))
        web=calculate_erce_web_item({**p,"bill_no":"SYNTHETIC_STAGED_PENSION","evidence_mode":"holdout"})
        runs.append(dict(band=band,payload=p,resolved={k:dataclasses.asdict(v) for k,v in r.items()},
            missing_variables=list(missing),missing_operands=h["support_missing_operands"],synthetic_web_status=web["status"]))
    return dict(bill_no="2203602",post_answer_regression=True,independent_evaluation=False,runs=runs,
        required_variables_filled=4,required_variable_count=6,total_thousand=None,gold_partial_total_thousand=11100000000,
        non_estimation_review=validate_non_estimation_review(decision_payload()),
        limitation="급여시계열·공식인구·미추계근거연결만완료.소득구간별수급률·차액감액계수미확보.추가행정비와국외재산신고효과미확정")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
