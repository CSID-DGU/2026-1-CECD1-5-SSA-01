"""Answer-informed frozen reference scenario, not an independent forecast."""
import dataclasses
import json

from backend.erce.disability_expansion_evidence import PROFILE,SCOPE,disability_expansion_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def payload():
    rows=[r for r in disability_expansion_rows() if "official_population_linear_trend" not in r["evidence_key"]]
    return dict(bill_no="2203497",route_key="transfer_recipient",cutoff_date="2026-10-06",
        evidence_mode="development_review",start_year=2025,years=5,support_derivation=PROFILE,
        disability_benefit_scope=SCOPE,disability_population_basis="freeze_2023_eligibility_delta",
        disability_composition_basis="table_2023_frozen",disability_cpi_basis="table_application_years_2025_2029",
        benefit_index_base_year=2024,supplementary_benefit_policy_unchanged=True,
        support_derivation_note="종전3급단일등 신규수급범위.현행차감·기초/부가급여 구분; 기존18~64재가 부부감액비율 준용 후보",
        population_proxy_note="2023년 수급권자 실적 차이동결 후보.추세전망 아님, 사용자 미확정 가정",
        composition_conflict_note="본문2022와표2023 불일치:표2023 구성비 선택.65세차상위초과는표본체3만원선택; 주석5만원은 미반영.시설기초지급은표기초급여행 준용",
        estimation_start_note="원문2025-01-01시행, 물가는정답표의2025~2029 적용연도대로 선택한 후보",
        use_unmatched_source_as_reference=True,unmatched_source_reference_note="회답일이발의일보다앞서동일버전미확인.명시적사후참조시나리오",
        selected_evidence_keys=[r["evidence_key"] for r in rows],
        evidence_selection_reasons={r["evidence_key"]:"같은 급여유형과2023실적동결 후보의 검토용참조" for r in rows},
        explicit_inputs={"payments_per_year":dict(value=12,unit="month/year",source_ref="원문2025시행 및매월지급")})


def run_regression():
    p=payload();r=estimate_routed_item(p)
    web=calculate_erce_web_item({**p,"bill_no":"SYNTHETIC_DISABILITY_EXPANSION","evidence_mode":"holdout"})
    total=sum(r.annual_amounts_thousand)
    return dict(bill_no="2203497",post_answer_regression=True,independent_evaluation=False,
        scenario_only=True,payload=p,result=dataclasses.asdict(r),required_variables_filled=2,
        required_variable_count=2,total_thousand=total,gold_total_thousand=5472400000,
        difference_percent=abs(total-5472400000)/5472400000*100,
        synthetic_web_status=web["status"],synthetic_derivation_trace=web["derivationTrace"],
        unresolved="정답은인구·수급권자비율추세·과거평균연령구성을사용.이번은2023실적동결 가정후보.원자료·표기불일치 검증미완료; 결과를정답재현 또는자동확정값으로취급금지")


if __name__=="__main__":
    print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
