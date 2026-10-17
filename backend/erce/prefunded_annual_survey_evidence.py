"""Annual survey costs less explicitly funded years; no automatic funding renewal."""
from math import isfinite, prod
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs
from backend.economic_forecast_registry import get_forecast_series

PROFILE = "prefunded_annual_survey_delta"
NOTES = ("prefunded_survey_scope_note","prefunded_survey_baseline_note","prefunded_survey_price_note")


def prefunded_survey_rows():
    common = dict(source_bill_no="2216008",available_at="2026-02-20",reviewed_at="2026-10-13",
        source_ref="2216008 비용추계서26C0181 PDF1~3쪽",
        agency="교육부",policy_domain="영유아 교육·특별활동·사교육비조사",
        scope="매년조사·2026기편성분제외·이후정례화추가비",
        service_function=PROFILE,support_derivation=PROFILE,allowed_routes=[PROFILE],
        variable_role="prefunded_survey_operand",requires_applicability_note=True,
        independently_verified=False,obtained_from="reviewed_answer")
    rows = [
        evidence_row(**common,evidence_key="2216008:survey_unit_cost:2026",
            variable_key="prefunded_survey_unit_cost",value=870000000,unit="KRW/survey",
            limitation="2026유아사교육비조사 확정예산 준용. 어린이집 특별활동도 조사표에 포함",
            price_year=2026),
        evidence_row(**common,evidence_key="2216008:survey_base_year:2026",
            variable_key="prefunded_survey_base_year",value=2026,unit="year"),
        evidence_row(**common,evidence_key="2216008:funded_budget:2026",
            variable_key="prefunded_survey_existing_budget",value={"2026":870000000},unit="year_to_KRW",
            limitation="2026기편성예산은확인. 다른연도0은 관측이 아니라 향후별도재원없음 승인 가정")]
    rows[0].update(source_ref="국회예산정책처2026예산안심의결과 PDF102쪽870백만원",
        source_url="https://nabo.go.kr/board/file/bulkDown.do?bid=19&idx=9020",
        independently_verified=True,obtained_from="official_public_budget",source_class="official_standard",
        available_at="2026-10-13",verified_at="2026-10-13",
        limitation="정답열람전공식예산표에서독립확인. 확인일을가용일로사용; 원문헌공표일확인아님. 현재조사 계약요율아님")
    forecast = get_forecast_series("nabo_macro_2025_09_consumer_price")
    rows.append(evidence_row(**{**common,"source_ref":forecast.source_ref},
        evidence_key="nabo_macro_2025_09:prefunded_survey_cpi",
        variable_key="prefunded_survey_cpi_rates",
        value={str(y):r for y,r in forecast.rates_by_year.items()},unit="year_to_ratio",
        forecast_series_key=forecast.key,forecast_published_at=forecast.published_at,
        limitation="확보된2025.9전망2025~2029. 2030값자동연장금지. 이의안정답의전망버전과적용시점은미기재"))
    return rows


def prepare_prefunded_survey(payload):
    if payload.get("route_key") != PROFILE:
        raise ValueError("prefunded survey route required")
    if (payload.get("prefunded_survey_confirmed") is not True
            or payload.get("future_unfunded_survey_assumption_confirmed") is not True
            or not all(str(payload.get(k) or "").strip() for k in NOTES)):
        return {**payload,"support_missing_operands":["prefunded_survey_confirmation"],"support_derivation_trace":[]}
    lag = payload.get("survey_price_rate_year_offset",0)
    if lag not in (0,-1) or isinstance(lag,bool):
        raise ValueError("unsupported survey CPI timing")
    if lag==-1 and (payload.get("estimate_purpose")!="reference_scenario"
            or payload.get("survey_lagged_cpi_assumption_confirmed") is not True
            or not str(payload.get("survey_cpi_timing_note") or "").strip()):
        return {**payload,"support_missing_operands":["survey_cpi_timing_confirmation"],"support_derivation_trace":[]}
    units = {r["variable_key"]:r["unit"] for r in prefunded_survey_rows()}
    layers = dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in ("growth_rate","growth_rates_by_year","frequency_per_year")):
        raise ValueError("annual survey CPI already applied")
    r,missing = resolve_formula_variables(tuple(units),**layers)
    if missing:
        return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    for k,row in r.items():
        values = list(row.value.values()) if isinstance(row.value,dict) else [row.value]
        if (row.unit!=units[k] or not row.source_ref or any(isinstance(x,bool)
                or not isinstance(x,(int,float)) or not isfinite(x) or x<0 for x in values)):
            raise ValueError("invalid prefunded survey operands")
    v = {k:x.value for k,x in r.items()}
    start,years,base = payload.get("start_year"),payload.get("years",5),v["prefunded_survey_base_year"]
    if (isinstance(start,bool) or not isinstance(start,int) or isinstance(years,bool)
            or not isinstance(years,int) or years<1 or base!=int(base) or start<base):
        raise ValueError("prefunded survey horizon invalid")
    rates,funded = v["prefunded_survey_cpi_rates"],v["prefunded_survey_existing_budget"]
    if not isinstance(rates,dict) or not isinstance(funded,dict):
        raise ValueError("annual CPI and funded budgets required")
    annual,trace = [],[]
    for year in range(start,start+years):
        needed = list(range(int(base)+1+lag,year+1+lag))
        if any(str(y) not in rates for y in needed):
            return {**payload,"support_missing_operands":["prefunded_survey_cpi_year_coverage"],"support_derivation_trace":[]}
        cost = round(v["prefunded_survey_unit_cost"]*prod(1+rates[str(y)] for y in needed),2)
        existing = funded.get(str(year),0)
        if existing>cost:
            raise ValueError("existing survey funding exceeds comparable gross cost; scope review needed")
        annual.append(cost-existing)
        trace.append(dict(year=year,gross_survey_cost_won=cost,already_funded_won=existing,
            annual_increment_won=cost-existing,cpi_years_applied=needed,cpi_year_offset=lag,
            future_funding_absence_is_assumption=str(year) not in funded))
    calculated = dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"] = dict(value=annual,unit="KRW/year",is_assumption=True,
        source_ref="; ".join(dict.fromkeys(x.source_ref for x in r.values())))
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}
