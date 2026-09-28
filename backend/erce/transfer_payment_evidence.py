"""Reviewed population inputs for transfer-payment formulas."""
from backend.erce.reviewed_variable_rows import evidence_row


def transfer_payment_rows():
    population = evidence_row(
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
        limitation="다른 연도·월 또는 연령·소득 제한 지원사업에 자동 전용 금지")
    adjusted_population = evidence_row(
        evidence_key="mois:base_population:2024-05",
        variable_key="base_population", value=51_277_347, unit="person",
        source_bill_no="official:mois-resident-population-2024-05",
        available_at="2024-05-31",
        source_ref="행정안전부 주민등록인구현황, 2024년 5월말 전국 51,277,347명",
        source_url="https://jumin.mois.go.kr/statMonth.do",
        agency="전국", policy_domain="인구통계", scope="2024년 5월말 전국 주민등록인구",
        service_function="전국민 일회성 지원금 대상인구 조정", variable_role="baseline_actual",
        reuse_policy="same_scope", source_class="official_standard",
        allowed_routes=["transfer_recipient_adjusted"], valid_from_year=2024, valid_to_year=2024,
        reference_date="2024-05-31", reviewed_at="2026-09-28",
        limitation="기준 인구일 뿐, 특정 법안의 최종 지급 대상자는 아님")
    answer_common = dict(
        source_bill_no="2200563", available_at="2024-07-11",
        source_ref="의안 2200563 비용추계서(24D0967), PDF p.3~5, [표 2]",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2200563/cost_estimate.pdf",
        agency="전국", policy_domain="민생회복지원금", scope="2024년 일회성 민생회복지원금",
        service_function="법안 제5조 지급대상 인구 조정",
        reuse_policy="target_only", source_class="precedent_assumption",
        allowed_routes=["transfer_recipient_adjusted"], reviewed_at="2026-09-28",
        obtained_from="reviewed_answer", value_years=[2024],
    )
    excluded = evidence_row(
        evidence_key="2200563:excluded_recipients:2024", variable_key="excluded_recipients",
        value=53_738, unit="person", variable_role="target_quantity", **answer_common,
        components={"correctional_inmates_2022": 52_940, "forensic_hospital_2022": 798},
        limitation="두 수용자 집계는 2022년 관측치의 정답 추계 가정. 다른 법안에 자동 재사용 금지")
    added = evidence_row(
        evidence_key="2200563:additional_recipients:2024", variable_key="additional_recipients",
        value=2_067_362, unit="person", variable_role="target_quantity", **answer_common,
        components={"long_term_foreigners_2023": 1_881_921, "permanent_residents_2023": 185_441},
        possible_overlap_count=185_441,
        limitation="정답 재현 전용. 법무부 통계의 장기 체류외국인 1,881,921명에 F-5 영주자 185,441명이 이미 포함될 가능성이 있어 별도 가산은 중복 위험. 다른 법안 전용 금지")
    return [population, adjusted_population, excluded, added]
