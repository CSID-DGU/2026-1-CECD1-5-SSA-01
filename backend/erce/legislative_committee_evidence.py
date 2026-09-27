"""Legislative support staff and operating budgets, not civilian meeting fees."""
from backend.erce.reviewed_variable_rows import evidence_row


def legislative_committee_rows():
    common = dict(agency="국회사무처",policy_domain="국회위원회",
        scope="국회 소규모 상설위원회 입법·심의 지원 공무원 및 운영",
        service_function="국회 상설 특별위원회 지원",
        obtained_from="non_target_source", reuse_policy="comparable",
        limitation="국회의원 정수와 지원 공무원 수는 별개. 순증 여부·재배치·직급 구성은 대상에서 재검토")
    older = dict(source_bill_no="2212534",available_at="2025-09-12",
        source_ref="의안2212534, 25D4707, 비용추계서 PDF p.5~6 표3·4 및 각주6; 11명 지원공무원 보수와 기관부담 전망",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2212534/cost_estimate.pdf")
    newer = dict(source_bill_no="2214994",available_at="2026-03-24",
        source_ref="의안2214994, 25D6771, 비용추계서 PDF p.4~6; 소규모 2개 위원회 11·9명, 운영경비 평균",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2214994/cost_estimate.pdf")
    salary_totals=[1022000000,1047000000,1072000000,1098000000,1124000000]
    return [
        evidence_row(evidence_key="2214994:legislative_support_headcount:2026",variable_key="headcount",
            value=10,unit="person",variable_role="headcount_assumption",allowed_routes=["personnel_average","personnel_asset"],
            reference_member_count=18,reference_staff_grades={"수석전문위원":1,"전문위원":1,"3~4급":1,"4~5급":2,"6급":1,"7급":1,"8급":1,"9급":2},
            required_workload_features={"budget_settlement_pre_review":True},
            assumes_net_new_staff=True,**common,**newer),
        evidence_row(evidence_key="2212534:legislative_salary_per_person:2026-2030",variable_key="salary_per_person",
            value=[amount/11 for amount in salary_totals],unit="KRW/person/year",variable_role="unit_rate",
            allowed_routes=["personnel_average"],value_years=[2026,2027,2028,2029,2030],
            reference_staff_count=11,reference_salary_totals_won=salary_totals,
            reference_staff_grades={"수석전문위원":1,"전문위원":1,"3~4급":2,"4~5급":2,"6급":1,"7급":1,"8급":1,"9급":2},
            price_status="같은 국회 지원직군의 선례 평균보수. 공식 직급별 보수표를 독립 확인한 값 아님",
            rounding_note="원문 백만원 단위 보수총액을 11명으로 나눈 비교단가; 평균 사용에 따른 직급구성 차이 있음",**common,**older),
        evidence_row(evidence_key="2214994:legislative_employer_rate:2026-2030",variable_key="employer_contribution_rate",
            value=[.13067,.13129,.13193,.13285,.13379],unit="ratio",variable_role="forecast_assumption",
            allowed_routes=["personnel_employer_contribution"],value_years=[2026,2027,2028,2029,2030],
            forecast_vintage="nabo_employer_contribution_2026_01",**common,**newer),
        evidence_row(evidence_key="2214994:legislative_basic_expense_ratio:2026",variable_key="basic_expense_ratio",
            value=.082,unit="ratio",variable_role="expense_ratio_assumption",allowed_routes=["personnel_basic_expense"],**common,**newer),
        evidence_row(evidence_key="2214994:legislative_asset_per_person:2026",variable_key="asset_unit_price_per_person",
            value=4980000,unit="KRW/person",variable_role="unit_rate",allowed_routes=["personnel_asset"],
            valid_from_year=2026,valid_to_year=2030,price_year=2026,occurrence_policy="지원인력 신설 첫해만 1회; annual recurring asset cost 아님",**common,**newer),
        evidence_row(evidence_key="2214994:legislative_annual_operating_budget:2026",variable_key="annual_operating_amount",
            value=156000000,unit="KRW/committee/year",variable_role="annual_budget_comparable",pricing_basis="annual_total",
            allowed_routes=["legislative_committee_operation"],price_year=2026,
            comparison_member_counts=[17,12],comparison_staff_counts=[11,9],
            budget_includes="운영지원 사업비. 지원직원 보수·기관부담금·기본경비·신규 자산취득과 별도 계상한 선례",
            source_discrepancy="본문은2026년 평균1.56억원, 각주는2025년1.55·1.53억원 인용. 연도별 갱신 산출 원자료는 독립 확인하지 않음",**common,**newer),
        evidence_row(evidence_key="2214994:legislative_operating_growth:2026",variable_key="growth_rate",
            value=.02,unit="ratio/year",variable_role="forecast_assumption",allowed_routes=["legislative_committee_operation"],
            forecast_vintage="source_cost_estimate_2026",**common,**newer),
    ]


POLICY_REVIEW_STAFF_GRADES={"수석전문위원":1,"전문위원":1,"3~4급":0,"4~5급":1,"6급":1,"7급":0,"8급":1,"9급":1}


def policy_review_committee_rows():
    """Reviewed small-policy-committee model; not all legislative bodies have six staff."""
    common=dict(agency="국회사무처",policy_domain="국회위원회",
        scope="예산·결산 예비심사 없는 제한된 정책심의 특별위원회",
        service_function="국회 소규모 정책심의 지원",source_bill_no="2215199",available_at="2026-03-24",
        source_ref="의안2215199, 25D6889, 비용추계서 PDF p.4~6 표2·3; 업무 권한에 따른 6명 직급모델 및 2026년 국회 예산 인용",
        source_url="backend/generated/assembly_22_validation_holdout_v1/by_bill/2215199/cost_estimate.pdf",
        obtained_from="reviewed_answer",reuse_policy="comparable",
        limitation="6명은 해당 업무를 고려한 선례 가정. 공식 직제 별표·급여 예산 원본을 독립 확인한 값 아님")
    return [
        evidence_row(evidence_key="2215199:policy_review_staff_model:2026",variable_key="headcount",
            value=6,unit="person",variable_role="headcount_assumption",
            allowed_routes=["personnel_average","personnel_asset"],reference_staff_grades=POLICY_REVIEW_STAFF_GRADES,
            required_workload_features={"budget_settlement_pre_review":False},
            applicability_note="제한된 법안·정책심의, 예결산 예비심사 없음. 의원 수와 자동 비례하지 않음",**common),
        evidence_row(evidence_key="2215199:policy_review_salary_per_person:2027-2031",variable_key="salary_per_person",
            value=[amount/6 for amount in [627000000,646000000,666000000,685000000,706000000]],
            unit="KRW/person/year",variable_role="unit_rate",allowed_routes=["personnel_average"],
            value_years=[2027,2028,2029,2030,2031],required_staff_grade_profile=POLICY_REVIEW_STAFF_GRADES,
            required_workload_features={"budget_settlement_pre_review":False},
            pricing_basis="특정 6명 직급구성의 평균보수. 10·11명 모델 평균보수로 대체하지 않음",
            rounding_note="공개 보수총액 백만원 단위의 표시값으로 나눈 관찰단가. 직급별 원 급여표는 미확보",**common),
        evidence_row(evidence_key="2215199:legislative_employer_rate:2027-2031",variable_key="employer_contribution_rate",
            value=[.13130,.13194,.13286,.13380,.13476],unit="ratio",variable_role="forecast_assumption",
            allowed_routes=["personnel_employer_contribution"],value_years=[2027,2028,2029,2030,2031],
            source_discrepancy="각주 마지막 연도가2030으로 중복 표기. 본문 추계기간에 따라 마지막 항목2031로 해석",**common),
        evidence_row(evidence_key="2215199:legislative_asset_per_person:2027",variable_key="asset_unit_price_per_person",
            value=5080000,unit="KRW/person",variable_role="unit_rate",allowed_routes=["personnel_asset"],
            price_year=2027,valid_from_year=2027,valid_to_year=2031,
            occurrence_policy="신설 첫해1회. 2027 적용 선례 단가이며 다음 사업 신설연도에 자동 고정 금지",**common),
    ]
