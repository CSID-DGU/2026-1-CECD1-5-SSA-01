"""Reviewed variable evidence recovered from an existing non-target document.

The AI selects rows explicitly. No law-to-precedent/formula selector is used.
"""

SERVICE_INDUSTRY_VARIABLES = {
    "plan_unit_cost": {
        "value": 130000000, "unit": "KRW/plan",
        "source_bill_no": "2214690", "available_at": "2025-12-17",
        "source_ref": "2214690, 25A6558, PDF p.9: 건축서비스 2019년 88백만원/2023년 107백만원, 생활물류 2022년 196백만원; 추계 적용 평균 130백만원",
        "service_function": "5년 주기 서비스산업 진흥 기본계획 연구용역",
        "scope": "중앙정부 법정 산업발전계획", "source_class": "precedent_assumption",
    },
    "committee_components": {
        "value": [{"paid_members": 20, "annual_meetings": 4, "meeting_unit_price": 250000}],
        "unit": "component_bundle", "source_bill_no": "2214690", "available_at": "2025-12-17",
        "source_ref": "2214690, 25A6558, PDF p.9: 위원 35명 이내/위촉20명 이내, 민간20명·분기1회·수당25만원 동결 가정",
        "service_function": "서비스산업 관련 범정부 정책 심의위원회",
        "scope": "중앙정부 위원회 1개, 민간위원장 포함 민간위원20명",
        "source_class": "precedent_assumption",
        "rate_status": "예산지침 고려한 선례 가정; 원 지침에서 공식 지급액 독립검증 전",
    },
}

# Post-answer observation is isolated from the pre-answer evidence above.
# It is not eligible when bill_no == 2216475 or cutoff_date < 2026-02-10.
SERVICE_INDUSTRY_POST_ANSWER_VARIABLES = {
    "committee_components": {
        "value": [{"paid_members": 20, "annual_meetings": [2, 4, 4, 4, 4],
                   "meeting_unit_price": 300000}],
        "unit": "component_bundle", "source_bill_no": "2216475", "available_at": "2026-02-10",
        "source_ref": "2216475, 26A0588, PDF p.7~9: 민간20명·연4회·2026년2회·수당30만원 가정",
        "service_function": "서비스산업선진화위원회 정책 심의",
        "scope": "중앙정부 위원회1개, 민간20명; 2026~2030년 관찰값",
        "source_class": "precedent_assumption",
        "schedule_start_year": 2026,
        "rate_status": "공식 상한20만원+2시간 이상 추가10만원을 고려한 선례 지급액 가정; 실제 회의시간 독립 검증 전",
        "reuse_note": "첫해2회는 새 법안에 자동 재사용 금지; 시행일/추계연도별 별도 확인",
    },
}
