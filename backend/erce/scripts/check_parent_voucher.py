"""After-answer regression with existing official population, no total-fitting."""
import dataclasses
import json
from backend.erce.parent_voucher_indexed_evidence import PROFILE
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def voucher_payload(age):
    method="2212022:parent_voucher_annual_increment"
    keys=[f"kosis_202312:age{age}_population:total:2026-2030:common",
        f"kosis_202312:age{age}:retro_population:2025:voucher"]
    keys += [f"2212022:voucher:age{age}:{k}:reviewed" for k in
        ("voucher_base_monthly","voucher_growth_rate","execution_rate","retro_monthly_increment")]
    return dict(bill_no="2212022",evidence_mode="development_review",cutoff_date="2026-10-06",
        route_key="direct_annual_amount",support_derivation=PROFILE,parent_benefit_age=age,payer="government",
        start_year=2026,years=5,benefit_index_base_year=2025,
        population_geography="전국",statistical_sex="total",population_vintage="2023-12",
        voucher_projection_basis="annual_increment_not_cumulative",fiscal_scope="national_and_local_combined",
        law_effective_date="2026-03-01",retroactive_date="2025-07-01",
        support_derivation_note="보육료 증가분에만 연령별 상승률 적용; 부모급여 전체액·CPI로 대체하지 않음",
        voucher_overlap_note="보육바우처와 부모급여 현금차액의 합산 지원 증가분만 추계",
        population_proxy_note="정답과 같은2023.12중위 연령별 인구를 사용; 실수급자와 동일하다는 주장 아님",
        estimation_start_note="원문부칙2026년3월1일 시행,2025년7월1일 소급. 2026첫해10개월+2025소급6개월",
        selected_evidence_keys=keys,selected_method_keys=[method],
        evidence_selection_reasons={k:"연령·보육료 증가분·자료연도 검토 후 사후 준용" for k in keys},
        method_selection_reasons={method:"보육료상승분 연동 및 소급지원; CPI물가연동과 구분"},
        method_confirmations={method:dict(voucher_overlap_note="바우처 전체액의 재지급이 아닌 부모급여 인상분",
            population_proxy_note="전국각세별 추계인구 준용",estimation_start_note="원문부칙에 따른10개월+전년도6개월 소급")})


def run_regression():
    results=[]
    for age in (0,1):
        p=voucher_payload(age);r=estimate_routed_item(p)
        web=calculate_erce_web_item({**p,"bill_no":"SIMILAR_PARENT_VOUCHER","evidence_mode":"holdout"})
        results.append(dict(age=age,result=dataclasses.asdict(r),
            reusable_web_status=web["status"],trace=web["derivationTrace"]))
    annual=[sum(r["result"]["annual_amounts_thousand"][i] for r in results) for i in range(5)]
    gold=[1686,1288,1404,1517,1630]
    amounts=[x/100000 for x in annual]
    total=sum(annual)/100000
    return dict(bill_no="2212022",post_answer_regression=True,independent_evaluation=False,
        results=results,required_lower_filled=12,required_lower_count=12,
        annual_thousand=annual,annual_eok=amounts,total_eok=total,gold_total_eok=7525,
        difference_percent=abs(total-7525)/7525*100,
        annual_difference_percent=[abs(a-b)/b*100 for a,b in zip(amounts,gold)],
        gold_annual_eok=gold,gold_age_totals_eok=[4032,3493],
        national_share_reference=.6947,
        limitation="표의 공개된 기준단가·상승률로 계산. 숨은 정밀수치에 맞춰 역산하지 않아 잔여오차 존재",
        unverified_details=["정답 원작업파일의 월증가액 정밀도와 반올림·절사 시점","2022~2025바우처 원단가와 집행계수 원예산서 독립검증"])


if __name__=="__main__":
    print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
