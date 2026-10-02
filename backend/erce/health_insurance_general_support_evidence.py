"""Reference inputs for changes to general-account health-insurance support."""
from __future__ import annotations

from backend.erce.reviewed_variable_rows import evidence_row


NABO_OUTLOOK = "https://www.nabo.go.kr/ko/report/projectionView.do?idx=8112"
NABO_SETTLEMENT = "https://www.nabo.go.kr/ko/report/analysisView.do?idx=8414&key=2509250001"
ANSWER_2202487 = "backend/generated/assembly_22_pdfs/by_bill/2202487/cost_estimate.pdf"


def health_insurance_general_support_rows() -> list[dict]:
    # 2023 actual and 2024-29 outlook published before bill 2202487 (2024-08-01).
    receipts = {
        "2023": 81_518_000_000_000,
        "2024": 85_100_000_000_000,
        "2025": 91_900_000_000_000,
        "2026": 99_200_000_000_000,
        "2027": 107_200_000_000_000,
        "2028": 115_700_000_000_000,
        "2029": 125_100_000_000_000,
    }
    rows = [evidence_row(
        evidence_key="official:nabo:health-insurance-premium-receipts:2023-2029",
        variable_key="premium_receipts_by_year", value=receipts, unit="KRW/year",
        source_bill_no="official:nabo:health-insurance-outlook-2023",
        available_at="2024-07-18",
        source_ref=("NABO 2023~2032 건강보험 재정전망(2023-10-10) 표25의 2024~2029 전망(조원, 반올림) "
                    "+ 2023회계연도 결산 분석(2024-07-18) p.12의 2023 실제 보험료수입 815,180억원"),
        agency="국회예산정책처", policy_domain="건강보험 일반회계 국고지원",
        scope="건강보험료 수입; 일반회계 지원 산식의 분모. 2023 결산 실적 및 2024~2029 전망",
        service_function="전전년도 보험료 수입 기준 일반회계 국고지원",
        variable_role="historical_actual_and_official_forecast", source_class="official_standard",
        source_url=f"{NABO_OUTLOOK} | {NABO_SETTLEMENT}",
        series_years=[2023, 2024, 2025, 2026, 2027, 2028, 2029],
        approximation_note="2024~2029는 조원 단위 반올림 전망치; 정확한 연도별 실적·전망치와 차이 가능",
        allowed_routes=["health_insurance_general_support_change"],
        limitation="보험료 수입 시계열만 제공. 국고지원율·재정분담 정책은 별도 확인 필요",
    )]
    # Weighted 2021-23 actual general-account support / actual premium receipts.
    # This is a historical proxy, not a statutory rate or a guaranteed budget rate.
    rows.append(evidence_row(
        evidence_key="official:nabo:general-account-effective-rate:2021-2023",
        variable_key="current_general_support_rate",
        value=(76_554 + 86_843 + 91_494) / (692_270 + 765_538 + 815_180),
        unit="ratio", source_bill_no="official:nabo:settlement-2023",
        available_at="2024-07-18",
        source_ref=("NABO 2023회계연도 결산 분석(2024-07-18) p.12 표: "
                    "2021~2023 일반회계 지원액 합계 ÷ 같은 기간 실제 보험료수입 합계"),
        agency="국회예산정책처", policy_domain="건강보험 일반회계 국고지원",
        scope="2021~2023 일반회계 지원액 / 결산 보험료수입 가중 실효율",
        service_function="현행 일반회계 지원 기준의 역사적 비교값",
        variable_role="historical_effective_rate", source_class="precedent_assumption",
        allowed_routes=["health_insurance_general_support_change"],
        reuse_policy="comparable", requires_applicability_note=True,
        obtained_from="independent_pre_bill_official_source",
        limitation="법정 14%가 아님. 과거 실제 지원액을 결산 보험료수입으로 나눈 참고값이며, 현행 기준 전망과 다를 수 있음",
    ))
    return rows


def health_insurance_general_support_answer_rows() -> list[dict]:
    """Exact target-answer figures, time-gated from its 2024-08-01 proposal."""
    common = dict(
        source_bill_no="2202487", available_at="2024-08-29",
        source_ref="의안 2202487 비용추계서(2024-08-29 회답)",
        source_url=ANSWER_2202487, agency="국회예산정책처",
        policy_domain="건강보험 일반회계 국고지원",
        scope="의안 2202487 비용추계에서 사용한 보험료수입 및 현행 일반회계 기준",
        service_function="전전년도 보험료 수입 기준 일반회계 국고지원",
        allowed_routes=["health_insurance_general_support_change"],
        reuse_policy="comparable", requires_applicability_note=True,
        obtained_from="reviewed_answer",
        limitation="발의 후 공개된 정답지 값. 2202487의 발의일 기준 추정에는 사용 금지; 다른 안에 적용할 때는 기간·기준 확인 필요",
    )
    return [
        evidence_row(
            evidence_key="2202487:premium_receipts_by_year:2023-2029",
            variable_key="premium_receipts_by_year",
            value={"2023": 81_518_000_000_000, "2024": 85_085_000_000_000,
                   "2025": 91_854_100_000_000, "2026": 99_212_700_000_000,
                   "2027": 107_175_600_000_000, "2028": 115_740_800_000_000,
                   "2029": 125_074_100_000_000},
            unit="KRW/year", variable_role="answer_series", source_class="precedent_assumption",
            series_years=[2023, 2024, 2025, 2026, 2027, 2028, 2029], **common,
        ),
        evidence_row(
            evidence_key="2202487:current_general_support_rate:2024",
            variable_key="current_general_support_rate", value=.115, unit="ratio",
            variable_role="answer_assumption", source_class="precedent_assumption",
            **common,
        ),
    ]
