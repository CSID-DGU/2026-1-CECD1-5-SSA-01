"""Reviewed military-noise case inputs; target quantities are not tariffs."""
from backend.erce.reviewed_variable_rows import evidence_row

YEARS=[2026,2027,2028,2029,2030]


def noise_support_specs():
    specs=[]
    for zone,old,new,baseline,prices in (
        (1,18347,18890,36803,[39286,40072,40873,41691,42524]),
        (2,93722,96500,27799,[29674,30267,30873,31490,32120]),
        (3,341461,351583,18151,[19375,19763,20158,20561,20973]),
    ):
        specs.append((f"zone{zone}","transfer_population_amount_delta",{
            "existing_recipient_count":(old,"person",True),
            "new_recipient_count":(new,"person",True),
            "benefit_per_recipient":(prices,"KRW/person/month",False),
            "existing_benefit_per_recipient":(baseline,"KRW/person/month",False),
            "payments_per_year":(12,"month/year",False)},"5~10"))
    for name,quantity,prices in (
        ("sound_house",254799,[29,31,33,35,38]),
        ("sound_school",121,[970,1032,1098,1167,1242]),
        ("sound_other",626,[97,103,110,117,124]),
        ("cool_house",254799,[3.7,3.7,3.8,3.9,3.9]),
        ("cool_school",0,[1993,2035,2077,2121,2151]),
        ("cool_other",626,[199,203,208,212,215]),
    ):
        specs.append((name,"capital_phased_installation",{
            "total_installation_quantity":(quantity,"facility",True),
            "installation_years":(10,"year",False),
            "installation_unit_cost":([round(p*1000000) for p in prices],"KRW/facility",False)},"7~12"))
    for name,quantity,price in (("tv_fee",290242,30000),("electric_house",290242,200000),
                               ("electric_school",121,15000000),("electric_other",626,1300000)):
        specs.append((name,"quantity_unit",{"quantity":(quantity,"facility",True),
            "unit_cost":(price,"KRW/facility/year",False)},"7~12"))
    return specs


def noise_support_rows():
    rows=[]
    for kind,route,values,page in noise_support_specs():
        for key,(value,unit,target) in values.items():
            rows.append(evidence_row(
                evidence_key=f"2203380:{kind}:{key}:2024",variable_key=key,value=value,unit=unit,
                source_bill_no="2203380",available_at="2024-10-28",
                source_ref=f"2203380 비용추계서 24D3202, PDF p.{page}",
                agency="국방부",policy_domain="군 소음피해 지원",scope=f"군 소음대책 {kind}",
                service_function=kind,variable_role="target_quantity" if target else "support_assumption",
                reuse_policy="target_only" if target else "comparable",reviewed_at="2026-10-03",
                obtained_from="reviewed_answer",requires_applicability_note=True,
                allowed_routes=[route],noise_support_component=kind,
                value_years=YEARS if isinstance(value,list) else None,
                observation_year=2007 if target and not kind.startswith("zone") else (2023 if target else None),
                quantity_basis=(
                    "학교 냉방은 교육부 기존 지원으로 순증 제외" if kind=="cool_school" else
                    "거주 인구" if kind.startswith("zone") else "세대" if kind in {"tv_fee","electric_house"} else "시설·가옥"),
                limitation="선례의 민간공항 2024년 지원단가를 군 소음 사업에 준용한 가정. 미래 단가는 공식 확정값 아님. 시설 물량은 2007년 자료여서 최신 현황 아님. 대상·기간·지원방식 확인 필수",
                derivation="표12의 반올림 표시 단가를 직접 사용; CPI로 원 단가를 재산출한 것은 아님" if isinstance(value,list) else
                           "표4·8 대상자 수" if kind.startswith("zone") and target else "표6·10·11 및 본문의 선례 가정",
            ))
    rows.append(evidence_row(
        evidence_key="2203380:resident_support:ratio:2024",variable_key="related_project_ratio",
        value=.268,unit="ratio",source_bill_no="2203380",available_at="2024-10-28",
        source_ref="2203380 비용추계서 PDF p.8·13: 소음대책사업 대비 주민지원사업 비율 26.8%",
        agency="국방부",policy_domain="군 소음피해 지원",scope="군 소음대책 주민지원사업",
        service_function="소음대책 연관 주민지원",variable_role="related_budget_ratio_assumption",
        reuse_policy="comparable",reviewed_at="2026-10-03",obtained_from="reviewed_answer",
        requires_applicability_note=True,allowed_routes=["related_project_ratio"],
        noise_support_component="resident_support",
        limitation="민간공항 중기계획 비율 준용 가정이며 국가 공통 보조율 아님. 기준사업비에 주민지원비를 먼저 포함하면 중복 발생. 지역 밖 미특정 사업은 제외",
    ))
    return rows


def reviewed_noise_replay(db_path):
    """After-answer replay; calculate the related budget from computed parent costs."""
    from backend.erce.engine import estimate_routed_item
    results={}
    for kind,route,values,_ in noise_support_specs():
        results[kind]=estimate_routed_item(dict(route_key=route,bill_no="2203380",years=5,start_year=2026,
            cutoff_date="2026-10-03",evidence_mode="development_review",variable_db_path=db_path,
            noise_support_component=kind,
            selected_evidence_keys=[f"2203380:{kind}:{key}:2024" for key in values]))
    parent=[sum(r.annual_amounts_thousand[i]*1000 for kind,r in results.items()
                if not kind.startswith("zone")) for i in range(5)]
    results["resident_support"]=estimate_routed_item(dict(route_key="related_project_ratio",
        bill_no="2203380",years=5,start_year=2026,cutoff_date="2026-10-03",
        evidence_mode="development_review",variable_db_path=db_path,noise_support_component="resident_support",
        selected_evidence_keys=["2203380:resident_support:ratio:2024"],
        calculated_inputs={"reference_project_cost":{"value":parent,"unit":"KRW/year",
            "source_ref":"동일 실행의 시설설치·수신료·전기료 결과 합계; 주민지원과 주민 보상금 제외"}}))
    return results
