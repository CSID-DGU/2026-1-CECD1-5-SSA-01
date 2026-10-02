"""Reviewed information-system/plan assumptions, with answer leakage guarded.

The cited 2023 budgets are known here through bill 2211999's estimate, not
independently verified original budget documents. Reuse is only a candidate
after that estimate became available and requires a scope judgment.
"""
from backend.erce.reviewed_variable_rows import evidence_row


def sports_information_system_rows() -> list[dict]:
    common = dict(
        source_bill_no="2211999", available_at="2025-08-08",
        agency="문화체육관광부", policy_domain="스포츠지능정보화",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2211999/cost_estimate.pdf",
        obtained_from="reviewed_answer", reviewed_at="2026-09-28",
    )
    plan = dict(
        scope="스포츠지능정보화 3년 기본계획 수립 연구",
        service_function="기본계획 연구용역", allowed_routes=["research_plan"],
        requires_applicability_note=True,
        limitation="2023~2025 문화디지털혁신 기본계획 예산을 인용한 선례 가정. "
                   "원 예산서는 독립 확인하지 않았으며 후속계획 절반 가정은 보편 단가가 아님",
    )
    build = dict(
        scope="스포츠정보시스템 재난·재해복구체계 2년 구축·운영",
        service_function="정보시스템 재해복구 구축·운영",
        allowed_routes=["information_system_staged_build"],
        system_kind="disaster_recovery", requires_applicability_note=True,
        limitation="서울시 2023년 데이터센터 재해복구 환경 구축예산 21.4억원을 참고해 "
                   "의안별로 연 10억원×2년을 가정한 값. 21.4억원/2의 기계적 단가나 "
                   "모든 재해복구시스템의 공식 단가가 아니며 대상 규모·구축범위 검토 필요",
    )
    return [
        evidence_row(
            evidence_key="2211999:first_plan_unit_cost:2027", variable_key="plan_unit_cost",
            value=220_000_000, unit="KRW/plan", variable_role="first_plan_unit_rate",
            reuse_policy="comparable", source_ref="의안 2211999 비용추계서 25C3287 PDF p.4, 첫 기본계획 예산",
            **common, **plan),
        evidence_row(
            evidence_key="2211999:repeat_plan_unit_cost:2030", variable_key="repeat_plan_unit_cost",
            value=110_000_000, unit="KRW/plan", variable_role="repeat_plan_assumption",
            reuse_policy="comparable", source_ref="의안 2211999 비용추계서 25C3287 PDF p.4, 후속계획 절반 가정",
            **common, **plan),
        evidence_row(
            evidence_key="2211999:disaster_recovery_annual_phase_cost:2030-2031",
            variable_key="annual_phase_cost", value=1_000_000_000,
            unit="KRW/year", variable_role="annual_build_operation_comparable",
            reuse_policy="comparable", source_ref="의안 2211999 비용추계서 25C3287 PDF p.5, 서울시 예산 인용 및 연 10억원 가정",
            **common, **build),
        evidence_row(
            evidence_key="2211999:disaster_recovery_start_offset:2027-2031",
            variable_key="phase_start_offset_years", value=3, unit="year",
            variable_role="target_schedule", reuse_policy="target_only",
            source_ref="의안 2211999 비용추계서 25C3287 PDF p.5, 2029년 통합 후 2030년 착수 가정",
            value_years=[2027, 2028, 2029, 2030, 2031], **common, **build),
        evidence_row(
            evidence_key="2211999:disaster_recovery_duration:2027-2031",
            variable_key="phase_duration_years", value=2, unit="year",
            variable_role="target_schedule", reuse_policy="target_only",
            source_ref="의안 2211999 비용추계서 25C3287 PDF p.5, 구축·운영 2년 가정",
            value_years=[2027, 2028, 2029, 2030, 2031], **common, **build),
    ]
