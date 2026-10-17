"""Reviewed historical operands and opt-in lower calculations for support costs.

These are answer-derived development references, not independently verified
current official statistics. Target projections cannot be reused as prices.
"""
from math import isfinite, prod

from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILES = {
    "regional_advocacy_case_scaled_committee": ("committee_components", {}),
    "low_income_couple_pension": ("transfer_recipient_delta", {}),
    "phased_couple_pension_types": ("transfer_population_amount_delta", {}),
    "published_pension_cost_replay": ("direct_annual_amount", {}),
    "phased_couple_pension": ("transfer_population_amount_delta", {}),
    "median_income_pension_groups": ("transfer_population_amount_delta", {}),
    "basic_pension_staged_increase": ("transfer_recipient_delta", {}),
    "disability_eligibility_expansion": ("transfer_recipient", {}),
    "disability_couple_reduction_recovery": ("transfer_recipient_delta", {}),
    "child_allowance_birth_order_weighted": ("transfer_population_amount_delta", {}),
    "child_allowance_under18_indexed_floor": ("transfer_population_amount_delta", {}),
    "parent_benefit_age_indexed_floor": ("transfer_recipient_delta", {}),
    "child_allowance_indexed_population": ("transfer_population_amount_delta", {
        "under19_population": "person", "under8_population": "person",
        "child_payment_rate": "ratio", "index_base_monthly_amount": "KRW/person/month",
        "child_cpi_rates": "ratio/year",
    }),
    "child_allowance_net_population": ("transfer_population_amount_delta", {
        "under18_population": "person", "under8_population": "person",
        "age0_population": "person", "age1_population": "person", "child_payment_rate": "ratio",
    }),
    "center_annual_designation": ("quantity_unit", {
        "initial_supported_centers": "center", "annual_new_centers": "center/year",
        "center_annual_unit": "KRW/center/year", "government_share": "ratio",
    }),
    "student_income_interest": ("transfer_recipient", {
        "eligible_loan_students": "person", "average_loan_balance": "KRW/person",
        "student_loan_rate": "ratio",
    }),
    "student_tuition_interest": ("transfer_recipient", {
        "age_population": "person", "support_population": "person",
        "reference_age_population": "person", "college_enrollment_proxy": "ratio",
        "loan_use_ratio": "ratio", "tuition_loan_balance": "KRW/person",
        "student_loan_rate": "ratio",
    }),
    "graduate_fee_compensation": ("transfer_recipient_subsidy", {
        "fee_paying_entrants": "person", "admission_fee": "KRW/person",
        "compensation_share": "ratio",
    }),
    "association_operating_support": ("transfer_subsidy_rate", {
        "association_count": "organization", "association_annual_unit": "KRW/organization/year",
        "government_share": "ratio",
    }),
}


def prepare_support_operands(payload):
    """Derive top-level slots only after an explicit applicability confirmation.

    No search/selection or numeric fallback occurs here. Partial operands remain
    missing; confirmed upper slots keep their normal evidence priority.
    """
    profile = payload.get("support_derivation")
    if profile == "protected_child_insurance_population_share":
        from backend.erce.protected_child_insurance_evidence import prepare_protected_child_insurance
        return prepare_protected_child_insurance(payload)
    if profile == "prefunded_annual_survey_delta":
        from backend.erce.prefunded_annual_survey_evidence import prepare_prefunded_survey
        return prepare_prefunded_survey(payload)
    if profile == "regional_resident_benefit_trend":
        from backend.erce.regional_resident_benefit_evidence import prepare_regional_resident_benefit
        return prepare_regional_resident_benefit(payload)
    if profile == "facility_survey_scope_expansion_delta":
        from backend.erce.facility_survey_expansion_evidence import prepare_facility_survey_expansion
        return prepare_facility_survey_expansion(payload)
    if profile == "education_training_package_freeze":
        from backend.erce.education_training_budget_evidence import prepare_education_training_budget
        return prepare_education_training_budget(payload)
    if profile == "child_awareness_education_budget":
        from backend.erce.child_awareness_budget_evidence import prepare_child_awareness_budget
        return prepare_child_awareness_budget(payload)
    if profile == "asset_management_annual_budget_proxy":
        from backend.erce.asset_management_budget_evidence import prepare_asset_management_budget
        return prepare_asset_management_budget(payload)
    if profile == "qualification_exam_stock_flow":
        from backend.erce.qualification_exam_evidence import prepare_qualification_exam
        return prepare_qualification_exam(payload)
    if profile == "survey_annualization_delta":
        from backend.erce.survey_annualization_evidence import prepare_survey_annualization
        return prepare_survey_annualization(payload)
    if profile == "appointed_ombudsman_secretariat":
        from backend.erce.ombudsman_evidence import prepare_ombudsman
        return prepare_ombudsman(payload)
    if profile == "special_classroom_expansion":
        from backend.erce.special_classroom_evidence import prepare_special_classrooms
        return prepare_special_classrooms(payload)
    if profile == "employment_levy_sector_delta":
        from backend.erce.levy_sector_evidence import prepare_levy_sectors
        return prepare_levy_sectors(payload)
    if profile == "enterprise_assistant_annual_support":
        from backend.erce.enterprise_assistant_evidence import prepare_enterprise_assistant
        return prepare_enterprise_assistant(payload)
    if profile == "hospital_interpreter_increment":
        from backend.erce.hospital_interpreter_increment import prepare_interpreter_increment
        return prepare_interpreter_increment(payload)
    if profile == "medical_standard_workplace_reference":
        from backend.erce.medical_standard_workplace import prepare_medical_workplace
        return prepare_medical_workplace(payload)
    if profile == "standard_workplace_subsidy_expansion":
        from backend.erce.standard_workplace_evidence import prepare_standard_workplace
        return prepare_standard_workplace(payload)
    if profile == "government_employment_levy_delta":
        from backend.erce.government_employment_levy import prepare_government_levy
        return prepare_government_levy(payload)
    if profile == "disabled_worker_minimum_wage_gap":
        from backend.erce.disabled_worker_wage_evidence import prepare_disabled_worker_gap
        return prepare_disabled_worker_gap(payload)
    if profile == "disabled_child_allowance_mandatory_delta":
        from backend.erce.disabled_child_allowance_evidence import prepare_disabled_child_allowance
        return prepare_disabled_child_allowance(payload)
    if profile == "mobile_identity_lifecycle":
        from backend.erce.mobile_identity_evidence import prepare_mobile_identity
        return prepare_mobile_identity(payload)
    if profile == "disabled_urban_rail_compensation":
        from backend.erce.rail_free_transport_evidence import prepare_rail_compensation
        return prepare_rail_compensation(payload)
    if profile == "hospital_communication_support_package":
        from backend.erce.medical_communication_evidence import prepare_medical_communication
        return prepare_medical_communication(payload)
    if profile == "elderly_public_activity_minimum_wage_delta":
        from backend.erce.elderly_public_activity_evidence import prepare_elderly_public_activity
        return prepare_elderly_public_activity(payload)
    if profile == "foreign_child_parent_fee":
        from backend.erce.foreign_childcare_evidence import prepare_foreign_childcare
        return prepare_foreign_childcare(payload)
    if profile == "social_security_committee_expansion":
        from backend.erce.central_social_committee_evidence import prepare_social_security_expansion
        return prepare_social_security_expansion(payload)
    if not profile:
        return payload
    if profile=="child_support_income_age_standard":
        from backend.erce.child_support_amount_basis import prepare_standard_amount
        return prepare_standard_amount(payload)
    if profile in {"child_support_advance_expense","child_support_system_upgrade"}:
        from backend.erce.child_support_advance_evidence import prepare_child_support
        return prepare_child_support(payload)
    if profile == "central_social_policy_committee":
        from backend.erce.central_social_committee_evidence import prepare_central_social_committee
        return prepare_central_social_committee(payload)
    if profile in {"grandparent_care_age_net", "grandparent_care_allowance_parallel"}:
        from backend.erce.grandparent_care_evidence import prepare_grandparent_care
        return prepare_grandparent_care(payload)
    if profile == "owner_energy_repair_grouped":
        from backend.erce.owner_energy_repair_evidence import prepare_energy_repair
        return prepare_energy_repair(payload)
    if profile == "housing_moving_brokerage_bundle":
        from backend.erce.housing_moving_evidence import prepare_housing_moving
        return prepare_housing_moving(payload)
    if profile == "housing_management_fee":
        from backend.erce.housing_management_evidence import prepare_housing_management
        return prepare_housing_management(payload)
    if profile == "jobseeker_cash_duration_extension":
        from backend.erce.jobseeker_duration_evidence import prepare_jobseeker_duration
        return prepare_jobseeker_duration(payload)
    if profile == "jobseeker_livelihood_previous_year":
        from backend.erce.jobseeker_livelihood_evidence import prepare_jobseeker
        return prepare_jobseeker(payload)
    if profile == "single_parent_survey_children":
        from backend.erce.single_parent_survey_evidence import prepare_single_parent
        return prepare_single_parent(payload)
    if profile == "child_allowance_reviewed_cpi":
        from backend.erce.child_allowance_reviewed_cpi import prepare_reviewed_child_cpi
        return prepare_reviewed_child_cpi(payload)
    if profile == "parent_benefit_voucher_annual_increment":
        from backend.erce.parent_voucher_indexed_evidence import prepare_parent_voucher
        return prepare_parent_voucher(payload)
    if profile == "submitted_elder_protection_plan":
        from backend.erce.submitted_support_plan import prepare_submitted_plan
        return prepare_submitted_plan(payload)
    if profile == "regional_advocacy_case_scaled_committee":
        from backend.erce.regional_advocacy_committee import prepare_regional_advocacy_committee
        return prepare_regional_advocacy_committee(payload)
    if profile == "low_income_couple_pension":
        from backend.erce.low_income_couple_pension import prepare_low_income_couple
        return prepare_low_income_couple(payload)
    if profile == "phased_couple_pension_types":
        from backend.erce.phased_pension_types import prepare_phased_pension_types
        return prepare_phased_pension_types(payload)
    if profile == "published_pension_cost_replay":
        from backend.erce.published_pension_replay import prepare_published_pension_replay
        return prepare_published_pension_replay(payload)
    if profile == "phased_couple_pension":
        from backend.erce.phased_couple_pension import prepare_phased_couple
        return prepare_phased_couple(payload)
    if profile == "median_income_pension_groups":
        from backend.erce.median_pension_evidence import prepare_median_pension
        return prepare_median_pension(payload)
    if profile == "basic_pension_staged_increase":
        from backend.erce.basic_pension_staged_evidence import prepare_basic_pension_staged
        return prepare_basic_pension_staged(payload)
    if profile == "disability_eligibility_expansion":
        from backend.erce.disability_expansion_evidence import prepare_disability_expansion
        return prepare_disability_expansion(payload)
    if profile == "disability_couple_reduction_recovery":
        from backend.erce.disability_couple_evidence import prepare_disability_couple_operands
        return prepare_disability_couple_operands(payload)
    if profile == "child_allowance_birth_order_weighted":
        from backend.erce.child_allowance_birth_order_evidence import prepare_birth_order_operands
        return prepare_birth_order_operands(payload)
    if profile in {"child_allowance_under18_indexed_floor", "parent_benefit_age_indexed_floor"}:
        from backend.erce.family_benefit_indexed_evidence import prepare_family_indexed_operands
        return prepare_family_indexed_operands(payload)
    if profile not in PROFILES or not str(payload.get("support_derivation_note") or "").strip():
        raise ValueError("support derivation needs a known profile and applicability note")
    route, units = PROFILES[profile]
    if payload.get("route_key") != route:
        raise ValueError("support derivation route mismatch")
    if profile == "child_allowance_indexed_population":
        if payload.get("child_allowance_scenario") != "all_under19_indexed" or payload.get("parent_benefit_unchanged") is not True:
            raise ValueError("indexed child allowance needs under19 scenario and unchanged parent benefit")
        if not str(payload.get("child_allowance_scope_note") or "").strip():
            raise ValueError("indexed child allowance needs applicability confirmation")
        base = payload.get("child_index_base_year")
        start = payload.get("start_year")
        if isinstance(base, bool) or not isinstance(base, int) or (start is not None and start != base + 1):
            raise ValueError("indexed child allowance start must follow confirmed base year")
        if start is not None and not str(payload.get("estimation_start_note") or "").strip():
            raise ValueError("estimation start needs a separate basis, not just the effective year")
        top, _ = resolve_formula_variables(("benefit_per_recipient", "existing_benefit_per_recipient", "payments_per_year"),
            target_explicit=payload.get("explicit_inputs"), target_current_actual=payload.get("actual_inputs"),
            official_standard=payload.get("official_inputs"), calculated_estimate=payload.get("calculated_inputs"),
            precedent_assumption=selected_precedent_inputs(payload))
        for name, row in top.items():
            expected = "month/year" if name == "payments_per_year" else "KRW/person/month"
            if row.unit != expected or not row.source_ref:
                raise ValueError(f"{name}: expected sourced {expected}")
    if profile == "child_allowance_net_population":
        if payload.get("child_allowance_scenario") != "under2_parent_only" or payload.get("parent_benefit_unchanged") is not True:
            raise ValueError("child allowance net scenario needs confirmed under2 exclusion and unchanged parent benefit")
        if not str(payload.get("child_allowance_scope_note") or "").strip():
            raise ValueError("child allowance net scenario needs applicability confirmation")
        if payload.get("start_year") is not None and not str(payload.get("estimation_start_note") or "").strip():
            raise ValueError("estimation start needs a separate basis, not just the effective year")
        top, _ = resolve_formula_variables(("benefit_per_recipient","existing_benefit_per_recipient","payments_per_year"),
            target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
            official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
            precedent_assumption=selected_precedent_inputs(payload))
        for name,row in top.items():
            expected="month/year" if name=="payments_per_year" else "KRW/person/month"
            if row.unit!=expected or not row.source_ref:
                raise ValueError(f"{name}: expected sourced {expected}")
    if profile == "student_income_interest":
        if not str(payload.get("student_interest_scope_note") or "").strip():
            raise ValueError("student interest needs incremental population and public support scope confirmation")
        if payload.get("start_year") is not None and not str(payload.get("estimation_start_note") or "").strip():
            raise ValueError("estimation start needs a separate basis, not just the effective year")
    if profile == "center_annual_designation":
        if not str(payload.get("center_operation_scope_note") or "").strip():
            raise ValueError("center operation needs continued operation, full-year cost and no-double-count confirmation")
        if payload.get("start_year") is not None and not str(payload.get("estimation_start_note") or "").strip():
            raise ValueError("estimation start needs a separate basis, not just the effective year")
    if any(key in layer for layer in (payload.get("explicit_inputs") or {},
            payload.get("actual_inputs") or {}, payload.get("official_inputs") or {},
            payload.get("calculated_inputs") or {}, payload.get("selected_variable_inputs") or {}) for key in
            (("growth_rate", "growth_rates_by_year", "participation_rate")
             if profile in {"child_allowance_net_population", "child_allowance_indexed_population"} else
             ("growth_rate", "growth_rates_by_year", "payments_per_year", "participation_rate"))):
        raise ValueError("support derivation already represents annual costs; duplicate adjustment forbidden")
    resolved, missing = resolve_formula_variables(tuple(units),
        target_explicit=payload.get("explicit_inputs"), target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"), calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    years = int(payload.get("years") or 5)
    data = {}
    for key, row in resolved.items():
        if row.unit != units[key] or not row.source_ref:
            raise ValueError(f"{key}: expected sourced {units[key]}")
        raw = row.value if isinstance(row.value, (list, tuple)) else [row.value] * years
        if len(raw) != years or any(isinstance(v, bool) or not isinstance(v, (int, float))
                or not isfinite(v) or (v <= -1 if key == "child_cpi_rates" else v < 0)
                or (units[key] == "ratio" and v > 1) for v in raw):
            raise ValueError(f"invalid support operand: {key}")
        data[key] = list(raw)
    calculated = dict(payload.get("calculated_inputs") or {})
    trace = []

    def derive(key, dependencies, unit, expression, calculate):
        if not all(dep in data for dep in dependencies):
            return
        values = [calculate(i) for i in range(years)]
        refs = "; ".join(dict.fromkeys(resolved[dep].source_ref for dep in dependencies))
        upper, _ = resolve_formula_variables((key,),target_explicit=payload.get("explicit_inputs"),
            target_current_actual=payload.get("actual_inputs"),official_standard=payload.get("official_inputs"),
            calculated_estimate=calculated)
        if key not in upper:
            calculated[key] = dict(value=values, unit=unit, source_ref=refs, is_assumption=True)
        trace.append(dict(variable_key=key, expression=expression,
                          dependencies=list(dependencies), values=values, unit=unit,
                          source_ref=refs, applied=key not in upper,
                          applicability_note=payload["support_derivation_note"]))

    if profile == "child_allowance_indexed_population":
        if all(k in data for k in ("under19_population", "under8_population")) and any(
                old > new for old, new in zip(data["under8_population"], data["under19_population"])):
            raise ValueError("inconsistent child age cohorts")
        if "index_base_monthly_amount" in data and len(set(data["index_base_monthly_amount"])) != 1:
            raise ValueError("index base must be one fixed amount, not indexed annual amounts")
        derive("new_recipient_count", ("under19_population", "child_payment_rate"), "person",
            "19세미만 인구×동일 아동수당 지급률", lambda i: data["under19_population"][i]*data["child_payment_rate"][i])
        derive("existing_recipient_count", ("under8_population", "child_payment_rate"), "person",
            "현행8세미만 인구×동일 아동수당 지급률", lambda i: data["under8_population"][i]*data["child_payment_rate"][i])
        derive("benefit_per_recipient", ("index_base_monthly_amount", "child_cpi_rates"), "KRW/person/month",
            "확인한 기준연도 월액×기준연도 다음해부터 해당연도까지 ∏(1+물가변동률); 표시단위 중간 반올림 없음",
            lambda i: data["index_base_monthly_amount"][0]*prod(1+v for v in data["child_cpi_rates"][:i+1]))
    elif profile == "child_allowance_net_population":
        if all(k in data for k in ("under18_population","under8_population","age0_population","age1_population")):
            for i in range(years):
                if not data["age0_population"][i]+data["age1_population"][i] <= data["under8_population"][i] <= data["under18_population"][i]:
                    raise ValueError("inconsistent child age cohorts")
        derive("new_recipient_count", ("under18_population","age0_population","age1_population","child_payment_rate"), "person",
            "(18세미만 인구−0세−1세)×확인한 아동수당 지급률; 부모급여 유지 가정",
            lambda i: (data["under18_population"][i]-data["age0_population"][i]-data["age1_population"][i])*data["child_payment_rate"][i])
        derive("existing_recipient_count", ("under8_population","child_payment_rate"), "person",
            "현행8세미만 인구×동일 아동수당 지급률",
            lambda i: data["under8_population"][i]*data["child_payment_rate"][i])
    elif profile == "center_annual_designation":
        for key in ("initial_supported_centers", "annual_new_centers"):
            if key in data and any(not float(value).is_integer() for value in data[key]):
                raise ValueError(f"{key}: center counts must be integers")
        if "initial_supported_centers" in data and len(set(data["initial_supported_centers"])) != 1:
            raise ValueError("initial_supported_centers is one opening stock, not an annual series")
        derive("quantity", ("initial_supported_centers", "annual_new_centers"), "center",
               "지원 시작시 순증 지원대상센터 수 + 해당 연도까지 신규 지정센터 누계(계속 운영 가정)",
               lambda i: data["initial_supported_centers"][0] + sum(data["annual_new_centers"][:i+1]))
        derive("unit_cost", ("center_annual_unit", "government_share"), "KRW/center/year",
               "센터당 연간 패키지 지원단가 × 선택한 정부 분담률(패키지 인건비 중복 가산 금지)",
               lambda i: data["center_annual_unit"][i] * data["government_share"][i])
    elif profile == "student_income_interest":
        derive("recipient_count", ("eligible_loan_students",), "person",
               "지역·소득구간별 신규 면제 ICL 이용자 수(기존 면제 제외)",
               lambda i: data["eligible_loan_students"][i])
        derive("benefit_per_recipient", ("average_loan_balance", "student_loan_rate"), "KRW/person/year",
               "같은 지역·소득구간 이용자의 평균 대출잔액 × 학생 대출금리",
               lambda i: data["average_loan_balance"][i] * data["student_loan_rate"][i])
    elif profile == "student_tuition_interest":
        if "reference_age_population" in data and any(v <= 0 for v in data["reference_age_population"]):
            raise ValueError("reference_age_population must be positive")
        if all(k in data for k in ("support_population", "reference_age_population")) and any(
                a > b for a, b in zip(data["support_population"], data["reference_age_population"])):
            raise ValueError("support population exceeds reference population")
        derive("recipient_count", tuple(units)[:5], "person",
            "연령별 인구 × 자립지원 인원/기준연령 인구 × 대학 재적 대리비율 × 대출이용비율",
            lambda i: data["age_population"][i] * data["support_population"][i]
            / data["reference_age_population"][i] * data["college_enrollment_proxy"][i]
            * data["loan_use_ratio"][i])
        derive("benefit_per_recipient", ("tuition_loan_balance", "student_loan_rate"), "KRW/person/year",
               "1인당 등록금 대출잔액 × 학생 대출금리",
               lambda i: data["tuition_loan_balance"][i] * data["student_loan_rate"][i])
    elif profile == "graduate_fee_compensation":
        derive("recipient_count", ("fee_paying_entrants",), "person", "입학금 납부 신입생 수",
               lambda i: data["fee_paying_entrants"][i])
        derive("benefit_per_recipient", ("admission_fee",), "KRW/person", "유형별 기준년도 입학금 동결",
               lambda i: data["admission_fee"][i])
        derive("subsidy_rate", ("compensation_share",), "ratio", "확인한 정부 보전 시나리오 비율",
               lambda i: data["compensation_share"][i])
    else:
        derive("project_cost", ("association_count", "association_annual_unit"), "KRW/year",
               "지원 단체 수 × 단체당 연간 운영 지원단가",
               lambda i: data["association_count"][i] * data["association_annual_unit"][i])
        derive("subsidy_rate", ("government_share",), "ratio", "선택한 국비 또는 국비·지방비 합산 분담률",
               lambda i: data["government_share"][i])
    dependencies = {
        "child_allowance_indexed_population": {
            "new_recipient_count": ("under19_population", "child_payment_rate"),
            "existing_recipient_count": ("under8_population", "child_payment_rate"),
            "benefit_per_recipient": ("index_base_monthly_amount", "child_cpi_rates")},
        "child_allowance_net_population": {
            "new_recipient_count": ("under18_population","age0_population","age1_population","child_payment_rate"),
            "existing_recipient_count": ("under8_population","child_payment_rate")},
        "center_annual_designation": {"quantity": ("initial_supported_centers", "annual_new_centers"),
            "unit_cost": ("center_annual_unit", "government_share")},
        "student_income_interest": {"recipient_count": ("eligible_loan_students",),
            "benefit_per_recipient": ("average_loan_balance", "student_loan_rate")},
        "student_tuition_interest": {"recipient_count": tuple(units)[:5],
            "benefit_per_recipient": ("tuition_loan_balance", "student_loan_rate")},
        "graduate_fee_compensation": {"recipient_count": ("fee_paying_entrants",),
            "benefit_per_recipient": ("admission_fee",), "subsidy_rate": ("compensation_share",)},
        "association_operating_support": {"project_cost": ("association_count", "association_annual_unit"),
            "subsidy_rate": ("government_share",)},
    }[profile]
    _, top_missing = resolve_formula_variables(tuple(dependencies),
        target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=calculated,
        precedent_assumption=selected_precedent_inputs(payload))
    needed = {key for top in top_missing for key in dependencies[top]}
    return {**payload, "calculated_inputs": calculated, "support_derivation_trace": trace,
            "support_missing_operands": [key for key in missing if key in needed]}


def support_operand_rows():
    rows = []

    def add(bill, date, profile, key, value, unit, *, suffix="reference", target=False, **metadata):
        rows.append(evidence_row(evidence_key=f"{bill}:{key}:{suffix}", variable_key=key,
            value=value, unit=unit, source_bill_no=bill, available_at=date,
            source_ref=f"의안{bill} 비용추계서 {metadata.pop('pages', '')}",
            agency="국회예산정책처", policy_domain=profile, scope=profile,
            service_function=profile, variable_role="target_quantity" if target else "assumption",
            reuse_policy="target_only" if target else "comparable", reviewed_at=metadata.pop("reviewed_at", "2026-10-03"),
            obtained_from="reviewed_answer", requires_applicability_note=True,
            allowed_routes=[PROFILES[profile][0]], support_derivation=profile,
            independently_verified=False, **metadata))

    b, d, p = "2209405", "2025-06-30", "student_tuition_interest"
    add(b,d,p,"age_population",[7282049,7060010,6887220,6738928,6573015],"person",
        target=True,value_years=list(range(2026,2031)),pages="PDF7쪽 표5",
        limitation="2023년12월 통계청 중위전망을 정답에서 확인한 17~29세 인구. 최신 API 검증 아님")
    for key,value,unit in [("support_population",11173,"person"),
            ("reference_age_population",7917654,"person"),
            ("college_enrollment_proxy",.292,"ratio"),("loan_use_ratio",.161,"ratio")]:
        add(b,d,p,key,value,unit,pages="PDF6~7쪽 표3~5", observation_year=2024 if unit=="person" else 2023,
            limitation="자립지원대상자·17~29세 집단의 비율 추정용. 대학 재적은 중퇴·휴학 포함 대리 가정; 일반 학생에 전용 금지")
    add(b,d,p,"tuition_loan_balance",[4225000,4310000,4396000,4484000,4574000],"KRW/person",
        value_years=list(range(2026,2031)),pages="PDF7쪽 표6",
        limitation="2024년 ICL 등록금 평균잔액에 NABO 물가전망을 적용한 선례. 생활비·일반상환대출·최신 실제잔액 아님")
    add(b,d,p,"student_loan_rate",.017,"ratio",pages="PDF8쪽",
        limitation="학생 ICL 금리의 추계기간 동결 가정. 조달금리 또는 미래 확정금리 아님")

    b,d,p = "2215813","2026-02-02","graduate_fee_compensation"
    groups = {
        "public": ([34038,34698,35378,36081,36807],184548,1),
        "private_general": ([104106,110173,116633,123513,130842],805409,.20),
        "private_graduate": ([3831,4006,4190,4382,4583],630611,.33),
    }
    for group,(counts,fee,share) in groups.items():
        for key,value,unit in [("fee_paying_entrants",counts,"person"),
                               ("admission_fee",fee,"KRW/person"),("compensation_share",share,"ratio")]:
            add(b,d,p,key,value,unit,suffix=group,target=key=="fee_paying_entrants",
                university_kind=group,pages="PDF5쪽 표2~3",
                **({"value_years":list(range(2026,2031))} if key=="fee_paying_entrants" else {}),
                price_year=2025,
                limitation="입학금0원 대학원 제외. 입학금은2025년 평균 동결. 정부 보전과20%·33% 준용은 정책 가정이지 대학원 법정 지원율 아님")

    b,d,p = "2214218","2025-12-03","association_operating_support"
    add(b,d,p,"association_count",29,"organization",target=True,pages="PDF5쪽 표3",
        limitation="시도 농업17+어업12개. 시군구 하부단체 제외; 타 단체 수로 재사용 금지")
    add(b,d,p,"association_annual_unit",26000000,"KRW/organization/year",pages="PDF12쪽 참고3",
        price_year=2023,limitation="4-H도본부 교육지원234백만원/9개소 준용. 법정 운영단가 아님; 회원수·사업기능·규모 비교 및 가격 동결 확인 필요")
    for scope,share in [("combined",1),("national",.5),("local",.5)]:
        add(b,d,p,"government_share",share,"ratio",suffix=scope,pages="PDF5쪽 표4",
            support_fiscal_scope=scope,limitation="국비·지방비50:50 선례 가정. 합산과 분할 결과를 더해 중복 계산 금지")
    b,d,p = "2219149","2026-08-20","student_income_interest"
    for band,counts,balances,use in [
        ("7",[66422,66780,67140,67502,67866],[4039000,4118000,4200000,4285000,4370000],.1063),
        ("8",[73803,74201,74601,75003,75407],[4565000,4655000,4748000,4843000,4940000],.1181),
    ]:
        for key,value,unit in [("eligible_loan_students",counts,"person"),
                ("average_loan_balance",balances,"KRW/person"),("income_band_loan_use_ratio",use,"ratio")]:
            add(b,d,p,key,value,unit,suffix=f"capital_band{band}",target=key=="eligible_loan_students",
                loan_income_band=band,student_loan_region="capital",pages="PDF5~6쪽 표2~3",
                **({"value_years":list(range(2027,2032))} if isinstance(value,list) else {}),
                observation_year=2026,
                limitation="수도권 재학생 해당 소득구간의 ICL, 2026년1학기 실적 준용. 잔액은 NABO물가 전망. 이용률 분모 원자료는 미확인; 자립지원·전국·다른 소득구간에 자동 전용 금지")
    add(b,d,p,"student_loan_rate",.017,"ratio",pages="PDF6쪽",
        limitation="추계기간 학생 ICL금리1.7% 동결 선례 가정. 재단 조달금리·미래 확정금리·최신 공식 API 검증 아님")
    add(b,d,p,"capital_student_growth",.0054,"ratio/year",pages="PDF5쪽",
        student_loan_region="capital",observation_year=2026,
        limitation="최근3년 수도권 재학생 증감률 준용 가정. 기준인구 원자료 없이 인원을 역산하지 않으며 일반 인구성장률 아님")
    add(b,d,p,"estimate_start_year",2027,"year",target=True,pages="PDF5쪽",
        effective_date="2026-11-20",timing_basis="다음 완전 회계연도부터 추계하는 해당 선례의 가정",
        limitation="해당 의안의 추계기간2027~2031년. 11월 시행이면 무조건 다음 해로 잡는 범용 규칙 아님")
    b,d,p = "2201262","2026-10-04","center_annual_designation"
    for kind,unit in [("agriculture",500000000),("fisheries",600000000)]:
        for key,value,unit_name in [("initial_supported_centers",0,"center"),
                ("annual_new_centers",1,"center/year"),("center_annual_unit",unit,"KRW/center/year")]:
            add(b,d,p,key,value,unit_name,suffix=kind,target=key=="initial_supported_centers",
                center_kind=kind,pages="24B0644 PDF4쪽 표2 및 PDF7쪽", reviewed_at="2026-10-04",
                source_reply_date="2024-06-14",price_year=2024,
                source_chronology_note="회답일이 발의일2024-07-01보다 앞섬. 사전 의뢰·공개시점 미확인이라 현재 확인일을 available_at으로 사용",
                **({"includes_labor_and_program_costs":True,
                    "original_package_components_won":{"settlement_employment":110000000,
                        "management":132000000,"housing_culture_welfare":140000000,"labor_other":221000000},
                    "original_package_total_won":603000000,
                    "applied_package_total_won":600000000}
                    if kind=="fisheries" and key=="center_annual_unit" else {}),
                limitation="매년 각1개 신규 지정·계속 운영·단가 동결은 선례 가정. 농업은 상담교류센터5억원, 어업은 제출 구성사업비603백만원을600백만원으로 적용한 패키지. 다른 기능·규모 센터에 자동 전용 금지")
    for scope,share in [("combined",1),("national",.5),("local",.5)]:
        add(b,d,p,"government_share",share,"ratio",suffix=scope,pages="24B0644 PDF4쪽 표2",
            support_fiscal_scope=scope,reviewed_at="2026-10-04",source_reply_date="2024-06-14",
            limitation="국비·지방비50:50을 추계기간 동결한 정책 가정. 합산과 분할을 함께 더하면 중복")
    add(b,d,p,"estimate_start_year",2025,"year",target=True,pages="24B0644 PDF3쪽",
        reviewed_at="2026-10-04",source_reply_date="2024-06-14",
        timing_basis="공포후6개월과 예상 시행시점을 고려한 해당 선례의2025~2029년 가정",
        limitation="원문에2025년이 명시된 것은 아님. 공포후6개월을 무조건 다음 해로 변환하지 않음")
    from backend.erce.child_allowance_net_evidence import child_allowance_net_rows
    from backend.erce.child_allowance_indexed_evidence import child_allowance_indexed_rows
    from backend.erce.family_benefit_indexed_evidence import family_indexed_rows
    from backend.erce.child_allowance_birth_order_evidence import birth_order_rows
    from backend.erce.regional_child_allowance_evidence import regional_child_allowance_rows
    from backend.erce.disability_couple_evidence import disability_couple_rows
    from backend.erce.disability_expansion_evidence import disability_expansion_rows
    from backend.erce.common_population_evidence import common_population_rows
    from backend.erce.disability_recipient_history import disability_recipient_history_rows
    from backend.erce.basic_pension_staged_evidence import basic_pension_staged_rows
    from backend.erce.basic_pension_statistical_proxies import basic_pension_proxy_rows
    from backend.erce.basic_pension_income_history import basic_pension_income_rows
    from backend.erce.median_pension_evidence import median_pension_rows
    from backend.erce.phased_couple_pension import phased_couple_rows
    from backend.erce.published_pension_replay import published_pension_replay_rows
    from backend.erce.phased_pension_types import phased_pension_type_rows
    from backend.erce.low_income_couple_pension import low_income_couple_rows
    from backend.erce.awareness_promotion_evidence import awareness_promotion_rows
    from backend.erce.commemorative_event_evidence import commemorative_event_rows
    from backend.erce.regional_advocacy_committee import regional_advocacy_committee_rows
    from backend.erce.submitted_support_plan import submitted_plan_rows
    from backend.erce.parent_voucher_indexed_evidence import parent_voucher_rows
    from backend.erce.child_allowance_reviewed_cpi import reviewed_child_cpi_rows
    from backend.erce.single_parent_survey_evidence import single_parent_rows
    from backend.erce.jobseeker_livelihood_evidence import jobseeker_rows
    from backend.erce.jobseeker_duration_evidence import duration_rows
    from backend.erce.housing_management_evidence import housing_management_rows
    from backend.erce.housing_moving_evidence import housing_updated_rows
    from backend.erce.owner_energy_repair_evidence import energy_repair_rows
    from backend.erce.grandparent_care_evidence import grandparent_care_rows
    from backend.erce.grandparent_care_evidence import grandparent_parallel_rows
    rows += grandparent_parallel_rows()
    from backend.erce.foreign_childcare_evidence import foreign_childcare_rows
    rows += foreign_childcare_rows()
    from backend.erce.policy_impact_research_evidence import policy_impact_research_rows
    rows += policy_impact_research_rows()
    from backend.erce.elderly_public_activity_evidence import elderly_public_activity_rows
    rows += elderly_public_activity_rows()
    from backend.erce.medical_communication_evidence import medical_communication_rows
    rows += medical_communication_rows()
    from backend.erce.hospital_interpreter_increment import interpreter_increment_rows
    rows += interpreter_increment_rows()
    from backend.erce.rail_free_transport_evidence import rail_free_transport_rows
    rows += rail_free_transport_rows()
    from backend.erce.mobile_identity_evidence import mobile_identity_rows
    rows += mobile_identity_rows()
    from backend.erce.disabled_child_allowance_evidence import disabled_child_allowance_rows
    rows += disabled_child_allowance_rows()
    from backend.erce.disabled_worker_wage_evidence import disabled_worker_wage_rows
    rows += disabled_worker_wage_rows()
    from backend.erce.government_employment_levy import government_levy_rows
    rows += government_levy_rows()
    from backend.erce.government_employment_levy import government_double_levy_rows
    rows += government_double_levy_rows()
    from backend.erce.disabled_worker_wage_evidence import direct_worker_wage_rows
    rows += direct_worker_wage_rows()
    from backend.erce.levy_sector_evidence import levy_sector_rows
    rows += levy_sector_rows()
    from backend.erce.special_classroom_evidence import special_classroom_rows
    rows += special_classroom_rows()
    from backend.erce.ombudsman_evidence import ombudsman_rows
    rows += ombudsman_rows()
    from backend.erce.survey_annualization_evidence import survey_annualization_rows
    rows += survey_annualization_rows()
    from backend.erce.qualification_exam_evidence import qualification_exam_rows
    rows += qualification_exam_rows()
    from backend.erce.qualification_exam_evidence import later_qualification_exam_projection_rows
    rows += later_qualification_exam_projection_rows()
    from backend.erce.asset_management_budget_evidence import asset_management_budget_rows
    rows += asset_management_budget_rows()
    from backend.erce.child_awareness_budget_evidence import child_awareness_budget_rows
    rows += child_awareness_budget_rows()
    from backend.erce.education_training_budget_evidence import education_training_budget_rows
    rows += education_training_budget_rows()
    from backend.erce.media_monitoring_survey_evidence import media_monitoring_survey_rows
    rows += media_monitoring_survey_rows()
    from backend.erce.facility_survey_expansion_evidence import facility_survey_expansion_rows
    rows += facility_survey_expansion_rows()
    from backend.erce.regional_resident_benefit_evidence import regional_resident_benefit_rows
    rows += regional_resident_benefit_rows()
    from backend.erce.prefunded_annual_survey_evidence import prefunded_survey_rows
    rows += prefunded_survey_rows()
    from backend.erce.protected_child_insurance_evidence import protected_child_insurance_rows
    rows += protected_child_insurance_rows()
    from backend.erce.enterprise_assistant_evidence import enterprise_assistant_rows
    rows += enterprise_assistant_rows()
    from backend.erce.standard_workplace_evidence import standard_workplace_rows
    rows += standard_workplace_rows()
    from backend.erce.medical_standard_workplace import medical_workplace_rows
    rows += medical_workplace_rows()
    from backend.erce.activity_support_research_evidence import activity_support_research_rows
    from backend.erce.central_social_committee_evidence import central_social_committee_rows
    from backend.erce.care_worker_survey_evidence import social_worker_rights_rows, social_worker_survey_history_rows
    rows += social_worker_rights_rows() + social_worker_survey_history_rows()
    from backend.erce.care_worker_survey_evidence import social_worker_treatment_plan_rows
    rows += social_worker_treatment_plan_rows()
    from backend.erce.care_worker_survey_evidence import welfare_meal_safety_survey_rows
    rows += welfare_meal_safety_survey_rows()
    from backend.erce.child_support_advance_evidence import child_support_rows
    from backend.erce.child_support_amount_basis import amount_basis_rows
    return rows + child_allowance_net_rows() + child_allowance_indexed_rows() + family_indexed_rows() + birth_order_rows() + regional_child_allowance_rows() + disability_couple_rows() + disability_expansion_rows() + common_population_rows() + disability_recipient_history_rows() + basic_pension_staged_rows() + basic_pension_proxy_rows() + basic_pension_income_rows() + median_pension_rows() + phased_couple_rows() + published_pension_replay_rows() + phased_pension_type_rows() + low_income_couple_rows() + awareness_promotion_rows() + commemorative_event_rows() + regional_advocacy_committee_rows() + submitted_plan_rows() + parent_voucher_rows() + reviewed_child_cpi_rows() + single_parent_rows() + jobseeker_rows() + duration_rows() + housing_management_rows() + housing_updated_rows() + energy_repair_rows() + grandparent_care_rows() + activity_support_research_rows() + central_social_committee_rows() + child_support_rows() + amount_basis_rows()
