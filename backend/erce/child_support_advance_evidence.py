"""Versioned advance-payment cohort and system-upgrade expense components."""
from decimal import Decimal,ROUND_HALF_UP
from math import isfinite,prod
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs

ADVANCE="child_support_advance_expense"
SYSTEM="child_support_system_upgrade"


def child_support_rows():
    rows=[]
    data={
        ADVANCE:[
            ("household_forecast",[22516347,22705521,22879575,23037240,23180129],"household"),
            ("minor_single_parent_share",.0176,"ratio"),("divorced_unmarried_share",.884,"ratio"),
            ("claim_holder_share",.213,"ratio"),("unpaid_claim_share",.259,"ratio"),
            ("children_per_claim",1.4,"person/household"),("advance_monthly_amount",200000,"KRW/person/month"),
            ("advance_months",12,"month/year"),("legacy_support_budget",1601000000,"KRW/year")],
        SYSTEM:[
            ("upgrade_components",{"functions":421000000,"data_linkage":219000000,"ocr":202000000,"audit_privacy":106000000},"component_to_KRW"),
            ("system_maintenance_rate",.15,"ratio/year"),("maintenance_start_offset",2,"year"),
            ("system_cpi",{"2028":.021,"2029":.021,"2030":.02},"year_to_ratio")]
    }
    for profile,values in data.items():
        for key,value,unit in values:
            rows.append(evidence_row(evidence_key=f"2201707:{profile}:{key}:reviewed",
                variable_key=key,value=value,unit=unit,source_bill_no="2201707",available_at="2024-08-12",reviewed_at="2026-10-09",
                source_ref="2201707 비용추계서24C1988 PDF4~7쪽;2021한부모실태조사·장래가구/여가부고도화계획인용",
                agency="여성가족부",policy_domain="양육비선지급",scope="지원자전원참고시나리오·기존양육비정보시스템고도화",
                service_function=profile,support_derivation=profile,child_support_model=profile,
                variable_role="advance_expense_operand",allowed_routes=["direct_annual_amount"],
                requires_applicability_note=True,independently_verified=False,obtained_from="reviewed_answer",
                **({"value_years":list(range(2026,2031))} if key=="household_forecast" else {}),
                limitation="역사적계획/조사비율·기존사업동결가정.최신공식실적아님.회수수입을지출에서상계하지않음"))
    return rows


def prepare_child_support(payload):
    profile=payload.get("support_derivation")
    if payload.get("route_key")!="direct_annual_amount" or payload.get("child_support_model")!=profile or profile not in {ADVANCE,SYSTEM}:
        raise ValueError("child-support expense model/route mismatch")
    if payload.get("fiscal_reporting")!="separate_revenue_and_expenditure" or not all(str(payload.get(k) or "").strip()
        for k in ("support_derivation_note","child_support_scope_note","estimation_start_note")):
        raise ValueError("child-support expense scope/timing and no-netting review required")
    if profile==ADVANCE and payload.get("statutory_standard_table_required") is True:
        if payload.get("advance_amount_basis")!="policy_fixed_proxy" or payload.get("proxy_assumption_confirmed") is not True or not all(
            str(payload.get(k) or "").strip() for k in ("proxy_basis_note","statutory_basis_difference_note")):
            return {**payload,"support_missing_operands":["policy_proxy_confirmation"],"support_derivation_trace":[]}
    policy_reference = profile == ADVANCE and (
        payload.get("delegated_eligibility_reference_required") is True
        or payload.get("advance_amount_basis") == "delegated_policy_reference"
        or any(str(key).endswith(":delegated_advance_policy_reference")
               for key in payload.get("selected_method_keys", []))
    )
    if policy_reference:
        notes = ("delegated_eligibility_note", "claim_amount_difference_note",
                 "reference_scenario_source", "legacy_transition_note")
        if (payload.get("advance_amount_basis") != "delegated_policy_reference"
                or payload.get("reference_scenario_confirmed") is not True
                or not all(str(payload.get(key) or "").strip() for key in notes)):
            return {**payload, "support_missing_operands": ["delegated_policy_reference_confirmation"],
                    "support_derivation_trace": []}
    start=payload.get("start_year");years=payload.get("years",5)
    if start is None:return {**payload,"support_missing_operands":["start_year"]}
    if isinstance(start,bool) or not isinstance(start,int) or isinstance(years,bool) or not isinstance(years,int) or years<1:
        raise ValueError("invalid child-support horizon")
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in ("recovery_rate","recovery_income","growth_rate","subsidy_rate")):
        raise ValueError("child-support revenue netting or duplicate growth forbidden")
    units=({"household_forecast":"household","minor_single_parent_share":"ratio","divorced_unmarried_share":"ratio",
        "claim_holder_share":"ratio","unpaid_claim_share":"ratio","children_per_claim":"person/household",
        "advance_monthly_amount":"KRW/person/month","advance_months":"month/year","legacy_support_budget":"KRW/year"}
        if profile==ADVANCE else {"upgrade_components":"component_to_KRW","system_maintenance_rate":"ratio/year",
            "maintenance_start_offset":"year","system_cpi":"year_to_ratio"})
    r,missing=resolve_formula_variables(tuple(units),**layers)
    if missing:return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    for k,row in r.items():
        vals=list(row.value.values()) if isinstance(row.value,dict) else row.value if isinstance(row.value,list) else [row.value]
        if row.unit!=units[k] or not row.source_ref or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x)
            or (x<=-1 if k=="system_cpi" else x<0) or (units[k].startswith("ratio") and x>1) for x in vals):
            raise ValueError("invalid child-support operand/unit")
    v={k:row.value for k,row in r.items()};annual=[];trace=[]
    if profile==ADVANCE:
        if payload.get("advance_take_up_scenario")!="all_eligible" or payload.get("claim_count_rounding")!="final_half_up":
            raise ValueError("advance registration and rounding scenario required")
        houses=v["household_forecast"]
        if not isinstance(houses,list) or len(houses)!=years:raise ValueError("household forecast horizon mismatch")
        if any(not isinstance(v[k],(int,float)) for k in units if k!="household_forecast") or v["advance_months"]>12:
            raise ValueError("advance scalars/months invalid")
        gates=("minor_single_parent_share","divorced_unmarried_share","claim_holder_share","unpaid_claim_share","children_per_claim")
        for i,h in enumerate(houses):
            raw=Decimal(str(h));stages={}
            for key in gates:
                raw*=Decimal(str(v[key]));stages[key]=float(raw)
            claims=int(raw.quantize(Decimal("1"),rounding=ROUND_HALF_UP))
            gross=claims*v["advance_monthly_amount"]*v["advance_months"]
            annual.append(gross-v["legacy_support_budget"])
            trace.append(dict(year=start+i,households=h,unrounded_stages=stages,advance_cases=claims,gross_expense=gross,
                legacy_budget=v["legacy_support_budget"],additional_expense=annual[-1],
                amount_basis=payload.get("advance_amount_basis","reviewed_reference"),
                statutory_basis_difference_note=payload.get("statutory_basis_difference_note"),
                reference_scenario_confirmed=payload.get("reference_scenario_confirmed", False),
                delegated_eligibility_note=payload.get("delegated_eligibility_note"),
                claim_amount_difference_note=payload.get("claim_amount_difference_note"),
                reference_scenario_source=payload.get("reference_scenario_source"),
                legacy_transition_note=payload.get("legacy_transition_note"),
                expression="round(가구×미성년한부모×이혼미혼×채권×미지급×자녀수)×월액×개월−기존지원예산;회수수입상계없음"))
    else:
        if not all(str(payload.get(k) or "").strip() for k in ("upgrade_scope_note","warranty_timing_note","maintenance_price_note")):
            raise ValueError("system upgrade/warranty/price reviews missing")
        components=v["upgrade_components"];rates=v["system_cpi"];offset=v["maintenance_start_offset"]
        if not isinstance(components,dict) or not components or not isinstance(rates,dict) or not isinstance(offset,(int,float)) or offset!=int(offset) or offset<1:
            raise ValueError("invalid system plan or warranty timing")
        offset=int(offset);build=sum(components.values());maintenance_base=build*v["system_maintenance_rate"]
        for i in range(years):
            maintenance=0
            if i>=offset:
                required=range(start+offset+1,start+i+1)
                if any(str(y) not in rates for y in required):
                    return {**payload,"support_missing_operands":["system_cpi_year_coverage"]}
                maintenance=maintenance_base*prod(1+rates[str(y)] for y in required)
            annual.append((build if i==0 else 0)+maintenance)
            trace.append(dict(year=start+i,build_expense=build if i==0 else 0,maintenance_expense=maintenance,
                warranty_or_no_charge=0<i<offset,first_maintenance_year=start+offset,
                expression="첫해기능별고도화예산합산,다음해무상보수,유지관리시작년15%이후물가"))
    calculated=dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"]=dict(value=annual,unit="KRW/year",is_assumption=True,
        source_ref="; ".join(dict.fromkeys(row.source_ref for row in r.values())))
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}
