"""Classroom capacity shortfalls, not whole new schools or teacher headcounts."""
from math import ceil,isfinite,prod
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs

PROFILE="special_classroom_expansion"
NOTES=("classroom_scope_note","classroom_stock_note","classroom_precision_note","classroom_price_note")
INDEX_ORIGINAL_URL="https://www.kostat.go.kr/boardDownload.es?bid=213&list_no=425820&seq=6"
INDEX_REVISED_URL="https://sri.kostat.go.kr/boardDownload.es?bid=213&list_no=431622&seq=11"


def special_classroom_rows():
    common=dict(source_bill_no="2205721",available_at="2024-12-02",reviewed_at="2026-10-11",
        source_ref="2205721 비용추계서24C5227 PDF4~7쪽",agency="교육부",policy_domain="특수교육 학급증설",
        scope="초등·고등 특수학교 및 일반학교특수학급, 유휴공간 증개축·사립동일지원 가정",
        service_function=PROFILE,support_derivation=PROFILE,allowed_routes=[PROFILE],variable_role="classroom_operand",
        requires_applicability_note=True,independently_verified=False,obtained_from="reviewed_answer",
        limitation="과거학생수·배치비율·학급성장 동결의 선례 가정. 전국단위 자료한계, 교원증원·새학교신축비 미포함")
    students={"elementary":dict(zip(map(str,range(2019,2025)),[41091,43205,44814,48448,51585,54283])),
              "high":dict(zip(map(str,range(2019,2025)),[20502,20655,20169,19867,20725,22040]))}
    stock={stage:{group:dict(zip(map(str,range(2021,2025)),counts)) for group,counts in groups.items()}
        for stage,groups in dict(elementary=dict(special=[1793,1871,1970,2017],general=[6330,6701,7038,7360]),
                                 high=dict(special=[1165,1149,1187,1221],general=[1932,1926,1955,2020])).items()}
    specs=[("special_student_history",students,"stage_year_to_person"),
        ("special_placement_2024",dict(elementary=dict(special=10316,general=35042),high=dict(special=6895,general=11185)),"stage_group_to_person"),
        ("special_class_stock_history",stock,"stage_group_year_to_class"),
        ("classroom_base_unit_price",50000000,"KRW/class"),("classroom_price_base_year",2022,"year"),
        ("classroom_cpi_rates",{str(y):v for y,v in [(2024,.025),(2025,.021),(2026,.02),(2027,.02),(2028,.02),(2029,.02),(2030,.02)]},"year_to_ratio"),
        ("class_need_rounding_digits",2,"decimal_digits")]
    rows=[evidence_row(**common,evidence_key=f"2205721:{k}:reviewed",variable_key=k,value=v,unit=u) for k,v,u in specs]
    rows[-1]["limitation"]="학급수 표7~8 대조로 선택한 소수2자리 정리 후 올림 가정. 문서에 명시된 공식 반올림 규칙 아님. 사용자확인·엄격올림 비교 필요"
    rows[-2]["limitation"]="2024.11전망 사례2203830의2024~2029률 준용 및2030도2%유지 가정. 원정답 CPI정밀도·연장정책 미명시"
    official={**common,"source_bill_no":"official:kostat:cpi_historical_indices",
        "source_class":"official_standard","independently_verified":True,"obtained_from":"official_public_data"}
    for key,year,value,basis,url,at in (
        ("classroom_index_2022",2022,107.71,"reviewed_historical_bridge",INDEX_ORIGINAL_URL,"2023-06-02"),
        ("classroom_index_2022",2022,107.72,"consistent_2024_vintage",INDEX_REVISED_URL,"2024-07-02"),
        ("classroom_index_2023",2023,111.59,None,INDEX_REVISED_URL,"2024-07-02")):
        rows.append(evidence_row(**{**official,"available_at":at,"source_ref":f"통계청 소비자물가 보도자료 {at}: 총지수2020=100, 해당연도{year}",
            "source_url":url,"limitation":"독립확인 공표값.2022지수는가중치개편으로107.71→107.72 수정. 다른발표버전 지수연결은 별도승인할 가정"},
            evidence_key=f"official:kostat:{key}:{basis or '2024_vintage'}",variable_key=key,value=value,unit="index_2020_100",
            **({"classroom_price_basis":basis} if basis else {})))
    return rows


def prepare_special_classrooms(payload):
    if payload.get("route_key")!=PROFILE:
        raise ValueError("classroom expansion route required")
    basis=payload.get("classroom_price_basis","consistent_2024_vintage")
    if basis not in {"consistent_2024_vintage","reviewed_historical_bridge"}:
        raise ValueError("unknown historical price-index basis")
    if payload.get("classroom_scenario_confirmed") is not True or not all(str(payload.get(k) or "").strip() for k in NOTES):
        return {**payload,"support_missing_operands":["classroom_confirmation"],"support_derivation_trace":[]}
    if basis=="reviewed_historical_bridge" and payload.get("price_index_bridge_confirmed") is not True:
        return {**payload,"support_missing_operands":["price_index_vintage_confirmation"],"support_derivation_trace":[]}
    if basis=="reviewed_historical_bridge" and (payload.get("estimate_purpose")!="reference_scenario" or not str(payload.get("reference_notice") or "").strip()):
        raise ValueError("cross-vintage price indices require a labelled reference scenario")
    policy=payload.get("classroom_rounding_policy","strict_ceiling")
    if policy not in {"strict_ceiling","reviewed_two_decimal_ceiling"}:
        raise ValueError("unknown capacity rounding policy")
    if policy!="strict_ceiling" and payload.get("class_precision_assumption_confirmed") is not True:
        return {**payload,"support_missing_operands":["class_rounding_confirmation"],"support_derivation_trace":[]}
    start,years=payload.get("start_year"),payload.get("years",5)
    if isinstance(start,bool) or not isinstance(start,int) or start<2025 or isinstance(years,bool) or not isinstance(years,int) or years<1:
        raise ValueError("classroom horizon required after2024 observations")
    units={r["variable_key"]:r["unit"] for r in special_classroom_rows() if r.get("classroom_price_basis") in (None,basis)}
    if policy=="strict_ceiling":
        units.pop("class_need_rounding_digits")
    units["special_new_class_caps"]="stage_to_person/class"
    r,missing=resolve_formula_variables(tuple(units),target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),precedent_assumption=selected_precedent_inputs(payload))
    if missing:
        return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    def numeric(x):
        return all(numeric(v) for v in x.values()) if isinstance(x,dict) else not isinstance(x,bool) and isinstance(x,(int,float)) and isfinite(x) and x>=0
    if any(row.unit!=units[k] or not row.source_ref or not numeric(row.value) for k,row in r.items()):
        raise ValueError("invalid classroom inputs/unit")
    v={k:row.value for k,row in r.items()};students=v["special_student_history"];stock=v["special_class_stock_history"];placement=v["special_placement_2024"];caps=v["special_new_class_caps"]
    stages={"elementary","high"};groups={"special","general"}
    if any(not isinstance(x,dict) or set(x)!=stages for x in (students,stock,placement,caps)):
        raise ValueError("both school stages required")
    if v["classroom_price_base_year"]!=2022 or min(v["classroom_index_2022"],v["classroom_index_2023"])<=0:
        raise ValueError("reviewed2022 construction price and positive indices required")
    for stage in stages:
        if (set(students[stage])!=set(map(str,range(2019,2025))) or students[stage]["2019"]<=0
                or set(stock[stage])!=groups or set(placement[stage])!=groups or caps[stage]<1 or caps[stage]!=int(caps[stage])):
            raise ValueError("invalid stage histories/capacity")
        if any(set(stock[stage][g])!=set(map(str,range(2021,2025))) or stock[stage][g]["2021"]<=0 for g in groups):
            raise ValueError("class stock observations must cover2021~2024")
        if sum(placement[stage].values())>students[stage]["2024"]:
            raise ValueError("placement exceeds total students")
    digits=v.get("class_need_rounding_digits",2)
    if policy!="strict_ceiling" and digits!=2:
        raise ValueError("reviewed rounding policy requires two decimal places")
    growth={s:(students[s]["2024"]/students[s]["2019"])**.2-1 for s in stages}
    installed={s:{g:round(stock[s][g]["2024"]*(stock[s][g]["2024"]/stock[s][g]["2021"])**((start-2024)/3)) for g in groups} for s in stages}
    annual=[];trace=[];rates=v["classroom_cpi_rates"]
    for year in range(start,start+years):
        if not isinstance(rates,dict) or any(str(y) not in rates for y in range(2024,year+1)):
            return {**payload,"support_missing_operands":["classroom_price_year_coverage"],"support_derivation_trace":[]}
        price=v["classroom_base_unit_price"]*v["classroom_index_2023"]/v["classroom_index_2022"]*prod(1+rates[str(y)] for y in range(2024,year+1))
        parts=[];total=0
        for s in sorted(stages):
            for g in sorted(groups):
                pupils=placement[s][g]*(1+growth[s])**(year-2024);raw_need=pupils/caps[s]
                need=ceil(round(raw_need,int(digits)) if policy!="strict_ceiling" else raw_need)
                old=installed[s][g];new=max(need-old,0);installed[s][g]+=new;total+=new
                parts.append(dict(stage=s,school_group=g,pupil_forecast=pupils,capacity=caps[s],raw_class_need=raw_need,
                    needed_classes=need,installed_before=old,new_classes=new,installed_after=installed[s][g]))
        amount=total*price;annual.append(amount)
        trace.append(dict(year=year,groups=parts,new_classes=total,unit_price_won=price,amount_won=amount,
            price_basis=basis,rounding_policy=policy,teacher_cost_status="separate_review_required"))
    calculated=dict(payload.get("calculated_inputs") or {})
    calculated["annual_amount"]=dict(value=annual,unit="KRW/year",is_assumption=True,source_ref="; ".join(dict.fromkeys(row.source_ref for row in r.values())))
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}
