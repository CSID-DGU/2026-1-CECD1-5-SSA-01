"""Separate school eligibility cohorts and reuse component-specific rate evidence."""
from math import isfinite
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.teacher_staffing_evidence import PAY_PROFILE
from backend.erce.variable_evidence_store import evidence_payload_from_db
from backend.erce.engine import estimate_routed_item


def split_school_staffing_groups(large_public, meals_public, overlap_public, large_private):
    """A OR B: keep intersection in A once, never assume unknown overlap is zero."""
    counts = (large_public, meals_public, overlap_public, large_private)
    if any(isinstance(n, bool) or not isinstance(n, (int, float)) or not isfinite(n)
           or n < 0 or int(n) != n for n in counts):
        raise ValueError("학교 대상군 인원·중복 인원을 확인해야 합니다")
    if overlap_public > min(large_public, meals_public):
        raise ValueError("중복 인원이 대상군보다 큽니다")
    return {"large_public":int(large_public),
            "meals_public":int(meals_public-overlap_public),
            "large_private":int(large_private)}


def school_staffing_group_rows():
    common=dict(source_bill_no="2207986",available_at="2025-04-07",agency="교육부",
        policy_domain="영양교사 증원",service_function="규모 또는 다회급식 학교 증원",
        reviewed_at="2026-10-03",obtained_from="reviewed_answer",staff_pay_profile=PAY_PROFILE,
        requires_applicability_note=True,
        limitation="2025 추계서가 인용한 과거 교육부 통계·교원 전망. 최신 공식값 아님. 원 봉급표·기관부담 요율·통계 원자료는 별도 확인 필요")
    rows=[]
    for group,sector,count,year,basis in (
        ("large_public","public",1208,2024,"36학급 이상 국공립 초중고; 초924 중131 고153"),
        ("meals_public","public",813,2025,"하루2회 이상 급식 국공립; 규모 기준과 중복 없음은 정답의 가정"),
        ("large_private","private",91,2024,"36학급 이상 사립 초중고; 초1 중2 고88"),
    ):
        rows.append(evidence_row(**common,evidence_key=f"2207986:{group}:headcount",
            variable_key="headcount",value=count,unit="person",scope=basis,
            variable_role="target_quantity",reuse_policy="target_only",observation_year=year,
            school_sector=sector,staffing_target_group=group,
            source_ref="2207986 비용추계서25C0723 PDF p.5,7~8 표2·6·9",
            allowed_routes=["personnel_average","personnel_asset","personnel_employer_contribution"],
            incremental_per_school=1,population_projection="대상학교 수5년 동결; 기존 배치 및 중복은 별도 확인"))
    for suffix,key,value,unit,sector,component,route,basis in (
        ("salary_public","salary_per_person",[34491000,35535000,36378000,37219000,38436000],
         "KRW/person/year","public","salary","personnel_average","표3 임금+연간 수당606만원;2급8~12호봉"),
        ("salary_private","salary_per_person",[34491000,35535000,36378000,37219000,38436000],
         "KRW/person/year","private","private_pension","personnel_employer_contribution","사립 보수는 동일 봉급·수당, 표3·7; 기본경비·자산 제외"),
        ("employer_cost","unit_cost",[4507000,4666000,4800000,4945000,5143000],
         "KRW/person/year","public","employer_cost","quantity_unit","표3 기관부담액; 부담률 역산하지 않음"),
        ("private_pension_rate","employer_contribution_rate",.03706,
         "ratio","private","private_pension","personnel_employer_contribution","본문·표7 인용 사학연금 국가부담률;원법령의 최신 여부는 별도 검증"),
        ("asset_duration","duration",1,
         "year","public","initial_asset","personnel_asset","신규 채용 첫해만 집기 구입하는 선례 가정"),
    ):
        rows.append(evidence_row(**common,evidence_key=f"2207986:{suffix}",variable_key=key,
            value=value,unit=unit,scope=f"{sector} 신규 영양교사",variable_role="rate_assumption",
            school_sector=sector,personnel_cost_component=component,allowed_routes=[route],
            cost_basis=basis,value_years=[2026,2027,2028,2029,2030],
            source_ref="2207986 비용추계서25C0723 PDF p.5~7 표3·7",
            rounded_precision_won=1000 if suffix.startswith("salary") or suffix=="employer_cost" else None))
    rows.append(evidence_row(**common,evidence_key="2207986:classroom_threshold_assumption",
        variable_key="classroom_threshold",value=36,unit="classroom/school",scope="초중고 규모 기준 가정",
        variable_role="eligibility_assumption_candidate",requires_user_confirmation=True,
        allowed_routes=["personnel_average"],
        source_ref="2207986 비용추계서 PDF p.3: 학교보건법 보건교사 배치기준 및2120470 선례 준용",
        cost_basis="영양교사 법정 확정 기준 아님. 새 의안에서 동일 기준 채택 여부 확인"))
    return rows


def estimate_school_staffing_groups(common, groups, overlap, overlap_source_ref):
    """Engine wiring: groups contain checked headcount evidence + rate IDs.

    Caller/AI selects evidence; rates and quantities are hydrated through the
    same source, self-exclusion, scope and year gates as individual ERCE items.
    """
    if not str(overlap_source_ref).strip():
        raise ValueError("중복 인원 근거 또는 확인된 시나리오 가정이 필요합니다")
    if set(groups)!={"large_public","meals_public","large_private"}:
        raise ValueError("학교 규모·다회급식 및 공사립 대상군 구분이 필요합니다")
    hydrated={}
    for group,config in groups.items():
        sector="private" if group=="large_private" else "public"
        p=evidence_payload_from_db(dict(common,route_key="personnel_average" if sector=="public"
            else "personnel_employer_contribution",school_sector=sector,staffing_target_group=group,
            selected_evidence_keys=[config["headcount_key"]]))
        hydrated[group]=p["selected_variable_inputs"]["headcount"]["value"]
    counts=split_school_staffing_groups(hydrated["large_public"],hydrated["meals_public"],
                                       overlap,hydrated["large_private"])
    parts={}
    for group,config in groups.items():
        sector="private" if group=="large_private" else "public"
        def run(route,component,keys,inputs):
            return estimate_routed_item(dict(common,route_key=route,school_sector=sector,
                staffing_target_group=group,personnel_cost_component=component,
                selected_evidence_keys=keys,calculated_inputs=inputs))
        count=dict(value=counts[group],unit="person",
                   source_ref=f"{config['headcount_key']}; 중복차감 근거:{overlap_source_ref}")
        if sector=="private":
            base=evidence_payload_from_db(dict(common,route_key="personnel_employer_contribution",
                school_sector=sector,personnel_cost_component="private_pension",
                selected_evidence_keys=[config["salary_key"]]))["selected_variable_inputs"]["salary_per_person"]
            payroll=[counts[group]*v for v in base["value"]]
            parts[group+":private_pension"]=run("personnel_employer_contribution","private_pension",
                [config["pension_rate_key"]],{"annual_salary_amount":dict(value=payroll,
                unit="KRW/year",source_ref=f"{count['source_ref']} × {base['source_ref']}")})
            continue
        salary=run("personnel_average","salary",[config["salary_key"]],{"headcount":count})
        burden=run("quantity_unit","employer_cost",[config["employer_cost_key"]],{"quantity":count})
        payroll=[(a+b)*1000 for a,b in zip(salary.annual_amounts_thousand,burden.annual_amounts_thousand)]
        basic=run("personnel_basic_expense","basic_expense",[config["basic_ratio_key"]],
                  {"annual_salary_amount":dict(value=payroll,unit="KRW/year",
                    source_ref=f"{group} 보수+기관부담금 계산;{config['salary_key']};{config['employer_cost_key']}")})
        asset=run("personnel_asset","initial_asset",[config["asset_key"],config["asset_duration_key"]],
                  {"headcount":count})
        parts.update({group+":salary":salary,group+":employer_cost":burden,
                      group+":basic_expense":basic,group+":initial_asset":asset})
    annual=[sum(r.annual_amounts_thousand[i] for r in parts.values()) for i in range(common["years"])]
    return dict(components={k:list(v.annual_amounts_thousand) for k,v in parts.items()},
        source_refs={k:list(v.source_refs) for k,v in parts.items()},
        effective_headcounts=counts,overlap_public=overlap,overlap_source_ref=overlap_source_ref,
        annual_amounts_thousand=annual,total_thousand=sum(annual),
        excluded_scope="다회급식 사립학교·유치원·특수·대안학교 및 사립 재정결함보조는 이 구성에 미포함; 비용0 확정 아님")


def reviewed_school_groups_replay(db_path):
    common=dict(bill_no="2207986",start_year=2026,years=5,cutoff_date="2026-10-03",
        evidence_mode="development_review",variable_db_path=db_path,staff_pay_profile=PAY_PROFILE,
        evidence_selection_reasons={
            "2200601:basic_ratio":"교육비특별회계 동일 기본경비 기준.2025 정확한 비율 미확보로2024 비율6.54%를 참고 가정 사용; 최신값 아님",
            "2212273:asset_price_per_person:2026":"2026년 정부기관1인당 집기 전망 준용. 원자료 독립 확인 전 참고 단가이며 정답 총액 역산하지 않음"})
    groups={}
    for group in ("large_public","meals_public"):
        groups[group]=dict(headcount_key=f"2207986:{group}:headcount",salary_key="2207986:salary_public",
            employer_cost_key="2207986:employer_cost",basic_ratio_key="2200601:basic_ratio",
            asset_key="2212273:asset_price_per_person:2026",asset_duration_key="2207986:asset_duration")
    groups["large_private"]=dict(headcount_key="2207986:large_private:headcount",
        salary_key="2207986:salary_private",pension_rate_key="2207986:private_pension_rate")
    result=estimate_school_staffing_groups(common,groups,0,"2207986 추계서 PDF p.3: 두 조건 중복 없음의 확인된 선례 가정")
    result.update(evaluation_type="post_answer_development_regression",
        limitation="해당 의안 정답의 인원·단가 사용한 회귀시험. 기본경비는 과거 선례 비율; 중복0은 관측 아닌 가정")
    return result
