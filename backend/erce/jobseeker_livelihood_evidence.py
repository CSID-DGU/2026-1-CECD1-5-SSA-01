"""Actual allowance payment frequency and previous-year livelihood floor."""
from math import isfinite
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs

PROFILE="jobseeker_livelihood_previous_year"


def jobseeker_rows():
    rows=[]
    for key,value,unit in (
        ("recognized_jobseekers",[219527,228929],"person"),
        ("iap_completion_rate",.98,"ratio"),
        ("average_payment_months",5.2,"month/year"),
        ("livelihood_floor_history",[512102,527158,548349,583444,623368],"KRW/person/month"),
    ):
        rows.append(evidence_row(evidence_key=f"2207706:{key}:reviewed",
            variable_key=key,value=value,unit=unit,source_bill_no="2207706",available_at="2025-02-17",
            reviewed_at="2026-10-06",source_ref="2207706 비용추계서25B0462 PDF4~6쪽 표2~3;고용노동부실적·복지부고시인용",
            agency="고용노동부",policy_domain="구직촉진수당",scope="국민취업지원제도I유형 인정인원·실지급",
            service_function=PROFILE,support_derivation=PROFILE,jobseeker_cohort="recognized_I_type",
            livelihood_floor_projection="historic_cagr_2019_2023",
            variable_role="historical_operand",allowed_routes=["transfer_recipient_delta"],
            requires_applicability_note=True,independently_verified=False,obtained_from="reviewed_answer",
            observation_years=[2022,2023] if key=="recognized_jobseekers" else [2019,2020,2021,2022,2023] if key=="livelihood_floor_history" else [2022,2023],
            limitation="당시관측치의평균/동결가정.전체구직자·II유형·법정최대6개월과다름.최신실적아님.원실적자료독립검증미완료"))
    rows.append(evidence_row(evidence_key="official:mohw:livelihood_floor:2025:single",
        variable_key="livelihood_floor_base",value=765444,unit="KRW/person/month",
        source_bill_no="official:mohw:livelihood_floor_2025",available_at="2025-07-09",
        reviewed_at="2026-10-06",source_ref="국가법령정보센터:보건복지부2025-07-09 기초생활수급 선정기준 및 급여중지 기준 해석",
        source_url="https://www.law.go.kr/LSW/cgmExpcInfoP.do?cgmExpcDatSeq=383956&mode=2&ofiClsCd=350116",
        agency="보건복지부",policy_domain="생계급여",scope="2025년1인가구생계급여최저보장수준",
        service_function="official_livelihood_floor",variable_role="official_reference_rate",
        source_class="official_standard",independently_verified=True,
        observation_year=2025,price_base_year=2025,requires_applicability_note=True,
        limitation="2025연도공식기준.뒤연도추계는관측치아닌가정.공개일은이번확인문서2025-07-09로보수적으로유지"))
    return rows


def prepare_jobseeker(payload):
    if payload.get("route_key")!="transfer_recipient_delta" or payload.get("jobseeker_cohort")!="recognized_I_type":
        raise ValueError("jobseeker allowance route/cohort mismatch")
    if payload.get("livelihood_floor_projection")!="historic_cagr_2019_2023":
        raise ValueError("jobseeker livelihood projection must be confirmed")
    if not all(str(payload.get(k) or "").strip() for k in ("support_derivation_note","payment_scope_note","floor_projection_note","estimation_start_note")):
        raise ValueError("jobseeker scope/projection/timing confirmations missing")
    start=payload.get("start_year")
    if start is None:return {**payload,"support_missing_operands":["start_year"]}
    base=payload.get("livelihood_floor_base_year");years=payload.get("years",5)
    if isinstance(base,bool) or not isinstance(base,int) or start!=base+1:
        raise ValueError("jobseeker first amount must use previous-year floor")
    offset=payload.get("historical_table_year_offset",0)
    if isinstance(offset,bool) or offset not in (0,1):
        raise ValueError("invalid historical table year offset")
    if offset and (payload.get("bill_no")!="2204843" or payload.get("evidence_mode")!="development_review"
            or not str(payload.get("source_year_discrepancy_note") or "").strip()):
        raise ValueError("unresolved table-year offset is own historical review only")
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in ("participation_rate","growth_rate","growth_rates_by_year")):
        raise ValueError("jobseeker duplicate rate/growth forbidden")
    units={"recognized_jobseekers":"person","iap_completion_rate":"ratio","average_payment_months":"month/year",
        "livelihood_floor_history":"KRW/person/month","livelihood_floor_base":"KRW/person/month"}
    r,missing=resolve_formula_variables(tuple(units),**layers)
    if missing:return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    for key,row in r.items():
        seq=row.value if isinstance(row.value,list) else [row.value]
        if row.unit!=units[key] or not row.source_ref or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x) or x<0 for x in seq):
            raise ValueError("jobseeker operand/unit/source mismatch")
    v={key:row.value for key,row in r.items()}
    if not isinstance(v["recognized_jobseekers"],list) or len(v["recognized_jobseekers"])!=2:
        raise ValueError("jobseeker needs 2022/2023 recognized counts")
    hist=v["livelihood_floor_history"]
    if not isinstance(hist,list) or len(hist)!=5 or hist[0]<=0 or hist[-1]<=0:
        raise ValueError("jobseeker needs positive 2019-2023 floor history")
    if isinstance(v["iap_completion_rate"],list) or not 0<=v["iap_completion_rate"]<=1 or isinstance(v["average_payment_months"],list) or not 0<=v["average_payment_months"]<=6:
        raise ValueError("jobseeker IAP or actual months outside allowance scope")
    if isinstance(v["livelihood_floor_base"],list):raise ValueError("floor base must be scalar")
    base_row=(payload.get("official_inputs") or {}).get("livelihood_floor_base") or (payload.get("selected_variable_inputs") or {}).get("livelihood_floor_base") or {}
    if base_row.get("price_base_year") is not None and base_row["price_base_year"]!=base:
        raise ValueError("floor base observation year mismatch")
    growth=(hist[-1]/hist[0])**.25-1
    count=sum(v["recognized_jobseekers"])/2*v["iap_completion_rate"]
    prices=[v["livelihood_floor_base"]*(1+growth)**(i+offset) for i in range(years)]
    source="; ".join(dict.fromkeys(row.source_ref for row in r.values()))
    calculated=dict(payload.get("calculated_inputs") or {})
    for key,value,unit in (("recipient_count",count,"person"),("benefit_per_recipient",prices,"KRW/person/month"),
            ("payments_per_year",v["average_payment_months"],"month/year")):
        if not any(key in (layer or {}) for layer in layers.values() if layer is not layers["precedent_assumption"]):
            calculated[key]=dict(value=value,unit=unit,source_ref=source,is_assumption=True)
    trace=[dict(year=start+i,floor_reference_year=start+i-1,table_price_reference_year=start+i-1+offset,
        historical_table_year_offset=offset,source_year_discrepancy_note=payload.get("source_year_discrepancy_note"),
        monthly_floor=p,history_cagr=growth,
        recognized_mean=sum(v["recognized_jobseekers"])/2,iap_rate=v["iap_completion_rate"],
        effective_recipients=count,payment_months=v["average_payment_months"],
        expression="평균인정인원×IAP수립률×평균지급개월×(전년도생계최저액−현행수당)") for i,p in enumerate(prices)]
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],"support_derivation_trace":trace}
