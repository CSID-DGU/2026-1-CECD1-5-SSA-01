"""Cost nature -> service subtype -> fixed-formula leaf.

Empty groups are known but not implemented; never guess a descendant formula.
"""
from __future__ import annotations
from collections.abc import Sequence


ERCE_ROUTE_TREE = {
    "인건비": {
        "보수": {"직급별": "personnel_grade", "평균보수": "personnel_average",
               "직급·직위변경차액": "personnel_position_difference"},
        "기관부담금": "personnel_employer_contribution",
        "기본경비": "personnel_basic_expense",
    },
    "물건비": {
        "법정부담금": {"정부고용부담금구간차액": "government_employment_levy_delta"},
        "정보시스템": {
            "모바일신분증구축운영": "mobile_identity_system_lifecycle",
            "사업계획금액사용": "information_system_project_plan",
            "운영": {
                "연간총액기반": "information_system_operation",
                "인력단가기반": "information_system_operation_staff",
            },
            "구축견적": {"기간지정연간사업비": "information_system_staged_build"},
            "기능개선견적": {},
        },
        "연구용역": {
            "기본계획": "research_plan",
            "실태조사": {"주기적조사": "research_survey", "매년조사": "annual_research_survey",
                     "기존조사연례화차액": "research_survey_annualization_delta",
                     "시설표본확대기존예산차액": "facility_survey_scope_expansion_delta",
                     "기편성연도제외정례조사": "prefunded_annual_survey_delta"},
        },
        "위원회": {"선례가정기반": "committee_operation", "구성요소입력": "committee_components",
                "과거운영실적기반": "committee_annual_operation"},
        "국회위원회": {"운영지원사업비": "legislative_committee_operation"},
        "협의체": {"회의개최운영비": "interagency_meeting_operation",
                 "연간운영비": "interagency_annual_operation"},
        "평가사업": {"평가단및초기지표개발": "evaluation_panel_with_initial_study",
                 "정책영향평가": {"연간연구용역패키지": "policy_impact_annual_contract"}},
        "통지": {"법적우편송달": "legal_notification"},
        "장례안장": {"유골함및명패": "burial_supplies"},
        "일반활동": "goods_service_activity",
        "자산관리": {"유사사업연간예산준용": "asset_management_annual_budget_proxy"},
        "교육홍보": {"아동인식개선통합사업예산": "child_awareness_education_budget"},
        "교육훈련": {"콘텐츠강사교육통합예산동결": "education_training_package_freeze"},
        "자격시험": {"초기재고신규재응시": "qualification_exam_stock_flow"},
        "기존위원회증원": "committee_member_increase",
        "수량단가": "quantity_unit",
        "검증된연간금액": "direct_annual_amount",
        "연관사업": {"기준사업비비율": "related_project_ratio"},
    },
    "이전지출": {
        "보호아동보험료": {"보호비중장래인구대리": "protected_child_insurance_population_share"},
        "지역주민급여": {"관측인구추세국비지방비분리": "regional_resident_benefit_trend"},
        "교통기관지원": {"장애인무임수송보전": "disabled_urban_rail_compensation"},
        "의료기관지원": {"의사소통체계패키지": "hospital_communication_support"},
        "차입이자지원": {"당해신규차입분": "new_borrowing_interest_support"},
        "교육지원": {"급식": {"연간경비공공분담": "school_meal_annual_public_support"}},
        "보상": {"유족연금승진차액": "survivor_pension_cohort_delta",
                 "사망조위금차액": "death_grant_delta"},
        "개인지원": {"일반급여": "transfer_recipient", "아동자산형성월적립": "transfer_child_asset_monthly",
                 "대상인구가감급여": "transfer_recipient_adjusted",
                 "기존급여인상차액": "transfer_recipient_delta",
                 "장애아동수당의무화순증": "disabled_child_allowance_mandatory_delta",
                 "노인공익활동최저임금차액": "elderly_public_activity_wage_delta",
                 "대상자및지급액동시변경": "transfer_population_amount_delta",
                 "기존월급여폐지감소": "transfer_benefit_abolition",
                 "배우자출산휴가급여기간확대": "transfer_spouse_leave_extension",
                 "의료등이용지원": "transfer_service_use",
                 "진단검사비순증지원": "diagnostic_test_subsidy"},
        "사업보조": "transfer_subsidy_rate",
        "인력서비스지원": {"1인중증장애인기업연간업무지원": "enterprise_assistant_annual_support"},
        "표준사업장지원": {"요건완화신청증분": "standard_workplace_subsidy_expansion",
                        "의료법인참고시나리오": "medical_standard_workplace_reference"},
        "고용사업주지원": {"장애인최저임금차액보조": "disabled_worker_minimum_wage_gap"},
        "보험료지원": {"기준선차감": "transfer_premium_subsidy_delta"},
        "사회보험": {"건강보험급여증가국고지원": "health_insurance_treasury_support",
                 "난임치료휴가급여": {"공무원사용률준용": "infertility_leave_civil_proxy",
                                  "예산산출근거준용": "infertility_leave_budget_proxy"},
                 "건강보험일반회계지원기준변경": "health_insurance_general_support_change"},
        "수급자기반국비분담": "transfer_recipient_subsidy",
    },
    "자본지출": {
        "교육시설": {"특수학급정원변경증개축": "special_classroom_expansion"},
        "시설공사": "capital_area", "자산취득": "capital_asset",
        "연차분할설치": "capital_phased_installation",
        "인원기반자산취득": "personnel_asset",
        "묘지조성": "burial_plot_construction",
    },
    "조세감면": {"세율변경": "tax_rate_change", "공제변경": "tax_deduction_change"},
    "세외수입감소": {
        "수수료변경": "non_tax_fee_change",
        "수수료면제": {"기존수입평균": "non_tax_fee_revenue_average",
                       "무료채널전환반영": "non_tax_fee_channel_shift"},
    },
    "출자출연": {"사업분담": "equity_project_share", "기관별출연": "equity_institution_unit"},
    "참고수입": {"장애인고용부담금부문별증가": "employment_levy_reference_receipts"},
}


def route_for_path(path: Sequence[str]) -> str:
    if isinstance(path, (str, bytes)) or not path:
        raise ValueError("route_path must be a nonempty list of tree node names")
    node = ERCE_ROUTE_TREE
    for name in path:
        if not isinstance(node, dict) or name not in node:
            raise KeyError("unknown ERCE tree path: " + "/".join(path))
        node = node[name]
    if not isinstance(node, str):
        raise ValueError("ERCE route_path must reach a registered formula leaf, not a group")
    return node


def formula_leaf_routes(node=None) -> list[str]:
    node = ERCE_ROUTE_TREE if node is None else node
    if isinstance(node, str):
        return [node]
    return [route for child in node.values() for route in formula_leaf_routes(child)]
