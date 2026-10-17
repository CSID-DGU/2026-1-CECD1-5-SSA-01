"""Opt-in historical eligibility expansion and weighted benefit scenarios.

No target total is used to derive counts or rates. The historical frozen-count
scenario is distinct from the answer's population/share trend forecast.
"""
from math import isfinite, prod

from backend.erce.disability_couple_evidence import disability_couple_rows
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs

PROFILE = "disability_eligibility_expansion"
SCOPE = "severe_grade3_single_incremental_18plus"


def disability_expansion_rows():
    groups = [
        dict(name="18~64세 재가", count=120867, basic=1, indexed_supplement=0, fixed_supplement=90000, couple=True),
        dict(name="18~64세 시설", count=20347, basic=1, indexed_supplement=0, fixed_supplement=0, couple=False),
        dict(name="18~64세 차상위", count=6871, basic=1, indexed_supplement=0, fixed_supplement=80000, couple=False),
        dict(name="18~64세 차상위초과", count=71393, basic=1, indexed_supplement=0, fixed_supplement=30000, couple=False),
        dict(name="65세이상 재가", count=52556, basic=0, indexed_supplement=1, fixed_supplement=90000, couple=False),
        dict(name="65세이상 시설", count=5605, basic=0, indexed_supplement=0, fixed_supplement=0, couple=False),
        dict(name="65세이상 시설특례", count=1356, basic=0, indexed_supplement=0, fixed_supplement=80000, couple=False),
        dict(name="65세이상 차상위", count=7524, basic=0, indexed_supplement=0, fixed_supplement=80000, couple=False),
        dict(name="65세이상 차상위초과", count=67137, basic=0, indexed_supplement=0, fixed_supplement=30000, couple=False),
        dict(name="65세이상 차상위특례", count=1438, basic=0, indexed_supplement=0, fixed_supplement=150000, couple=False),
    ]
    rows=[]
    for name,value,unit in (
        ("expanded_eligible_reference",904029,"person"),
        ("existing_eligible_reference",508975,"person"),
        ("disability_take_up",.7059,"ratio"),
        ("disability_benefit_groups",groups,"cohort_bundle"),
        ("expansion_cpi",[.022,.022,.021,.021,.021],"ratio/year"),
        ("existing_couple_reduction",.2,"ratio"),
    ):
        rows.append(evidence_row(evidence_key=f"2203497:{name}:scenario_2023",
            variable_key=name,value=value,unit=unit,source_bill_no="2203497",
            available_at="2026-10-06",reviewed_at="2026-10-06",
            source_ref="2203497 비용추계서24C2651 PDF4~6쪽 표2·3·5 및 전제",
            agency="국회예산정책처",policy_domain="장애인연금",scope=SCOPE,
            service_function=PROFILE,variable_role="assumption",support_derivation=PROFILE,
            allowed_routes=["transfer_recipient"],requires_applicability_note=True,
            disability_benefit_scope=SCOPE,
            **({"disability_population_basis":"freeze_2023_eligibility_delta"} if name in ("expanded_eligible_reference","existing_eligible_reference") else {}),
            disability_composition_basis="table_2023_frozen",
            disability_cpi_basis="table_application_years_2025_2029",
            valid_from_year=2025,valid_to_year=2029,
            **({"value_years":list(range(2025,2030))} if name=="expansion_cpi" else {}),
            obtained_from="reviewed_answer",independently_verified=False,
            source_reply_date="2024-08-23",source_bill_version_match=False,
            historical_current_eligible=[521180,520176,518705,514409,508975],
            historical_expanded_eligible=[921379,920329,918341,914254,904029],
            historical_years=list(range(2019,2024)),
            limitation="2023실적 인원·구성비동결 후보이며 정답의 추세전망 아님. 회답일이발의일보다앞서 이용가능일은확인일. 본문2022구성비/표2023 및65세차상위초과 표3만원/주석5만원 불일치: 표본체3만원을 선택한 시나리오만 지원. 최신통계로 취급금지"))
    original = next(r for r in disability_couple_rows() if r["variable_key"]=="disability_base_monthly")
    rows.append({**original,"evidence_key":original["evidence_key"]+":expansion",
        "alias_of":original["evidence_key"],"support_derivation":PROFILE,
        "disability_benefit_scope":SCOPE,"allowed_routes":["transfer_recipient"],"reviewed_at":"2026-10-06"})
    original = next(r for r in disability_couple_rows() if r["variable_key"]=="disability_couple_share")
    rows.append({**original,"evidence_key":original["evidence_key"]+":expansion",
        "alias_of":original["evidence_key"],"support_derivation":PROFILE,
        "disability_benefit_scope":SCOPE,"allowed_routes":["transfer_recipient"],"reviewed_at":"2026-10-06"})
    rows.append(projected_recipient_row())
    return rows


def projected_recipient_row():
    from backend.erce.common_population_evidence import population_series
    historical_adult=population_series("adult_population",2019,5)
    old=[521180,520176,518705,514409,508975]
    new=[921379,920329,918341,914254]
    def forecast(counts,denominators):
        ratios=[n/d for n,d in zip(counts,denominators)]
        xs=list(range(2019,2019+len(ratios)));xm=sum(xs)/len(xs);ym=sum(ratios)/len(ratios)
        slope=sum((x-xm)*(y-ym) for x,y in zip(xs,ratios))/sum((x-xm)**2 for x in xs)
        return [ym+slope*(year-xm) for year in range(2025,2030)],ratios
    old_ratio,old_history=forecast(old,historical_adult)
    new_ratio,new_history=forecast(new,historical_adult[:4])
    adult=population_series("adult_population",2025,5)
    if any(not 0<=o<=n<=1 for o,n in zip(old_ratio,new_ratio)):
        raise ValueError("invalid projected eligibility ratios")
    values=[p*(n-o)*.7059 for p,n,o in zip(adult,new_ratio,old_ratio)]
    return evidence_row(evidence_key="2203497:recipient_count:official_population_linear_trend",
        variable_key="recipient_count",value=values,unit="person",
        source_bill_no="2203497",available_at="2026-10-06",reviewed_at="2026-10-06",
        source_ref="KOSIS DT_1BPA001 2023.12 중위전망18세이상 +2203497 PDF4쪽표2 수급권자실적,OLS비율추세 및70.59%",
        agency="통계청·국회예산정책처",policy_domain="장애인연금",scope=SCOPE,
        service_function=PROFILE,variable_role="derived_population",support_derivation=PROFILE,
        disability_benefit_scope=SCOPE,disability_population_basis="official_population_linear_ratio_trend",
        value_years=list(range(2025,2030)),allowed_routes=["transfer_recipient"],
        requires_applicability_note=True,independently_verified=False,obtained_from="official_population_and_reviewed_counts",
        source_bill_version_match=False,
        calculation_trace=dict(adult_population=adult,historical_adult_population=historical_adult,
            historical_existing_counts=old,historical_expanded_counts=new,
            historical_existing_ratios=old_history,historical_expanded_ratios=new_history,
            existing_projected_ratios=old_ratio,expanded_projected_ratios=new_ratio,take_up=.7059,
            expression="18세이상공식전망×(확대후비율OLS추세−현행비율OLS추세)×70.59%"),
        source_url="https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1BPA001",
        limitation="인원동결아님.OLS를명시한후보이며정답이사용한구체추세모형은미확인.비율실적은정답에서확인.원문버전불일치검토필수")


def prepare_disability_expansion(payload):
    expected=dict(route_key="transfer_recipient",disability_benefit_scope=SCOPE,
        disability_composition_basis="table_2023_frozen",
        disability_cpi_basis="table_application_years_2025_2029",benefit_index_base_year=2024,
        start_year=2025,years=5)
    if any(payload.get(k)!=v for k,v in expected.items()):
        raise ValueError("disability expansion needs matching scope, frozen scenario, base and period")
    if payload.get("disability_population_basis") not in {"freeze_2023_eligibility_delta","official_population_linear_ratio_trend"}:
        raise ValueError("unknown disability population scenario")
    if any(not str(payload.get(k) or "").strip() for k in (
        "population_proxy_note","support_derivation_note","composition_conflict_note","estimation_start_note")):
        raise ValueError("disability expansion needs population and conflicting source scenario notes")
    if payload.get("supplementary_benefit_policy_unchanged") is not True:
        raise ValueError("expansion assumes existing benefit rules remain unchanged")
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if payload.get("disability_population_basis")=="official_population_linear_ratio_trend":
        provided,_=resolve_formula_variables(("recipient_count",),**layers)
        if "recipient_count" not in provided:
            raise ValueError("projected population scenario requires sourced forecast counts, not frozen fallback")
    if any(k in (l or {}) for l in layers.values() for k in ("participation_rate","growth_rate","growth_rates_by_year")):
        raise ValueError("disability expansion duplicate adjustment forbidden")
    units=dict(expanded_eligible_reference="person",existing_eligible_reference="person",
        disability_take_up="ratio",disability_benefit_groups="cohort_bundle",expansion_cpi="ratio/year",
        disability_base_monthly="KRW/person/month",disability_couple_share="ratio",existing_couple_reduction="ratio")
    resolved,missing=resolve_formula_variables(tuple(units),**layers)
    data={}
    for key,row in resolved.items():
        if row.unit!=units[key] or not row.source_ref:raise ValueError("invalid expansion unit/source")
        if key=="disability_benefit_groups":
            groups=row.value
            if not isinstance(groups,(list,tuple)) or not groups:raise ValueError("missing benefit groups")
            for g in groups:
                if not isinstance(g,dict) or not isinstance(g.get("name"),str) or not isinstance(g.get("couple"),bool):raise ValueError("invalid benefit group")
                for field in ("count","basic","indexed_supplement","fixed_supplement"):
                    v=g.get(field)
                    if isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) or v<0:raise ValueError("invalid benefit group value")
                if g["basic"] not in (0,1) or g["indexed_supplement"] not in (0,1) or g["basic"]+g["indexed_supplement"]>1:
                    raise ValueError("basic and indexed supplement double counting")
                if g["couple"] and not g["basic"]:raise ValueError("couple reduction only applies to basic benefit")
            if sum(g["count"] for g in groups)<=0:raise ValueError("empty cohort population")
            data[key]=groups;continue
        vals=list(row.value) if isinstance(row.value,(list,tuple)) else [row.value]*5
        if len(vals)!=5 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v)
             or (v<=-1 if key=="expansion_cpi" else v<0) or (units[key]=="ratio" and v>1) for v in vals):raise ValueError("invalid expansion operand")
        if key in ("expanded_eligible_reference","existing_eligible_reference","disability_base_monthly") and len(set(vals))!=1:
            raise ValueError("frozen reference must be fixed")
        data[key]=vals
    if all(k in data for k in ("expanded_eligible_reference","existing_eligible_reference")) and any(
        a<b for a,b in zip(data["expanded_eligible_reference"],data["existing_eligible_reference"])):
        raise ValueError("expanded eligibility smaller than existing")
    deps=dict(recipient_count=("expanded_eligible_reference","existing_eligible_reference","disability_take_up"),
        benefit_per_recipient=("disability_benefit_groups","disability_base_monthly","expansion_cpi","disability_couple_share","existing_couple_reduction"))
    calculated=dict(payload.get("calculated_inputs") or {});trace=[]
    for key,dependencies in deps.items():
        if not all(k in data for k in dependencies):continue
        if key=="recipient_count":
            values=[(data["expanded_eligible_reference"][i]-data["existing_eligible_reference"][i])*data["disability_take_up"][i] for i in range(5)]
            expression="(확대대상2023실적−현행대상2023실적)×수급률; 동결후보"
        else:
            groups=data["disability_benefit_groups"];total=sum(g["count"] for g in groups);values=[]
            for i in range(5):
                base=data["disability_base_monthly"][i]*prod(1+r for r in data["expansion_cpi"][:i+1])
                values.append(sum(g["count"]*(base*(g["basic"]*(1-data["disability_couple_share"][i]*data["existing_couple_reduction"][i] if g["couple"] else 1)+g["indexed_supplement"])+g["fixed_supplement"]) for g in groups)/total)
            expression="Σ(유형별인원비중×(기초급여·기초연동부가급여·고정부가급여)); 기초에만부부감액"
        upper,_=resolve_formula_variables((key,),**{**layers,"calculated_estimate":calculated})
        ref="; ".join(dict.fromkeys(resolved[d].source_ref for d in dependencies))
        unit="person" if key=="recipient_count" else "KRW/person/month"
        if key not in upper:calculated[key]=dict(value=values,unit=unit,source_ref=ref,is_assumption=True)
        trace.append(dict(variable_key=key,expression=expression,dependencies=list(dependencies),values=values,unit=unit,source_ref=ref,applied=key not in upper))
    _,top_missing=resolve_formula_variables(tuple(deps),**{**layers,"calculated_estimate":calculated})
    needed={d for k in top_missing for d in deps[k]}
    return {**payload,"calculated_inputs":calculated,"support_derivation_trace":trace,"support_missing_operands":[k for k in missing if k in needed]}
