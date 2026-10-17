"""Reviewed rank shares and population for grouped child benefits.

Keep table-3 annual shares and table-4 implied fixed shares separate. Neither
is silently chosen to fit a target total; population is a proxy, not recipients.
"""
from math import isfinite

from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE="child_allowance_birth_order_weighted"
SCENARIOS=("table3_annual", "table4_fixed2026")


def evidence_keys(scenario):
    return ["2208381:under18_population:2026-2030", "2208381:under8_population:2026-2030",
            "2208381:child_execution_factor:2025"] + [f"2208381:birth_share_{rank}:{scenario}" for rank in ("first","second","third_plus")]


def birth_order_rows():
    common=dict(source_bill_no="2208381",available_at="2025-04-03",agency="국회예산정책처",
        policy_domain="아동수당",scope="전국0~17세 출생순위별 급여·2026~2030년",
        service_function=PROFILE,variable_role="assumption",reuse_policy="comparable",
        reviewed_at="2026-10-04",obtained_from="reviewed_answer",independently_verified=False,
        allowed_routes=["transfer_population_amount_delta"],support_derivation=PROFILE,
        child_population_geography="전국",birth_order_population_basis="birth_share_proxy",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2208381/cost_estimate.pdf")
    rows=[]
    for key,variable,value,unit,pages,metadata in (
        ("2208381:under18_population:2026-2030","under18_population",[6358318,6136084,5931220,5700261,5486168],"person","PDF3쪽 표2",dict(value_years=list(range(2026,2031)),population_age_min=0,population_age_max=17)),
        ("2208381:under8_population:2026-2030","under8_population",[2045969,1953367,1897859,1871606,1868454],"person","PDF3쪽 표2의0~7세 각연령 합산",dict(value_years=list(range(2026,2031)),population_age_min=0,population_age_max=7)),
        ("2208381:child_execution_factor:2025","child_execution_factor",.996,"ratio","PDF4쪽 전제 및 PDF5~6쪽",dict(observation_year=2025,valid_from_year=2026,valid_to_year=2030)),
    ):
        rows.append(evidence_row(evidence_key=key,variable_key=variable,value=value,unit=unit,
            source_ref=f"2208381 비용추계서25C1087 {pages}",**common,**metadata,
            limitation="2023.12 중위전망 인구 또는2025년 집행계수 동결 선례. 최신실측 아님. 지급률97.2% 추가 적용 금지"))
    annual=([.629,.638,.647,.655,.663],[.305,.299,.293,.287,.281],[.066,.063,.060,.058,.056])
    for scenario in SCENARIOS:
        for i,rank in enumerate(("first","second","third_plus")):
            value=list(annual[i]) if scenario=="table3_annual" else [annual[i][0]]*5
            rows.append(evidence_row(evidence_key=f"2208381:birth_share_{rank}:{scenario}",
                variable_key=f"birth_share_{rank}",value=value,unit="ratio",
                source_ref="2208381 비용추계서25C1087 PDF4쪽 표3" if scenario=="table3_annual" else
                           "2208381 비용추계서25C1087 PDF4쪽2026비율 및 PDF5쪽표4 인원/총인구의근사비율 확인",
                **common,value_years=list(range(2026,2031)),birth_order_share_scenario=scenario,
                forecast_basis="2014~2023년 출생순위 통계 준용; 현재 아동의 실제 형제순위 분포 아님",
                limitation="연령별 실제출생순위가 아닌 대리비율. table3연도별전망과table4암시2026비율동결을 구분. 표4로부터 원시비율을 정확히 복원한 값이 아님. 정답 총액에 맞춰 비율 조정 금지"))
    return rows


def prepare_birth_order_operands(payload):
    if payload.get("route_key")!="transfer_population_amount_delta":
        raise ValueError("birth order route mismatch")
    for key in ("support_derivation_note","birth_order_scope_note","birth_order_scenario_note","estimation_start_note"):
        if not str(payload.get(key) or "").strip():raise ValueError(f"birth order confirmation required: {key}")
    if payload.get("birth_order_share_scenario") not in SCENARIOS or payload.get("birth_order_population_basis")!="birth_share_proxy":
        raise ValueError("birth order share scenario and proxy must be confirmed")
    if payload.get("child_population_geography")!="전국" or payload.get("parent_benefit_unchanged") is not True:
        raise ValueError("birth order geography and unchanged parent benefit must be confirmed")
    units={"under18_population":"person","under8_population":"person","child_execution_factor":"ratio",
        **{f"birth_share_{r}":"ratio" for r in ("first","second","third_plus")},
        **{f"birth_amount_{r}":"KRW/person/month" for r in ("first","second","third_plus")}}
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    for layer in layers.values():
        if any(k in (layer or {}) for k in ("participation_rate","growth_rate","growth_rates_by_year")):
            raise ValueError("birth order duplicate adjustment forbidden")
    resolved,missing=resolve_formula_variables(tuple(units),**layers)
    top,_=resolve_formula_variables(("existing_benefit_per_recipient","payments_per_year","benefit_per_recipient"),**layers)
    for key,row in top.items():
        if row.unit!=("month/year" if key=="payments_per_year" else "KRW/person/month") or not row.source_ref:
            raise ValueError("birth order needs sourced monthly amounts and payment months")
    years=int(payload.get("years") or 5);data={}
    for key,row in resolved.items():
        values=list(row.value) if isinstance(row.value,(list,tuple)) else [row.value]*years
        if row.unit!=units[key] or not row.source_ref:raise ValueError(f"invalid birth order unit/source: {key}")
        if len(values)!=years or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) or v<0
                or (units[key]=="ratio" and v>1) for v in values):raise ValueError(f"invalid birth order operand: {key}")
        data[key]=values
    ranks=("first","second","third_plus");shares=tuple(f"birth_share_{r}" for r in ranks)
    if all(k in data for k in shares) and any(abs(sum(data[k][i] for k in shares)-1)>1e-9 for i in range(years)):
        raise ValueError("birth order shares must sum to one; do not silently normalize")
    if all(k in data for k in ("under18_population","under8_population")) and any(
            old>new for old,new in zip(data["under8_population"],data["under18_population"])):
        raise ValueError("inconsistent birth order age cohorts")
    deps={"new_recipient_count":("under18_population","child_execution_factor"),
          "existing_recipient_count":("under8_population","child_execution_factor"),
          "benefit_per_recipient":shares+tuple(f"birth_amount_{r}" for r in ranks)}
    expressions={"new_recipient_count":"전체0~17세 전망인구×선택한 집행계수",
        "existing_recipient_count":"현행0~7세 전망인구×동일집행계수",
        "benefit_per_recipient":"Σ(확인한출생순위비율×해당순위월액); 연령전체에같은비율준용 가정"}
    calculated=dict(payload.get("calculated_inputs") or {});trace=[]
    for key,dependencies in deps.items():
        if not all(k in data for k in dependencies):continue
        values=[sum(data[f"birth_share_{r}"][i]*data[f"birth_amount_{r}"][i] for r in ranks)
                if key=="benefit_per_recipient" else data[dependencies[0]][i]*data[dependencies[1]][i] for i in range(years)]
        refs="; ".join(dict.fromkeys(resolved[k].source_ref for k in dependencies))
        upper,_=resolve_formula_variables((key,),**{**layers,"calculated_estimate":calculated})
        unit="KRW/person/month" if key=="benefit_per_recipient" else "person"
        if key not in upper:calculated[key]=dict(value=values,unit=unit,source_ref=refs,is_assumption=True)
        trace.append(dict(variable_key=key,dependencies=list(dependencies),values=values,unit=unit,
            source_ref=refs,expression=expressions[key],applied=key not in upper,applicability_note=payload["support_derivation_note"]))
    _,top_missing=resolve_formula_variables(tuple(deps),**{**layers,"calculated_estimate":calculated})
    needed={k for t in top_missing for k in deps[t]}
    return {**payload,"calculated_inputs":calculated,"support_derivation_trace":trace,
            "support_missing_operands":[k for k in missing if k in needed]}
