"""Reviewed, versioned ERCE evidence; never a universal price list.

New observations are appended by source/version, not overwritten to match a
target answer. Target-only quantities and budgets are not comparable prices.
"""
from __future__ import annotations

from typing import Any

from backend.erce.notification_evidence_registry import NOTIFICATION_BENCHMARKS
from backend.erce.diagnostic_evidence_registry import DIAGNOSTIC_BENCHMARKS
from backend.erce.project_plan_evidence_registry import PROJECT_PLAN_REFERENCES
from backend.erce.registration_fee_evidence_registry import (
    OFFICIAL_REGISTRATION_FEES, POST_ANSWER_REGISTRATION_OBSERVATIONS,
)
from backend.erce.service_industry_variable_registry import (
    SERVICE_INDUSTRY_VARIABLES, SERVICE_INDUSTRY_POST_ANSWER_VARIABLES,
)
from backend.erce.meeting_allowance_rules import MEETING_ALLOWANCE_RULES
from backend.research_service_unit_cost_registry import RESEARCH_SERVICE_BENCHMARKS


def evidence_row(*, evidence_key: str, variable_key: str, value: Any, unit: str,
                 source_bill_no: str, available_at: str, source_ref: str,
                 agency: str, policy_domain: str, scope: str, service_function: str,
                 variable_role: str, reuse_policy: str = "comparable",
                 source_class: str = "precedent_assumption", reviewed_at: str = "2026-09-27",
                 **context: Any) -> dict[str, Any]:
    return dict(evidence_key=evidence_key, variable_key=variable_key, value=value, unit=unit,
                source_bill_no=source_bill_no, available_at=available_at, source_ref=source_ref,
                agency=agency, policy_domain=policy_domain, scope=scope,
                service_function=service_function, variable_role=variable_role,
                reuse_policy=reuse_policy, source_class=source_class,
                review_status="reviewed", reviewed_at=reviewed_at, **context)


def reviewed_variable_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    notice = NOTIFICATION_BENCHMARKS[0]
    common = dict(source_bill_no=notice["source_bill_no"], available_at=notice["available_at"],
                  source_ref=notice["source_ref"], agency=notice["agency"], policy_domain=notice["policy_domain"],
                  scope=notice["target_population"], service_function=notice["service_function"],
                  scale_basis=notice["scale_basis"], obtained_from="reviewed_answer")
    for variable, data in notice["inputs"].items():
        rows.append(evidence_row(evidence_key=f"2212780:{variable}:2025", variable_key=variable,
            **data, **common, variable_role="unit_rate" if variable == "notice_unit_price" else "assumption",
            **({"value_years": list(notice["price_years"])} if variable == "notice_unit_price" else {})))
    rows.append(evidence_row(evidence_key="2212780:annual_case_count:2027-2031",
        variable_key="annual_case_count", value=[21701,25152,29151,33786,39158], unit="case/year",
        **common, variable_role="target_quantity", reuse_policy="target_only",
        value_years=list(notice["price_years"]),
        limitation="정답 표4의 전망 건수. 2023년 실적→15.9% 전망의 기준연도 불일치 미해결; 신규 법안에 그대로 전용 금지"))
    # Preserve the unresolved forecast discrepancy, rather than fitting an
    # artificial base year to the answer's annual case counts.

    diag = DIAGNOSTIC_BENCHMARKS[0]
    common = dict(source_bill_no=diag["source_bill_no"], available_at=diag["available_at"],
        source_ref=diag["source_ref"], agency=diag["agency"], policy_domain=diag["policy_domain"],
        scope="전국 6~11세 경계선지능 진단검사 지원", service_function=diag["service_function"],
        comparables=diag["comparables"], obtained_from="reviewed_answer")
    rows.append(evidence_row(evidence_key="2203298:test_unit_cost:2024", variable_key="test_unit_cost",
        **diag["inputs"]["test_unit_cost"], **common, variable_role="unit_rate", price_year=2024,
        price_policy="추계기간 동결 선례 가정; 공식 전국 검사요금 아님"))
    for variable, value, unit, role in (
        ("annual_recipients", [22035,20360,18659,17250,16067], "person/year", "target_quantity"),
        ("existing_annual_cost", 172000000, "KRW/year", "baseline_actual"),
    ):
        rows.append(evidence_row(evidence_key=f"2203298:{variable}:2026-2030", variable_key=variable,
            value=value, unit=unit, **common, variable_role=role, reuse_policy="target_only",
            source_class="target_current_actual" if variable == "existing_annual_cost" else "precedent_assumption",
            **({"value_years": [2026,2027,2028,2029,2030]} if variable == "annual_recipients" else {}),
            limitation="지원인원은 인구전망×1% 가정. 기존 사업비는 2024년 3개 교육청 예산 준용; 현재·타 지역 전체 실적 아님"))
    rows.append(evidence_row(evidence_key="2203298:coverage_rate:2024", variable_key="coverage_rate",
        value=.01, unit="ratio", **common, variable_role="assumption",
        limitation="법정·공식 고정비율 아님. 대상 연령·예산·실시 가능 규모가 유사할 때만 검토"))
    rows.append(evidence_row(evidence_key="2203298:first_occurrence_offset_years:2026",
        variable_key="first_occurrence_offset_years", value=1, unit="year", **common,
        variable_role="schedule", reuse_policy="target_only", value_years=[2026,2027,2028,2029,2030],
        limitation="2024년 실시 조사에서 3년 뒤인 2027년 재실시; 시작연도 2026년 기준"))

    plan = PROJECT_PLAN_REFERENCES[0]
    rows.append(evidence_row(evidence_key="2200093:annual_project_budget:2025-2029",
        variable_key="annual_project_budget", value=list(plan["annual_budget_won"]), unit="KRW/year",
        source_bill_no=plan["source_bill_no"], available_at=plan["available_at"], source_ref=plan["source_ref"],
        agency=plan["agency"], policy_domain=plan["policy_domain"], scope=plan["service_function"],
        service_function=plan["service_function"], variable_role="target_project_budget",
        reuse_policy="target_only", source_class="target_current_actual", value_years=list(plan["budget_years"]),
        includes_operations_maintenance=True, independently_verified=False,
        obtained_from="reviewed_answer", limitation=plan["limitations"]))

    fee = POST_ANSWER_REGISTRATION_OBSERVATIONS
    common = dict(source_bill_no=fee["source_bill_no"], available_at=fee["available_at"],
        source_ref=fee["source_ref"], agency="대법원", policy_domain="부동산등기",
        scope=fee["scope"], service_function=fee["service_function"], obtained_from="reviewed_answer",
        limitation=fee["accounting_caveat"])
    for variable, value, unit, role in (
        ("historical_annual_fee_revenues", fee["electronic_fee_revenues_won"], "KRW/year", "historical_actual"),
        ("other_channel_base_revenue", fee["nonelectronic_fee_revenues_won"][-1], "KRW/year", "baseline_actual"),
        ("other_channel_base_year", fee["historical_years"][-1], "year", "reference_year"),
        ("other_channel_growth_rate", fee["nonelectronic_growth_assumption"], "ratio/year", "assumption"),
        ("channel_shift_rate", fee["channel_shift_assumption"], "ratio", "assumption"),
    ):
        rows.append(evidence_row(evidence_key=f"2215482:{variable}:2026", variable_key=variable,
            value=value, unit=unit, **common, variable_role=role,
            observation_years=fee["historical_years"],
            reuse_note="같은 부동산등기 업무·전국·채널 범위에서만 검토. 전환율은 시나리오 가정"))
    for rate in OFFICIAL_REGISTRATION_FEES:
        rows.append(evidence_row(evidence_key=rate["key"], variable_key="old_fee", value=rate["value"],
            unit=rate["unit"], source_bill_no="official:" + rate["key"],
            available_at=rate["effective_from"], source_ref=rate["source_ref"], source_url=rate["source_url"],
            agency="대법원", policy_domain="부동산등기", scope=rate["service"] + "/" + rate["channel"],
            service_function=rate["service"], variable_role="unit_rate", reuse_policy="same_scope",
            source_class="official_standard", valid_from_year=2026, verified_at=rate["verified_at"],
            refresh_policy="시행본 변경 시 새 버전 추가. 과거 시행일 이전에는 자동 적용 금지"))

    for benchmark in RESEARCH_SERVICE_BENCHMARKS:
        bill = benchmark.source_bill_no or "2201446"
        variable = "plan_unit_cost" if benchmark.mechanism == "research_plan" else "survey_unit_cost"
        rows.append(evidence_row(evidence_key=benchmark.key + ":" + variable, variable_key=variable,
            value=benchmark.applied_unit_cost_won, unit="KRW/plan" if variable == "plan_unit_cost" else "KRW/survey",
            source_bill_no=bill, available_at=benchmark.available_at, source_ref=benchmark.source_ref,
            agency=benchmark.agency, policy_domain=benchmark.policy_domain or "교원",
            scope="중앙정부 연구용역", service_function=benchmark.mechanism, variable_role="unit_rate",
            sample_costs_won=list(benchmark.sample_costs_won), recurrence_interval_years=benchmark.recurrence_interval_years,
            obtained_from="reviewed_answer", limitation="주기·첫 실시연도는 새 법안에서 별도 판단. 전국 연구용역의 고정 단가 아님"))
    for registry, bill in ((SERVICE_INDUSTRY_VARIABLES, "2214690"), (SERVICE_INDUSTRY_POST_ANSWER_VARIABLES, "2216475")):
        for variable, data in registry.items():
            extra = {k: v for k, v in data.items() if k not in {"value", "unit", "source_bill_no", "available_at", "source_ref", "scope", "service_function", "source_class"}}
            rows.append(evidence_row(evidence_key=f"{bill}:{variable}:reviewed", variable_key=variable,
                value=data["value"], unit=data["unit"], source_bill_no=bill, available_at=data["available_at"],
                source_ref=data["source_ref"], agency="기획재정부", policy_domain="서비스산업",
                scope=data["scope"], service_function=data["service_function"], variable_role="unit_rate" if variable == "plan_unit_cost" else "assumption_bundle",
                **extra, **({"value_years": [2026,2027,2028,2029,2030]} if bill == "2216475" else {})))
    for rule in MEETING_ALLOWANCE_RULES:
        rows.append(evidence_row(evidence_key=rule["key"], variable_key="meeting_unit_price_limit",
            value=rule["base_limit_won"], unit=rule["unit"], source_bill_no="official:" + rule["key"],
            available_at=rule["available_at"], source_ref=rule["source_ref"], source_url=rule["source_url"],
            agency="중앙정부", policy_domain="위원회", scope=rule["scope"], service_function="위원회 참석비 지급 한도",
            variable_role="constraint", source_class="official_standard", reuse_policy="comparable",
            value_kind="upper_limit", valid_from_year=2026, valid_to_year=2026,
            additional_limit_won=rule["additional_limit_won"], conditions=rule["selection_note"],
            refresh_policy="다음 연도 집행지침 원문 확인 후 새 버전 추가"))
    return rows


def burial_comparable_rows() -> list[dict[str, Any]]:
    """Read from bill 2212347 BEFORE opening the target bill 2211932 answer."""
    common = dict(source_bill_no="2212347", available_at="2025-09-04",
        source_ref="의안 2212347, 25D4547, 비용추계서 PDF p.3~6",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2212347/cost_estimate.pdf",
        agency="국가보훈부", policy_domain="국립묘지",
        scope="특수임무공로자 국립호국원 안장; 기존 안장자격 보유자 제외",
        service_function="국립호국원 안장대상 확대", value_years=[2026,2027,2028,2029,2030],
        obtained_from="non_target_source", reuse_policy="comparable",
        limitation="기존 사망자 분할 안장 및 예상 신규 사망자를 포함한 선례 가정. 새 법안의 소급 범위·기존 자격을 별도 확인")
    deaths = [352,351,348,348,348]
    return [
        evidence_row(evidence_key="2212347:burial_quantity:2026-2030", variable_key="quantity",
            value=[count * .458 for count in deaths], unit="person/year", **common,
            variable_role="target_quantity_comparable", annual_eligible_deceased=deaths,
            requires_retroactive_application=True,
            existing_deceased_total=1597, existing_deceased_allocation=[320,320,319,319,319],
            projected_new_deaths=[32,31,29,29,29], interment_rate=.458,
            calculation_note="각 연도 기존 사망자 분할분+신규 사망자에 최근 5년 호국원 안장률45.8% 적용; 기대인원 소수 보존"),
        evidence_row(evidence_key="2212347:new_death_burial_quantity:2026-2030", variable_key="quantity",
            value=[count * .458 for count in [32,31,29,29,29]], unit="person/year", **common,
            variable_role="target_quantity_comparable", projected_new_deaths=[32,31,29,29,29],
            interment_rate=.458, excludes_pre_effective_deaths=True,
            calculation_note="같은 선례의 신규 사망자만 분리해 안장률 적용. 다른 집단 인원이나 현재 실적에 무조건 전용 금지"),
        evidence_row(evidence_key="2212347:burial_supplies_unit_cost:2026-2030", variable_key="unit_cost",
            value=[140000 * 1.02 ** n for n in range(1,6)], unit="KRW/person", **common,
            allowed_routes=["burial_supplies","quantity_unit"],
            variable_role="unit_rate", base_price_year=2025, base_price_won=140000,
            price_components={"유골함":90000,"봉안명패":50000}, annual_growth_assumption=.02,
            price_status="보훈부 제공액을 인용한 선례. 공식 현행 웹단가 독립 확인 아님"),
        evidence_row(evidence_key="2212347:burial_plot_unit_cost:2026-2030", variable_key="unit_cost",
            value=[2572000 * 1.0479 ** n for n in range(1,6)], unit="KRW/person", **common,
            allowed_routes=["burial_plot_construction","quantity_unit"],
            variable_role="unit_rate", base_price_year=2025, base_price_won=2572000,
            construction_scale={"capacity":50000,"area_m2":957570,"total_budget_million":128607},
            annual_growth_assumption=.0479,
            price_status="국립연천현충원 사업비/수용규모 준용 선례. 동일 공사·전국 고정 단가 아님"),
    ]
