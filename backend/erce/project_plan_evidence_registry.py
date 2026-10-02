"""Project-specific reference metadata, deliberately NOT reusable unit rates.

This registry is documentation of observed precedent scope. The engine does not
load its budgets for other bills; a new target must provide its own plan evidence.
"""

PROJECT_PLAN_REFERENCES = ({
    "key": "climate_adaptation_platform_2200093",
    "source_bill_no": "2200093",
    "available_at": "2024-08-13",
    "agency": "국립환경과학원",
    "policy_domain": "기후위기적응정보",
    "service_function": "기후위기 적응정보 수집·공개·활용 통합플랫폼",
    "target_population": "중앙행정기관·지자체·산업계·연구계·학계·국민",
    "scale_basis": "국립환경과학원 해당 사업 ISP의 연도별 재원배분",
    "plan_period": "2023-09-08~2024-02-05",
    "budget_years": (2025, 2026, 2027, 2028, 2029),
    "annual_budget_won": (5326000000, 5737000000, 4324000000, 3724000000, 0),
    "includes_operations_maintenance": True,
    "source_ref": "의안 2200093, 24B0438, 비용추계서 PDF p.2~4; 국립환경과학원 ISP 인용",
    "independently_verified_plan": False,
    "reusable_unit_rate": False,
    "limitations": (
        "2029년 0은 정답 표의 해당 추계기간 표시이며 이후 운영비 0을 뜻하지 않음; "
        "별도 조사연구·기술개발·전문기관 지원 등은 구체 계획 부재로 미추계; "
        "유지관리비 포함 여부는 선례별 확인 사항이지 정보시스템 전체의 고정 규칙 아님"
    ),
},)
