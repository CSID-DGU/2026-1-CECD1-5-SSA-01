"""Official fee rows and target-specific observations kept separate."""

OFFICIAL_REGISTRATION_FEES = (
    {"key": "internet_real_estate_view_2025_08_01", "service": "부동산등기기록 열람",
     "channel": "internet", "value": 700, "unit": "KRW/case", "source_class": "official_standard",
     "effective_from": "2025-08-01", "verified_at": "2026-09-27",
     "source_ref": "등기사항증명서 등 수수료규칙 제3조제2항, 제3222호 시행본",
     "source_url": "https://www.easylaw.go.kr/CSP/CnpClsMainBtr.laf?ccfNo=3&cciNo=1&cnpClsNo=2&csmSeq=649"},
    {"key": "internet_real_estate_issue_2025_08_01", "service": "부동산등기사항증명서 발급",
     "channel": "internet", "value": 1000, "unit": "KRW/copy", "source_class": "official_standard",
     "effective_from": "2025-08-01", "verified_at": "2026-09-27",
     "source_ref": "등기사항증명서 등 수수료규칙 제2조제2항, 제3222호 시행본",
     "source_url": "https://www.easylaw.go.kr/CSP/CnpClsMainBtr.laf?ccfNo=3&cciNo=1&cnpClsNo=2&csmSeq=649"},
)

# Obtained only after opening the target answer, not eligible for its blind test.
POST_ANSWER_REGISTRATION_OBSERVATIONS = {
    "source_bill_no": "2215482", "available_at": "2026-03-26",
    "source_ref": "2215482, 25D7080, 비용추계서 PDF p.4~5; 대법원 제공자료 인용",
    "service_function": "부동산등기 열람·발급 수수료 면제",
    "scope": "전국, 전자/비전자 채널 구분; 부동산 등기 한정",
    "historical_years": [2020, 2021, 2022, 2023, 2024],
    "electronic_fee_revenues_won": [74014000000, 78829000000, 72665000000, 73226000000, 73973000000],
    "nonelectronic_fee_revenues_won": [8261000000, 8065000000, 6956000000, 6276000000, 6077000000],
    "channel_shift_assumption": 0.5,
    "nonelectronic_growth_assumption": -0.074,
    "accounting_caveat": "정답 표에는 기존 1회 면제액 포함. 실제 징수액과 구분·중복면제 차감 검토 필요",
    "reuse_policy": "다른 사업의 수입규모로 자동 전용하지 않음. 전환율50%는 시나리오 가정, 법정 고정값 아님",
}
