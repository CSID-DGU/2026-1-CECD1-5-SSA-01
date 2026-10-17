"""Tuition-capped scholarship scenarios, not unconditional payment rates."""
from math import isfinite

from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

MODE = "tuition_capped_delta"
YEARS = [2026, 2027, 2028, 2029, 2030]
POLICY_URL = "https://www.kosaf.go.kr/ko/info.do?mode=view&pg=press01_02&seqNo=18747"
CURRENT_URL = "https://www.moe.go.kr/boardCnts/viewRenew.do?boardID=294&boardSeq=105272&lev=0"
MIX_URL = "https://nabo.go.kr/board/file/down.do?fid=33318748"
# Observed national student composition, not the scholarship target's actual
# distribution. This report labels them enrolled students, but its totals
# match the census's registered students (including students on leave).
NATIONAL_MIX_2024 = {
    "public_general": 425003, "public_junior": 9755,
    "private_general": 1411622, "private_junior": 482287,
}
CAPS = {"type1": (6000000, 4400000, 3600000, 1000000),
        "multichild_first_second": (6100000, 5050000, 4650000, 1350000)}
BANDS = ("1-3", "4-6", "7-8", "9")
TUITION = {
    "public_general": [4227000, 4235000, 4244000, 4252000, 4260000],
    "public_junior": [2408000, 2417000, 2426000, 2435000, 2444000],
    "private_general": [7716000, 7762000, 7809000, 7856000, 7903000],
    "private_junior": [6391000, 6463000, 6536000, 6609000, 6683000],
}
COUNTS = {
    "new_two_child_second": ([113871,112581,111305,110044,108797],
        [125781,124356,122947,121554,120177], [129013,127552,126106,124677,123265],
        [105851,104651,103466,102293,101134]),
    "existing_multichild_second": ([16364,16179,15996,15814,15635],
        [15388,15213,15041,14870,14702], [14170,14009,13850,13693,13538],
        [10062,9948,9835,9724,9613]),
}


def scholarship_cap_rows():
    common = dict(available_at="2026-10-03", reviewed_at="2026-10-03",
        agency="교육부", policy_domain="다자녀 국가장학금",
        scope="등록금 한도 내 지원 차액", service_function="등록금·지원상한별 장학금 순증",
        allowed_routes=["transfer_recipient_delta"], scholarship_calculation=MODE)
    rows = []
    # Each schedule is valid only for its own policy year. Reusing it in a
    # future frozen-policy scenario requires a separately confirmed assumption.
    for year, url in ((2025, POLICY_URL), (2026, CURRENT_URL)):
        for program, caps in CAPS.items():
            for band, cap in zip(BANDS, caps):
                rows.append(evidence_row(**common,
                    evidence_key=f"official:scholarship:{year}:{program}:{band}",
                    variable_key="existing_support_cap", value=cap, unit="KRW/person/year",
                    source_bill_no=f"official:scholarship:{year}", source_ref=url, source_url=url,
                    source_class="official_standard", variable_role="constraint", value_kind="upper_limit",
                    scholarship_income_band=band, scholarship_program=program,
                    scholarship_policy_reference_year=year, valid_from_year=year, valid_to_year=year,
                    limitation="지원 상한이며 평균 지급액 아님. 2025년은 2학기 인상 후 연간환산 기준",
                    refresh_policy="매년 시행 기준 확인. 미래 연도의 확정 단가로 자동 전용 금지"))
        rows.append(evidence_row(**common,
            evidence_key=f"official:scholarship:{year}:third_plus:9",
            variable_key="new_support_cap", value=2000000, unit="KRW/person/year",
            source_bill_no=f"official:scholarship:{year}", source_ref=url, source_url=url,
            source_class="official_standard", variable_role="constraint", value_kind="upper_limit",
            scholarship_income_band="9", scholarship_policy_reference_year=year,
            valid_from_year=year, valid_to_year=year,
            limitation="셋째 이상 9구간 상한. 둘째 확대 적용은 법안 사실이 아닌 별도 정책 시나리오"))
    for kind, values in TUITION.items():
        rows.append(evidence_row(**common, evidence_key=f"2209533:tuition:{kind}:2026-2030",
            variable_key="annual_tuition", value=values, unit="KRW/person/year",
            source_bill_no="2209533", source_ref="2209533 첨부25C2051 대학유형별 등록금 전망표",
            variable_role="projected_tuition", university_kind=kind, value_years=YEARS,
            requires_applicability_note=True,
            limitation="2025년 작성 전망. 최신 실제 등록금 아님. 대상 대학유형·규모가 같을 때 가정 후보"))
    for cohort, groups in COUNTS.items():
        for band, values in zip(BANDS, groups):
            rows.append(evidence_row(**common,
                evidence_key=f"2209533:count:{cohort}:{band}:2026-2030",
                variable_key="recipient_count", value=values, unit="person/year",
                source_bill_no="2209533", source_ref="2209533 첨부25C2051 소득·편입/기존 인원 전망표",
                variable_role="target_quantity", reuse_policy="target_only", value_years=YEARS,
                scholarship_cohort=cohort, scholarship_income_band=band,
                limitation="해당 법안 전망인원. 대학유형별 인원 미제공. 다른 법안 인원으로 자동 재사용 금지"))
    rows.append(evidence_row(**common, evidence_key="2209533:policy_scenario",
        variable_key="scholarship_scope_rule", value={
            "candidate_cohorts": list(COUNTS), "excluded_already_full": ["기초·차상위"],
            "unestimated_cohorts": ["new_two_child_first"],
            "needs_confirmation": ["둘째부터 전액지원 실시", "9구간 신규/기존 지원방식 차이"],
            "missing_statistics": "소득구간×출생순위×가구자녀수×대학유형별 재학생 수"},
        unit="rule", source_bill_no="2209533", source_ref="2209533 첨부25C2051 추계 전제 및 표",
        variable_role="applicability_rule", requires_applicability_note=True,
        limitation="원문은 가족 자녀수 기준만 변경. 전액지원 확대는 확인받을 선례 가정; 미추계는 비용0 아님"))
    rows.append(evidence_row(**common,
        evidence_key="official:nabo:university_mix:2024:general_junior",
        variable_key="scholarship_university_mix", value=NATIONAL_MIX_2024,
        unit="person", source_bill_no="official:nabo:university_mix:2024",
        source_ref="국회예산정책처 지방대학 육성정책 평가(2025-08-21), PDF p.35~36/본문 p.14~15, 교육부 자료",
        source_url=MIX_URL, published_at="2025-08-21", observation_year=2024,
        variable_role="population_distribution_proxy", source_class="precedent_assumption",
        requires_applicability_note=True, independently_verified=True,
        cache_path="backend/generated/erce_official_sources/2026-10-03/nabo_20250821_university_mix.pdf",
        source_sha256="5d452f6e7e6fff044181db338e53113e51882d28fa42e57765b4fd6513747799",
        population_basis="2024 전국 일반대학·전문대학 재적학생 구성비",
        limitation="장학금 소득·가구자녀수·출생순위별 실제 분포 아님. 휴학생 포함 재적학생 통계이며 교육·산업대학 별도 미포함. 일반대학 분포를 일반·교육·산업 유형의 대리값으로 사용한다는 확인 필요",
        refresh_policy="새 공식 통계 확보 시 새 버전 추가. 해당 법안의 유형별 실적이 있으면 우선 사용",
        obtained_from="official_report_population_proxy"))
    return rows


def prepare_scholarship_population_mix(payload):
    if payload.get("scholarship_population_allocation") != "national_mix_proxy":
        return payload
    if payload.get("scholarship_recipient_count_scope") != "cohort_total":
        raise ValueError("scholarship proxy allocation needs an unsplit cohort total")
    if not str(payload.get("scholarship_mix_confirmation_note") or "").strip():
        raise ValueError("scholarship university mix needs applicability confirmation")
    resolved, _ = resolve_formula_variables(("recipient_count", "scholarship_university_mix"),
        target_explicit=payload.get("explicit_inputs"), target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"), calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k not in resolved for k in ("recipient_count", "scholarship_university_mix")):
        raise ValueError("missing scholarship cohort count or university mix")
    mix = resolved["scholarship_university_mix"]
    if mix.unit != "person" or not isinstance(mix.value, dict) or set(mix.value) != set(TUITION):
        raise ValueError("scholarship mix needs four university types and person units")
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) or v < 0
           for v in mix.value.values()) or sum(mix.value.values()) <= 0:
        raise ValueError("invalid scholarship university composition")
    kind = payload.get("university_kind")
    if kind not in mix.value:
        raise ValueError("scholarship allocation university type is missing")
    count = resolved["recipient_count"]
    if count.unit not in {"person", "person/year"}:
        raise ValueError("scholarship cohort count needs person units")
    values = count.value if isinstance(count.value,(list,tuple)) else [count.value]*int(payload.get("years") or 5)
    if len(values) != int(payload.get("years") or 5) or any(isinstance(v,bool) or
            not isinstance(v,(int,float)) or not isfinite(v) or v < 0 for v in values):
        raise ValueError("invalid scholarship cohort counts")
    share = mix.value[kind] / sum(mix.value.values())
    updated = dict(payload)
    # Transform the confirmed TOTAL into a per-university estimate without
    # pretending it was a per-university fact. Keep the parent value as audit
    # metadata and remove it from every priority layer before calculation.
    for layer in ("explicit_inputs", "actual_inputs", "official_inputs", "calculated_inputs", "selected_variable_inputs"):
        inputs = dict(payload.get(layer) or {})
        inputs.pop("recipient_count", None)
        updated[layer] = inputs
    updated["calculated_inputs"]["recipient_count"] = dict(
        value=[v*share for v in values], unit="person/year", is_assumption=True,
        source_ref=count.source_ref + "; " + mix.source_ref,
        calculation="집단 총인원 × 확인받은 전국 대학유형 구성비",
        parent_cohort_counts=list(values), university_share=share)
    updated["scholarship_recipient_count_scope"] = "university_type_allocated"
    return updated


def prepare_scholarship_caps(payload):
    if payload.get("scholarship_calculation") != MODE:
        return payload
    payload = prepare_scholarship_population_mix(payload)
    if not str(payload.get("scholarship_support_confirmation_note") or "").strip():
        raise ValueError("scholarship support scenario needs confirmation")
    cohort = payload.get("scholarship_cohort")
    expected_program = {"new_two_child_second": "type1",
                        "existing_multichild_second": "multichild_first_second"}.get(cohort)
    if expected_program and payload.get("scholarship_program") != expected_program:
        raise ValueError("scholarship cohort and existing program mismatch")
    mode = payload.get("scholarship_new_support_mode")
    if mode not in {"full_tuition", "capped"}:
        raise ValueError("scholarship new support mode must be full_tuition or capped")
    keys = ("annual_tuition", "existing_support_cap", "new_support_cap")
    resolved, _ = resolve_formula_variables(keys,
        target_explicit=payload.get("explicit_inputs"), target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"), calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    needed = keys if mode == "capped" else keys[:2]
    if any(k not in resolved for k in needed):
        return payload  # Preserve unknown variables; never manufacture a zero.
    years = int(payload.get("years") or 5)
    def series(key):
        item = resolved[key]
        if item.unit != "KRW/person/year":
            raise ValueError("scholarship caps and tuition need annual units")
        values = item.value if isinstance(item.value, (list, tuple)) else [item.value] * years
        if len(values) != years or any(isinstance(v, bool) or not isinstance(v, (int,float))
                or not isfinite(v) or v < 0 for v in values):
            raise ValueError("invalid scholarship annual values")
        return values
    tuition, old = series("annual_tuition"), series("existing_support_cap")
    new = tuition if mode == "full_tuition" else series("new_support_cap")
    old_actual = [min(t, c) for t, c in zip(tuition, old)]
    new_actual = [min(t, c) for t, c in zip(tuition, new)]
    if any(n < o for n, o in zip(new_actual, old_actual)):
        raise ValueError("support expansion cannot reduce scholarship payment")
    # Annual values already include policy assumptions; no implicit growth or
    # semester multipliers may be applied again by the generic engine.
    for layer in ("explicit_inputs", "actual_inputs", "official_inputs", "calculated_inputs", "selected_variable_inputs"):
        inputs = payload.get(layer) or {}
        if any(k in inputs for k in ("growth_rate", "growth_rates_by_year", "first_year_fraction")):
            raise ValueError("scholarship annual values cannot apply duplicate growth")
        if "payments_per_year" in inputs:
            v = inputs["payments_per_year"]
            if (v.get("value") if isinstance(v, dict) else v) != 1:
                raise ValueError("annual scholarship cannot apply semesters twice")
    calculated = dict(payload.get("calculated_inputs") or {})
    refs = "; ".join(dict.fromkeys(resolved[k].source_ref for k in needed))
    for key, values in (("benefit_per_recipient", new_actual), ("existing_benefit_per_recipient", old_actual)):
        # Do not override stronger, explicitly supplied actual payments.
        calculated[key] = dict(value=values, unit="KRW/person/year", source_ref=refs,
            is_assumption=True, calculation="min(등록금, 확인된 지원상한)")
    return {**payload, "calculated_inputs":calculated}


def reviewed_scholarship_cap_payload(db_path, cohort, band, university_kind):
    """Post-answer development scenario only; never an independent prediction."""
    if cohort not in COUNTS or band not in BANDS or university_kind not in TUITION:
        raise ValueError("unknown scholarship cohort/band/university type")
    program = "type1" if cohort == "new_two_child_second" else "multichild_first_second"
    capped = cohort == "existing_multichild_second" and band == "9"
    keys = [f"2209533:count:{cohort}:{band}:2026-2030",
        f"2209533:tuition:{university_kind}:2026-2030",
        f"official:scholarship:2025:{program}:{band}"]
    if capped:
        keys.append("official:scholarship:2025:third_plus:9")
    return dict(route_key="transfer_recipient_delta", bill_no="2209533",
        start_year=2026, years=5, cutoff_date="2026-10-03", evidence_mode="development_review",
        variable_db_path=db_path, scholarship_calculation=MODE,
        scholarship_cohort=cohort, scholarship_income_band=band, scholarship_program=program,
        scholarship_policy_reference_year=2025, university_kind=university_kind,
        scholarship_new_support_mode="capped" if capped else "full_tuition",
        scholarship_support_confirmation_note="정답 확인 후 가정: 둘째 확대. 9구간은 신규 전액/기존200만원으로 구분; 정책 확인 필요",
        scholarship_policy_projection="freeze_reference_policy",
        scholarship_policy_confirmation_note="2025년2학기 연간환산 기준 동결 선례 가정; 미래 공식 확정값 아님",
        selected_evidence_keys=keys)


def reviewed_scholarship_bounds(db_path):
    """Bounds over unknown university mix, not fourfold duplicated enrollment."""
    from backend.erce.engine import estimate_routed_item
    lower, upper = [0]*5, [0]*5
    partial = None
    for cohort in COUNTS:
        for band in BANDS:
            scenarios = [estimate_routed_item(reviewed_scholarship_cap_payload(db_path, cohort, band, kind))
                         for kind in TUITION]
            for i in range(5):
                amounts = [r.annual_amounts_thousand[i] for r in scenarios]
                lower[i] += min(amounts)
                upper[i] += max(amounts)
            if cohort == "existing_multichild_second" and band == "9":
                partial = list(scenarios[0].annual_amounts_thousand)
    return dict(bill_no="2209533", evidence_mode="development_review", years=YEARS,
        existing_band9_thousand=partial, lower_bound_thousand=lower, upper_bound_thousand=upper,
        gold_annual_million=[1498425,1503288,1508302,1512959,1517417],
        gold_total_million=7540391,
        limitations=["전체 금액 점추정 아님; 대학유형별 대상인원 미확보",
            "신규2자녀 첫째는 정답도 미추계", "9구간 신규/기존 지원방식 차이는 정책 가정 확인 필요",
            "정답 확인 후 회귀검증이며 미열람 평가 정확도 아님"])


def reviewed_scholarship_point_estimate(db_path, *, policy_scenario):
    """Compute all answer-covered groups with a declared national-mix proxy.

    The policy scenarios are kept separate: do not tune the mix or policy
    choice to reproduce the answer's monetary amounts.
    """
    from backend.erce.engine import estimate_routed_item
    if policy_scenario not in {"answer_table_reference", "all_second_full_tuition",
                               "third_child_schedule_extension"}:
        raise ValueError("scholarship policy scenario must be selected explicitly")
    totals = [0]*5
    components = []
    allocated = {}
    mix_key = "official:nabo:university_mix:2024:general_junior"
    for cohort in COUNTS:
        for band in BANDS:
            allocated[(cohort,band)] = [0.0]*5
            for kind in TUITION:
                p = reviewed_scholarship_cap_payload(db_path, cohort, band, kind)
                if policy_scenario == "all_second_full_tuition" and band == "9":
                    p["scholarship_new_support_mode"] = "full_tuition"
                    p["selected_evidence_keys"] = [k for k in p["selected_evidence_keys"] if ":third_plus:" not in k]
                if policy_scenario == "third_child_schedule_extension" and band == "9":
                    p["scholarship_new_support_mode"] = "capped"
                    new_cap = "official:scholarship:2025:third_plus:9"
                    if new_cap not in p["selected_evidence_keys"]:
                        p["selected_evidence_keys"].append(new_cap)
                p.update(scholarship_population_allocation="national_mix_proxy",
                    scholarship_recipient_count_scope="cohort_total",
                    scholarship_mix_confirmation_note="대상 집단 실제 대학분포 미확보. 2024 전국 일반·전문대 재적학생 구성비를 대리값으로 동결; 교육·산업대도 일반대 비중 준용. 정답 역산 없음",
                    scholarship_support_confirmation_note=f"정답 확인 후 정책 시나리오 비교: {policy_scenario}. 원문 의무나 현재 확정정책 아님",
                    evidence_selection_reasons={mix_key:"소득·가구별 대학분포가 없으므로 전국 일반·전문대 재적학생 구성비를 비교 가정으로 사용"})
                p["selected_evidence_keys"].append(mix_key)
                r = estimate_routed_item(p)
                for i, amount in enumerate(r.annual_amounts_thousand):
                    totals[i] += amount
                    allocated[(cohort,band)][i] += r.resolved_variables["recipient_count"].value[i]
                components.append(dict(cohort=cohort, income_band=band, university_kind=kind,
                    allocated_recipients=r.resolved_variables["recipient_count"].value,
                    annual_amounts_thousand=list(r.annual_amounts_thousand), source_refs=list(r.source_refs)))
    # Each group is split once; all its recipients are preserved across types.
    for (cohort, band), values in allocated.items():
        expected = COUNTS[cohort][BANDS.index(band)]
        if any(abs(a-b)>1e-6 for a,b in zip(values,expected)):
            raise ValueError("scholarship allocation did not conserve cohort counts")
    gold = 7540391 * 1000
    return dict(bill_no="2209533", evidence_mode="development_review", status="computed_review",
        policy_scenario=policy_scenario, years=YEARS, covered_cohorts=list(COUNTS),
        covered_income_bands=list(BANDS), annual_amounts_thousand=totals,
        total_thousand=sum(totals), gold_total_thousand=gold,
        total_absolute_error_percent=abs(sum(totals)-gold)/gold*100,
        mix_evidence_key=mix_key,
        university_shares={k:v/sum(NATIONAL_MIX_2024.values()) for k,v in NATIONAL_MIX_2024.items()},
        components=components,
        missing_calculation_inputs=[],
        limitations=["정답과 같은 일부추계 범위 전체를 계산; 신규2자녀 첫째는 범위 밖이며 비용0 아님",
            "대학유형별 대상집단 실제 분포 대신2024년 전국 재적학생 구성비 대리가정",
            "지원방식·정책 동결은 명시한 시나리오이며 사용자 확인 필요",
            "정답 확인 후 재계산이며 미열람 독립평가 아님"])
