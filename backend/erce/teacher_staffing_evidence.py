"""Conditional school staffing checklist and versioned, rounded precedent rates."""
from backend.erce.reviewed_variable_rows import evidence_row

PAY_PROFILE = "nutrition_teacher_grade2_start_step8_annual_step_2026_2030"


def teacher_staffing_review_candidates(items, articles, route_by_key):
    """Suggest omitted components, never create costs or staffing assumptions."""
    trigger = next((item for item in items if item["routeKey"] == "personnel_average"
                    and "영양교사" in articles[item["itemIndex"]]["text"]
                    and "2명이상" in "".join(articles[item["itemIndex"]]["text"].split())), None)
    if trigger is None:
        return []
    article = articles[trigger["itemIndex"]]
    covered = {item["routeKey"] for item in items}
    private_already_selected = any(item["routeKey"] == "personnel_employer_contribution"
                                   and "사립" in item["name"] for item in items)
    candidates = []
    for component, route, reason in (
        ("public_basic_expense", "personnel_basic_expense",
         "국·공립 추가 배치의 기본경비 필요 여부를 확인하세요. 선례는 봉급·수당과 기관부담금 합계에 비율을 적용했습니다."),
        ("public_initial_assets", "personnel_asset",
         "새 인력의 PC·집기 구입 필요 여부를 확인하세요. 신규 구입이면 첫해만 계산하고 기존 장비 재사용 시 제외합니다."),
        ("private_pension_share", "personnel_employer_contribution",
         "대상에 사립학교가 포함되는지 확인하세요. 사립 교원 연금의 국가부담은 국·공립 인건비와 분리하고, 재정결함보조는 별도 근거가 필요합니다."),
    ):
        if route in covered and component != "private_pension_share":
            continue
        if component == "private_pension_share" and private_already_selected:
            continue
        option = route_by_key[route]
        candidates.append(dict(componentKey=component, routeKey=route,
            formulaKey=option["formulaKey"], formula=option["formula"],
            missingVariables=option["requiredVariables"], status="conditional_review",
            triggerRef=article["no"], sourceQuote=article["text"], sourcePage=article["source_page"],
            reason=reason, requiresConfirmation=True))
    compact="".join(article["text"].split())
    if "또는" in compact and "2회이상" in compact:
        option=route_by_key["personnel_average"]
        candidates.append(dict(componentKey="teacher_target_group_split",routeKey="personnel_average",
            formulaKey=option["formulaKey"],formula=option["formula"],status="conditional_review",
            triggerRef=article["no"],sourceQuote=article["text"],sourcePage=article["source_page"],
            missingVariables=["규모 기준 국공립 인원","다회급식 국공립 인원","중복 인원","규모 기준 사립 인원"],
            reason="규모와 다회급식 대상을 따로 계산하고 중복은 한 번만 계상하세요. 사립 다회급식 통계가 없으면 비용0이 아닌 미산정 범위로 남깁니다.",
            requiresConfirmation=True))
    return candidates


def teacher_staffing_rows():
    rows = []
    common = dict(source_bill_no="2200601", available_at="2024-07-11",
        agency="교육부", policy_domain="영양교사 증원", service_function="학교 추가배치",
        reviewed_at="2026-10-03", obtained_from="reviewed_answer",
        requires_applicability_note=True, staff_pay_profile=PAY_PROFILE,
        limitation="2024년 비용추계서의 과거 가정. 최신 공식 단가 아님; 백만원 반올림 표이며 정확한 호봉별 원자료·기관부담률 전망은 미확보")
    for scenario, public, private, primary_threshold in ((1,156,8,1500),(2,618,9,1000)):
        for sector, count in (("public",public),("private",private)):
            rows.append(evidence_row(**common,
                evidence_key=f"2200601:s{scenario}:{sector}:headcount", variable_key="headcount",
                value=count, unit="person", scope=f"시나리오{scenario} {sector} 학교",
                source_ref="2200601 비용추계서 PDF p.3,6~8;2023 교육통계 준용",
                variable_role="target_quantity", reuse_policy="target_only", school_sector=sector,
                observation_year=2023, primary_students_over=primary_threshold,
                secondary_students_over=1200, incremental_per_school=1,
                allowed_routes=["personnel_average","personnel_asset"],
                staffing_assumption="대상 학교마다1명 순증,5년 동결; 기존 배치 인원·재배치 확인 필요"))
    for suffix, key, value, unit, route, sector, component, basis in (
        ("salary", "salary_per_person", [35e6,37e6,38e6,40e6,41e6], "KRW/person/year",
         "personnel_average", "public", "salary", "봉급·수당; 기관부담금 제외"),
        ("employer_cost", "unit_cost", [5e6,5e6,5e6,5e6,6e6], "KRW/person/year",
         "quantity_unit", "public", "employer_cost", "1인당 기관부담금; 반올림 보수에서 부담률 역산 금지"),
        ("basic_ratio", "basic_expense_ratio", .0654, "ratio",
         "personnel_basic_expense", "public", "basic_expense", "봉급·수당+기관부담금에 적용;2024 교육비특별회계 예산 비율"),
        ("initial_asset", "asset_unit_price_per_person", 5e6, "KRW/person",
         "personnel_asset", "public", "initial_asset", "첫해1회, 반올림된 전망 단가"),
        ("asset_duration", "duration", 1, "year",
         "personnel_asset", "public", "initial_asset", "신규 채용 시 첫해만 구입한다는 선례 가정"),
        ("private_pension_rate", "employer_contribution_rate", .03706, "ratio",
         "personnel_employer_contribution", "private", "private_pension", "본문상 봉급·수당 기준. 표6은 기본경비·집기 포함 총단가를 적용한 것으로 보여 불일치 기록"),
    ):
        rows.append(evidence_row(**common, evidence_key=f"2200601:{suffix}", variable_key=key,
            value=value, unit=unit, scope=f"{sector} 신규 영양교사",
            source_ref="2200601 비용추계서 PDF p.4~8 표3·각주5", variable_role="rate_assumption",
            school_sector=sector, personnel_cost_component=component, allowed_routes=[route],
            cost_basis=basis, value_years=[2026,2027,2028,2029,2030],
            rounded_precision_won=1000000 if suffix in {"salary","employer_cost","initial_asset"} else None))
    return rows


def reviewed_teacher_replay(db_path, scenario):
    """Post-answer development replay; use disclosed rounded rates, not gold totals."""
    from backend.erce.engine import estimate_routed_item
    if scenario not in (1,2):
        raise ValueError("teacher staffing scenario")
    common = dict(bill_no="2200601", start_year=2026, years=5, cutoff_date="2026-10-03",
        evidence_mode="development_review", variable_db_path=db_path, staff_pay_profile=PAY_PROFILE)
    def run(route, sector, component, keys, calculated=None):
        return estimate_routed_item(dict(common, route_key=route, school_sector=sector,
            personnel_cost_component=component, selected_evidence_keys=keys,
            calculated_inputs=calculated or {}))
    public_key=f"2200601:s{scenario}:public:headcount"
    salary=run("personnel_average","public","salary",[public_key,"2200601:salary"])
    # Counts and component dependencies remain traceable calculated inputs.
    public_count=next(r["value"] for r in teacher_staffing_rows() if r["evidence_key"]==public_key)
    quantity={"quantity":{"value":public_count,"unit":"person","source_ref":public_key}}
    burden=run("quantity_unit","public","employer_cost",["2200601:employer_cost"],quantity)
    total_pay=[(a+b)*1000 for a,b in zip(salary.annual_amounts_thousand,burden.annual_amounts_thousand)]
    basic=run("personnel_basic_expense","public","basic_expense",["2200601:basic_ratio"],
        {"annual_salary_amount":{"value":total_pay,"unit":"KRW/year","source_ref":"계산:2200601:salary +2200601:employer_cost"}})
    asset=run("personnel_asset","public","initial_asset",[public_key,"2200601:initial_asset","2200601:asset_duration"])
    private_count=next(r["value"] for r in teacher_staffing_rows()
        if r["evidence_key"]==f"2200601:s{scenario}:private:headcount")
    pay=next(r["value"] for r in teacher_staffing_rows() if r["evidence_key"]=="2200601:salary")
    private=run("personnel_employer_contribution","private","private_pension",["2200601:private_pension_rate"],
        {"annual_salary_amount":{"value":[private_count*p for p in pay],"unit":"KRW/year",
                                 "source_ref":f"계산:2200601:s{scenario}:private:headcount ×2200601:salary; 본문상 동일 봉급·수당 가정"}})
    parts=dict(salary=salary,employer_cost=burden,basic_expense=basic,initial_asset=asset,private_pension=private)
    totals=[sum(r.annual_amounts_thousand[i] for r in parts.values()) for i in range(5)]
    return dict(components={k:list(v.annual_amounts_thousand) for k,v in parts.items()},
                annual_amounts_thousand=totals,total_thousand=sum(totals),
                evaluation_type="post_answer_rounded_rate_regression",
                limitation="원자료 미확보: 반올림단가 사용, 사립연금은 불일치 표가 아닌 본문상 보수 기준")
