"""Source-qualified loan revenue / additional-borrowing interest references.

This route covers current-year new issuance only, not total debt service.
Missing baseline balances and future rates must never be backsolved from gold.
"""
from math import isfinite
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

FINANCING_SCOPE = "kosaf_icl_new_issue_government_interest_only"
PENALTY_PROFILE = "icl_cap9_to5_2019_2023"
ROUTE = "new_borrowing_interest_support"


def _number(value, name, *, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(name)
    if not isfinite(value) or value < 0 or (maximum is not None and value > maximum):
        raise ValueError(name)
    return float(value)


def new_borrowing_interest_amounts(request, inputs):
    for key in ("growth_rate", "growth_rates_by_year", "base_year", "first_year_fraction", "duration"):
        if key in inputs:
            raise ValueError(f"{key}: use annual borrowing/rates and average balance without duplicate adjustment")
    operands = {}
    for name in ("new_borrowing_amount", "borrowing_interest_rate", "average_balance_factor", "government_interest_support_share"):
        expected = "KRW/year" if name == "new_borrowing_amount" else "ratio"
        if inputs[name].unit != expected:
            raise ValueError(f"{name} unit must be {expected}")
        raw = inputs[name].value
        if isinstance(raw, (list, tuple)):
            if len(raw) != request.years:
                raise ValueError(name)
            values = raw
        else:
            values = [raw] * request.years
        operands[name] = [_number(value, name, maximum=None if name == "new_borrowing_amount" else 1)
                          for value in values]
    return [operands["new_borrowing_amount"][i] * operands["borrowing_interest_rate"][i]
            * operands["average_balance_factor"][i] * operands["government_interest_support_share"][i]
            for i in range(request.years)]


def incremental_penalty_loss(balances, previous_balance, old_actual_rate, new_actual_rate, replacement_share):
    """Confirmed incremental-stock scenario; requires the previous-year balance.

    Rates are realized/condition-converted ratios, NOT statutory caps.
    This does not decide whether an incremental-stock scenario is applicable.
    """
    previous = _number(previous_balance, "previous_year_balance")
    old = _number(old_actual_rate, "old_actual_rate", maximum=1)
    new = _number(new_actual_rate, "new_actual_rate", maximum=1)
    replacement = _number(replacement_share, "replacement_share", maximum=1)
    if new > old or not isinstance(balances, (list, tuple)) or not balances:
        raise ValueError("increasing penalty / empty balances outside this decline scenario")
    output = []
    for raw in balances:
        balance = _number(raw, "balance")
        if balance < previous:
            raise ValueError("declining balance requires a separate financing scenario")
        output.append((balance - previous) * (old - new) * replacement)
        previous = balance
    return output


def borrowing_rates_for_years(years, known_rates, sovereign_forecast, spread):
    """Use a dated direct rate or a supplied forecast + spread; never extrapolate."""
    spread = _number(spread, "borrowing_spread", maximum=1)
    output = []
    for year in years:
        if year in known_rates:
            value = known_rates[year]
        elif year in sovereign_forecast:
            value = _number(sovereign_forecast[year], f"sovereign_forecast:{year}", maximum=1) + spread
        else:
            raise ValueError(f"missing interest rate forecast:{year}")
        output.append(_number(value, f"borrowing_interest_rate:{year}", maximum=1))
    return output


def project_overdue_balances(supply, overdue, *, start_year, years, lag):
    """Forecast lagged-supply ratios using mean annual percentage-point change.

    The preceding forecast year is included, so first-year increments need no
    fitted baseline. Retain precision; the report's displayed 1.7pp is rounded.
    """
    lag_value = _number(lag, "repayment_lag_years")
    if not lag_value.is_integer() or lag_value < 1:
        raise ValueError("repayment_lag_years")
    lag = int(lag_value)
    supply = {int(y): _number(v,"icl_supply_by_year") for y,v in supply.items()}
    overdue = {int(y): _number(v,"overdue_repayment_by_year") for y,v in overdue.items()}
    observed = sorted(overdue)
    if len(observed) < 2 or any(b-a != 1 for a,b in zip(observed,observed[1:])):
        raise ValueError("need consecutive historical overdue years")
    ratios = {}
    for year in observed:
        if year-lag not in supply or supply[year-lag] <= 0:
            raise ValueError(f"missing lagged supply:{year-lag}")
        ratios[year] = _number(overdue[year]/supply[year-lag],"overdue_to_supply_ratio",maximum=1)
    growth = (ratios[observed[-1]]-ratios[observed[0]])/(len(observed)-1)
    if start_year-1 <= observed[-1] or years < 1:
        raise ValueError("forecast must include a subsequent baseline year")
    balances = []
    for year in range(start_year-1,start_year+years):
        if year-lag not in supply:
            raise ValueError(f"missing forecast supply:{year-lag}")
        ratio = _number(ratios[observed[-1]]+growth*(year-observed[-1]),"forecast_ratio",maximum=1)
        balances.append(supply[year-lag]*ratio)
    return balances, growth


def prepare_loan_interest_projection(payload):
    """Opt-in confirmed historical scenario, after normal DB scope/self gates."""
    if not payload.get("loan_projection_scenario"):
        return payload
    if payload["loan_projection_scenario"] != "icl_six_year_lag_linear_ratio_growth" or not str(payload.get("loan_projection_confirmation_note") or "").strip():
        raise ValueError("loan projection needs a confirmed applicability note")
    required = ("icl_supply_by_year", "overdue_repayment_by_year", "repayment_lag_years",
                "old_actual_penalty_ratio", "new_converted_penalty_ratio", "borrowing_replacement_share",
                "known_borrowing_rates_by_year", "sovereign_interest_forecast", "borrowing_spread")
    resolved, missing = resolve_formula_variables(required,
        target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if missing:
        raise ValueError("missing loan projection evidence: "+", ".join(missing))
    for key in ("icl_supply_by_year","overdue_repayment_by_year"):
        if resolved[key].unit != "KRW/year":
            raise ValueError(f"{key} unit must be KRW/year")
    for key in ("old_actual_penalty_ratio","new_converted_penalty_ratio","borrowing_replacement_share","borrowing_spread","known_borrowing_rates_by_year","sovereign_interest_forecast"):
        if resolved[key].unit != "ratio":
            raise ValueError(f"{key} unit must be ratio")
    if payload.get("start_year") is None:
        raise ValueError("start_year")
    start, years = int(payload["start_year"]), int(payload.get("years") or 5)
    balances, _ = project_overdue_balances(resolved["icl_supply_by_year"].value,
        resolved["overdue_repayment_by_year"].value, start_year=start, years=years,
        lag=resolved["repayment_lag_years"].value)
    amount = incremental_penalty_loss(balances[1:],balances[0],
        resolved["old_actual_penalty_ratio"].value,resolved["new_converted_penalty_ratio"].value,
        resolved["borrowing_replacement_share"].value)
    rates = borrowing_rates_for_years(range(start,start+years),
        {int(y):v for y,v in resolved["known_borrowing_rates_by_year"].value.items()},
        {int(y):v for y,v in resolved["sovereign_interest_forecast"].value.items()},resolved["borrowing_spread"].value)
    calculated = dict(payload.get("calculated_inputs") or {})
    refs = "; ".join(dict.fromkeys(row.source_ref for row in resolved.values()))
    for key,value,unit in (("new_borrowing_amount",amount,"KRW/year"),("borrowing_interest_rate",rates,"ratio")):
        calculated.setdefault(key,dict(value=value,unit=unit,source_ref=refs,is_assumption=True))
    return {**payload,"calculated_inputs":calculated}


def loan_financing_rows():
    common = dict(source_bill_no="2204385", available_at="2026-10-03", agency="교육부",
        policy_domain="취업후상환학자금", scope="한국장학재단 ICL 연체금 감소에 따른 추가 채권 이자",
        service_function="당해 신규 차입분에 대한 정부 이자 지원", reviewed_at="2026-10-03",
        obtained_from="reviewed_answer", requires_applicability_note=True,
        public_financing_scope=FINANCING_SCOPE,
        limitation="24C4099 추계의 과거 조건. 직접 공식자료 독립 검증 전이며 최신 고정값 아님. 재원 연결·정부 부담 및 신규분 범위 확인 필요")
    rows = []
    def add(suffix, key, value, unit, page, role, **extra):
        rows.append(evidence_row(**common, evidence_key=f"2204385:{suffix}", variable_key=key,
            value=value, unit=unit, source_ref=f"2204385 첨부24C4099 PDF p.{page}",
            variable_role=role, allowed_routes=[ROUTE], **extra))
    add("new_borrowing_2025_2029", "new_borrowing_amount", [753000000,266000000,380000000,743000000,285000000],
        "KRW/year", 6, "target_quantity", reuse_policy="target_only", value_years=[2025,2026,2027,2028,2029])
    add("new_borrowing_2025", "new_borrowing_amount", 753000000, "KRW/year", 6,
        "target_quantity", reuse_policy="target_only", valid_from_year=2025, valid_to_year=2025)
    add("new_issue_rate_2025", "borrowing_interest_rate", .0357, "ratio", "3·6", "budget_rate_reference",
        valid_from_year=2025, valid_to_year=2025, price_year=2025)
    add("average_balance_factor", "average_balance_factor", .583, "ratio", 6, "case_assumption")
    add("government_interest_support_share", "government_interest_support_share", 1, "ratio", "3·6", "funding_assumption")
    add("borrowing_replacement_share", "borrowing_replacement_share", 1, "ratio", "3·6", "funding_assumption")
    add("old_actual_penalty_ratio", "old_actual_penalty_ratio", .0836, "ratio", 5,
        "historical_actual_ratio", loan_penalty_profile=PENALTY_PROFILE, observation_years=[2019,2020,2021,2022,2023])
    add("new_converted_penalty_ratio", "new_converted_penalty_ratio", .0454, "ratio", 5,
        "condition_converted_ratio", loan_penalty_profile=PENALTY_PROFILE, observation_years=[2019,2020,2021,2022,2023])
    add("new_issue_spread", "borrowing_spread", .0017, "ratio", 6, "forecast_assumption",
        valid_from_year=2025, valid_to_year=2029,
        application_policy="2025 예산 금리차로 관찰,2025는 직접금리3.57% 우선.2026~2029 국고채 전망에 가산")
    add("repayment_lag", "repayment_lag_years", 6, "year", "3·4", "case_assumption")
    add("overdue_ratio_growth", "overdue_ratio_growth_percentage_points", 1.7, "percentage_point/year", 4,
        "historical_trend_assumption", observation_years=[2019,2020,2021,2022,2023])
    add("historical_supply", "icl_supply_by_year", {
        "2013":1781100000000,"2014":1638600000000,"2015":1370500000000,
        "2016":1198300000000,"2017":904600000000,"2019":877700000000,
        "2020":821500000000,"2021":795300000000,"2022":826400000000,"2023":791800000000},
        "KRW/year", 4, "historical_statistics", loan_penalty_profile=PENALTY_PROFILE)
    add("historical_overdue", "overdue_repayment_by_year", {
        "2019":45500000000,"2020":53800000000,"2021":62200000000,
        "2022":73600000000,"2023":85900000000}, "KRW/year", 4,
        "historical_statistics", loan_penalty_profile=PENALTY_PROFILE)
    add("known_borrowing_rates", "known_borrowing_rates_by_year", {"2025":.0357}, "ratio", "3·6",
        "budget_rate_reference", loan_penalty_profile=PENALTY_PROFILE,
        rate_note="2025 신규분만 직접 제시. 이후는 별도 국고채 전망과 금리차로 계산")
    return rows


def official_loan_projection_rows():
    """Directly checked official vintages; do not silently replace old rows."""
    common = dict(available_at="2026-10-03",reviewed_at="2026-10-03",source_class="official_standard",
        obtained_from="official_web",requires_applicability_note=True,policy_domain="취업후상환학자금",
        public_financing_scope=FINANCING_SCOPE,allowed_routes=[ROUTE],verified_at="2026-10-03")
    return [evidence_row(**common,evidence_key="official:nabo202410:treasury3y:2024_2033",
        variable_key="sovereign_interest_forecast",value={str(y):v/100 for y,v in
            zip(range(2024,2034),(3.1,2.8,2.8,2.7,2.6,2.5,2.5,2.4,2.3,2.3))},unit="ratio",
        source_bill_no="official:nabo202410",agency="국회예산정책처",scope="2024년10월 전망 국고채3년 금리",
        service_function="공식 금리 전망",variable_role="official_forecast",published_at="2024-10-11",
        source_ref="2025년 NABO 경제전망(Ⅰ.지출),2024.10, PDF p.147/인쇄p.109 부록10년전망",
        source_url="https://www.nabo.go.kr/board/file/down.do?fid=33318209",
        source_archive="backend/generated/erce_official_sources/2026-10-03/nabo_202410_expenditure.pdf",
        source_sha256="fcf855bf9e999db2ff79fa09137c65f6551a02367a84135d820fd53a6a92ecd4",
        valid_from_year=2024,valid_to_year=2033,forecast_maturity_years=3,refresh_policy="새 전망은 별도 버전 추가",
        limitation="당시 전망이며 현재 최신 전망이 아님;3년 금리 선택 자체는 확인한 재원 시나리오 가정"),
        evidence_row(**common,evidence_key="official:index155302:icl_supply:2013_2025:20261003",
        variable_key="icl_supply_by_year",value={str(y):v*100000000 for y,v in
            zip(range(2013,2026),(17811,16386,13705,11983,9046,8379,8777,8215,7953,8264,7918,8762,9169))},
        unit="KRW/year",source_bill_no="official:index155302",agency="교육부",scope="전국 취업후상환학자금 연간 공급액",
        service_function="ICL 과거 공급 규모",variable_role="historical_statistics",
        source_ref="e-나라지표1553 통계표155302,취업후상환학자금 대출행; 억원→원 환산",
        source_url="https://www.index.go.kr/unity/potal/eNara/sub/showStblGams3.do?stts_cd=155302&idx_cd=1553&freq=Y&period=2013:2025",
        source_archive="backend/generated/erce_official_sources/2026-10-03/index155302_icl_supply_2013_2025.html",
        source_sha256="94b48886cafebfc8a9c356e4e6b0445457af6e195081d535151c7a9ee8ad0ba8",
        publisher="교육부·한국장학재단",observation_years=list(range(2013,2026)),reported_updated_at="2026-03-04",
        refresh_policy="연간 갱신본을 새 스냅샷으로 저장; 기존 빈티지 유지",
        limitation="2026-10-03 확보본; 과거 공급실적과 미래 연체 발생률 전망은 구분.2018공급액8379억원을 직접 확인")]


def reviewed_loan_projection_payload(db_path):
    common = reviewed_loan_interest_payload(db_path,years=5)
    keys = ["2204385:"+suffix for suffix in ("average_balance_factor","government_interest_support_share",
        "historical_overdue","repayment_lag","old_actual_penalty_ratio","new_converted_penalty_ratio",
        "borrowing_replacement_share","new_issue_spread","known_borrowing_rates")]
    keys += ["official:nabo202410:treasury3y:2024_2033","official:index155302:icl_supply:2013_2025:20261003"]
    return {**common,"selected_evidence_keys":keys,"loan_penalty_profile":PENALTY_PROFILE,
        "loan_projection_scenario":"icl_six_year_lag_linear_ratio_growth",
        "loan_projection_confirmation_note":"정답 확인 후 참고회귀:ICL 공급액6년시차·비율추세·증가분 차입 및 정부이자지원 가정 적용",
        "evidence_selection_reasons":{key:"ICL 신규차입 이자지원의 당시2024.10 전망/공급실적 범위 확인. 연체율·시차는 정답 확인 후 시나리오" for key in keys}}


def reviewed_loan_interest_payload(db_path, *, years=1):
    if years not in (1, 5):
        raise ValueError("review fixture supports 2025 only or 2025–2029")
    amount = "new_borrowing_2025" if years == 1 else "new_borrowing_2025_2029"
    # Future interest rates are deliberately not supplied for the five-year case.
    suffixes = [amount, "average_balance_factor", "government_interest_support_share"]
    if years == 1:
        suffixes.append("new_issue_rate_2025")
    return dict(route_key=ROUTE, bill_no="2204385", agency="교육부", policy_domain="취업후상환학자금",
        public_financing_scope=FINANCING_SCOPE, start_year=2025, years=years,
        cutoff_date="2026-10-03", evidence_mode="development_review", variable_db_path=db_path,
        selected_evidence_keys=[f"2204385:{suffix}" for suffix in suffixes])
