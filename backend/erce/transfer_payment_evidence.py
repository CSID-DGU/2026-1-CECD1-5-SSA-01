"""Reviewed population inputs for transfer-payment formulas."""
from backend.erce.reviewed_variable_rows import evidence_row


def transfer_payment_rows():
    return [evidence_row(
        evidence_key="mois:registered_population:2024-05",
        variable_key="recipient_count", value=51_277_347, unit="person",
        source_bill_no="official:mois-resident-population-2024-05",
        available_at="2024-05-31",
        source_ref="행정안전부 주민등록인구현황, 2024년 5월말 전국 51,277,347명",
        source_url="https://jumin.mois.go.kr/statMonth.do",
        agency="전국", policy_domain="인구통계", scope="2024년 5월말 전국 주민등록인구",
        service_function="전국민 일회성 지원금", variable_role="target_quantity",
        reuse_policy="same_scope", source_class="official_standard",
        allowed_routes=["transfer_recipient"], valid_from_year=2024, valid_to_year=2024,
        reference_date="2024-05-31",
        limitation="다른 연도·월 또는 연령·소득 제한 지원사업에 자동 전용 금지")]
