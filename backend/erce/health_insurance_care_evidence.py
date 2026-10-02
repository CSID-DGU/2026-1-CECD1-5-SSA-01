"""Pre-existing public references for health-insurance care-benefit estimates.

These are reusable *candidates*, not target-bill answers. In particular, the
pilot's 1,200 participants are not a national eligible population estimate.
"""
from __future__ import annotations

from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_evidence_store import find_variable_candidates


MOHW_PILOT_URL = (
    "https://www.mohw.go.kr/board.es?act=view&bid=0027&list_no=1480370"
    "&mid=a10503000000"
)
NABO_OUTLOOK_URL = "https://www.nabo.go.kr/ko/report/projectionView.do?idx=8112"
ANSWER_2200100_PATH = "backend/generated/assembly_22_pdfs/by_bill/2200100/cost_estimate.pdf"


def health_insurance_care_rows() -> list[dict]:
    """Versioned reference values published before bill 2200100 was proposed."""
    common = dict(
        source_bill_no="official:mohw:care-pilot-2024-02-22",
        available_at="2024-02-22",
        source_ref="보건복지부, 요양병원 간병지원 1단계 시범사업 공모(2024-02-22), 병원 배치유형 표",
        source_url=MOHW_PILOT_URL,
        agency="보건복지부",
        policy_domain="건강보험 요양병원 간병급여",
        scope="요양병원 간병지원 1단계 시범사업; 180일 이하 기본 본인부담률",
        service_function="신규 간병급여로 인한 공단급여비 증가",
        reuse_policy="comparable",
        reviewed_at="2026-09-29",
        obtained_from="independent_pre_bill_official_source",
        allowed_routes=["health_insurance_treasury_support"],
        care_channel="nursing_hospital",
        price_year=2024,
        requires_applicability_note=True,
        limitation=("2024년 일부 요양병원 시범사업의 기본 일당 단가 후보. "
                    "전국 대상자 규모나 향후 연도 수가가 아니며, 180일 초과 의료최고도 환자의 "
                    "본인부담률 인상 구간에는 그대로 적용할 수 없음"),
    )
    rows = []
    # Insurer amount is derived from the published patient copay and copay
    # rate: copay / rate * (1-rate). This is not copied from 2200100's answer.
    for scenario, copay_won, copay_rate in (
        ("A", 9756, .40), ("B", 11478, .40), ("C", 17935, .50),
    ):
        rows.append(evidence_row(
            evidence_key=f"official:mohw:care-pilot:{scenario}:insurer-daily:2024",
            variable_key="insurer_daily_benefit",
            value=round(copay_won * (1 - copay_rate) / copay_rate),
            unit="KRW/case/day", variable_role="unit_rate",
            source_class="calculated_estimate", scenario_key=scenario,
            patient_daily_copay_won=copay_won,
            patient_copay_rate=copay_rate,
            derivation="본인부담금 × (1−본인부담률) ÷ 본인부담률",
            **common,
        ))
    for group, maximum in (("medical_high", 180), ("medical_critical", 300)):
        rows.append(evidence_row(
            evidence_key=f"official:mohw:care-pilot:{group}:max-days:2024",
            variable_key="covered_days_per_case_max", value=maximum,
            unit="day/case", variable_role="constraint", value_kind="upper_limit",
            source_class="official_standard", patient_group=group,
            limitation="시범사업의 최대 지원일수일 뿐 평균 입원일수 또는 실제 지급일수가 아님",
            **{key: value for key, value in common.items() if key != "limitation"},
        ))
    rows.append(evidence_row(
        evidence_key="official:nabo:health-insurance-effective-support:2020-2022",
        variable_key="government_support_rate", value=.141, unit="ratio",
        source_bill_no="official:nabo:health-insurance-outlook-2023",
        available_at="2023-10-10",
        source_ref="국회예산정책처, 2023~2032년 건강보험 재정전망(2023-10-10), 실 국고지원율 2020~2022년 평균 14.1%",
        source_url=NABO_OUTLOOK_URL,
        agency="보건복지부", policy_domain="건강보험 국고지원",
        scope="결산 기준 건강보험료 실제 수입 대비 국고지원금, 2020~2022년 평균",
        service_function="건강보험 지출 증가에 연동되는 국고지원율 시나리오",
        variable_role="historical_effective_rate", source_class="precedent_assumption",
        reuse_policy="comparable", reviewed_at="2026-09-29",
        obtained_from="independent_pre_bill_official_source",
        allowed_routes=["health_insurance_treasury_support"],
        requires_applicability_note=True, historical_period="2020~2022",
        limitation="과거 실효율로서 법정 20%나 향후 확정 지원율이 아님. 새 법안의 추계 기준연도에 맞는 최신 결산 확인 필요",
    ))
    return rows


def health_insurance_care_answer_rows() -> list[dict]:
    """Post-answer comparable observations; barred from bill 2200100 holdout."""
    common = dict(
        source_bill_no="2200100", available_at="2024-07-15",
        source_ref="의안 2200100 비용추계서(24C0462), 2024-07-15 회답",
        source_url=ANSWER_2200100_PATH,
        agency="보건복지부", policy_domain="건강보험 요양병원 간병급여",
        scope="전국 요양병원 의료최고도·의료고도 간병급여 가정",
        service_function="신규 간병급여로 인한 공단급여비 및 국고지원 증가",
        reuse_policy="comparable", reviewed_at="2026-09-29",
        obtained_from="reviewed_answer", requires_applicability_note=True,
        allowed_routes=["health_insurance_treasury_support"],
        care_channel="nursing_hospital",
        limitation="2200100 정답에서 추출. 해당 의안의 발의일 기준 평가에는 사용 금지; 다른 의안에서도 대상·연도·간병 기준 확인 필요",
    )
    rows = []
    # NABO table 7: the critical-care copay rises after 180 days, so the
    # first-180-day pilot rate cannot be reused for these bands.
    long_stay_prices = {
        "181-210": {"A": 13171, "B": 15495, "C": 15245},
        "211-240": {"A": 11488, "B": 13515, "C": 12151},
        "241-270": {"A": 9552, "B": 11238, "C": 8593},
        "271-300": {"A": 7327, "B": 8620, "C": 4502},
    }
    for band, scenario_prices in long_stay_prices.items():
        for scenario, price in scenario_prices.items():
            rows.append(evidence_row(
                evidence_key=f"2200100:{scenario}:critical:{band}:daily-benefit:2024",
                variable_key="insurer_daily_benefit", value=price,
                unit="KRW/case/day", variable_role="unit_rate",
                source_class="precedent_assumption", scenario_key=scenario,
                patient_group="medical_critical", stay_band=band, price_year=2024,
                source_ref=common["source_ref"] + ", PDF p.10, 표 7",
                **{key: value for key, value in common.items() if key != "source_ref"},
            ))
    rows.append(evidence_row(
        evidence_key="2200100:effective-government-support:2021-2023",
        variable_key="government_support_rate", value=.14, unit="ratio",
        variable_role="historical_effective_rate", historical_period="2021~2023",
        source_class="precedent_assumption",
        source_ref=common["source_ref"] + ", PDF p.11, 국고지원율 최근 3년 결산 평균",
        **{key: value for key, value in common.items() if key != "source_ref"},
    ))
    for key, value, note in (
        ("nursing_hospital_admission_rate", .042, "65세 이상 인구 대비 요양병원 입원 비율; 2020~2022 평균"),
        ("medical_critical_share", .019, "요양병원 입원환자 중 의료최고도 비율; 2022년 자료"),
        ("medical_high_share", .323, "요양병원 입원환자 중 의료고도 비율; 2022년 자료"),
    ):
        rows.append(evidence_row(
            evidence_key=f"2200100:{key}:historical",
            variable_key=key, value=value, unit="ratio", variable_role="historical_population_ratio",
            source_class="precedent_assumption", calculation_note=note,
            source_ref=common["source_ref"] + ", PDF p.7~8, 표 4",
            **{field: value for field, value in common.items() if field != "source_ref"},
        ))
    for group, stays in (
        ("medical_critical", {"0-180": 39, "181-210": 194, "211-240": 225,
                              "241-270": 256, "271-300": 285}),
        ("medical_high", {"0-180": 57}),
    ):
        for band, days in stays.items():
            rows.append(evidence_row(
                evidence_key=f"2200100:{group}:{band}:average-stay:2022",
                variable_key="covered_days_per_case", value=days,
                unit="day/case", variable_role="historical_average_duration",
                source_class="precedent_assumption", patient_group=group,
                stay_band=band, observation_year=2022,
                source_ref=common["source_ref"] + ", PDF p.10, 표 8",
                **{field: value for field, value in common.items() if field != "source_ref"},
            ))
    return rows


def care_reference_candidates(*, cutoff_date: str, target_bill_no: str,
                              db_path=None) -> list[dict]:
    """Return temporally eligible hints; never silently fill a target operand."""
    kwargs = dict(cutoff_date=cutoff_date, target_bill_no=target_bill_no,
                  evidence_mode="holdout")
    if db_path is not None:
        kwargs["db_path"] = db_path
    rows = find_variable_candidates(**kwargs)
    return [row for row in rows
            if "health_insurance_treasury_support" in row.get("allowed_routes", [])
            and row.get("variable_key") in {
                "insurer_daily_benefit", "covered_days_per_case_max",
                "government_support_rate", "covered_days_per_case",
                "nursing_hospital_admission_rate", "medical_critical_share",
                "medical_high_share",
            }]
