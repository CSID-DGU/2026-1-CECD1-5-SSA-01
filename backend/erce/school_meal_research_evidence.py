"""Answer-based, version-qualified research references; retain raw comparables."""
from backend.erce.reviewed_variable_rows import evidence_row


def linked_research_cycle_candidates(items, articles):
    plans=[item for item in items if item["routeKey"]=="research_plan"
           and "recurrence_interval_years" in item.get("explicitInputs",{})]
    for item in items:
        if item["routeKey"]!="research_survey" or "recurrence_interval_years" in item.get("explicitInputs",{}):
            continue
        text=articles[item["itemIndex"]]["text"]
        if not all(word in text for word in ("기준","조정","연구")):
            continue
        candidates=[]
        for plan in plans:
            period=plan["explicitInputs"]["recurrence_interval_years"]
            candidates.append(dict(value=period["value"],unit="year",basis="linked_plan_cycle",
                sourceRef=period["source_ref"],requiresConfirmation=True,
                reason="기준 검토를 기본계획 갱신과 함께 수행한다는 가정이에요. 법안이 조사 주기를 정한 것은 아니에요."))
        if candidates:
            item["recurrenceCandidates"]=candidates
            item["calculation"]["recurrenceCandidates"]=candidates
            item["linkedPlanRecurrenceYears"]=candidates[0]["value"] if len(candidates)==1 else None
    for item in items:
        if "공청회" in articles[item["itemIndex"]]["text"]:
            item["scopeChecks"]=["용역비에 공청회가 포함돼 있는지", "별도 개최 규모와 단가"]


def school_meal_research_rows():
    common=dict(source_bill_no="2211348",available_at="2026-10-03",agency="교육부",
        policy_domain="학교급식",service_function="계획 수립·적정인력 기준 검토",
        reviewed_at="2026-10-03",obtained_from="reviewed_answer",requires_applicability_note=True,
        source_bill_version_match=False,
        source_version_issue="추계서 회답2025-03-19/6개월 시행/조문제6항,원문 발의2025-07-08/1년 시행/제7항; 참조용으로만 사용",
        limitation="정답기준 참고 자료. 같은 원문 버전인지 미확인;PRISM 원자료 독립 검증 전이며 실제 확보일 이후만 사용")
    rows=[]
    for suffix,cost,year,agency,topic,kind,key,route in (
        ("school_meal_policy_2020",40000000,2020,"서울특별시교육청","학교급식정책연구","education_basic_plan","plan_unit_cost","research_plan"),
        ("education_facility_plan_2020",40000000,2020,"교육부","교육시설 안전·유지관리 계획","education_basic_plan","plan_unit_cost","research_plan"),
        ("lifelong_education_plan_2021",30000000,2021,"교육부","제5차 평생교육 기본계획 비전·과제","education_basic_plan","plan_unit_cost","research_plan"),
        ("preschool_plan_2021",36000000,2021,"교육부","제3차 유아교육 기본계획","education_basic_plan","plan_unit_cost","research_plan"),
        ("meal_staff_efficiency_2023",22000000,2023,"서울특별시교육청","학교·유치원 급식종사자 효율적 인력운영","meal_staffing_standard","survey_unit_cost","research_survey"),
        ("care_worker_job_2023",22000000,2023,"서울특별시교육청","돌봄전담사 직무분석·인력 운영","meal_staffing_standard","survey_unit_cost","research_survey"),
        ("choice_meal_manual_2024",20000000,2024,"경기도교육청","자율선택급식 표준 매뉴얼","meal_staffing_standard","survey_unit_cost","research_survey"),
        ("choice_meal_work_analysis_2024",22000000,2024,"경기도교육청","자율선택급식 종사자 업무분석·효율화","meal_staffing_standard","survey_unit_cost","research_survey"),
    ):
        rows.append(evidence_row(**common,evidence_key=f"2211348:research_sample:{suffix}",
            variable_key=key,value=cost,unit="KRW/plan" if route=="research_plan" else "KRW/survey",
            source_ref="2211348 첨부25C0254 PDF p.6~7 표2·4,PRISM 연구사례 인용",
            scope=topic,variable_role="historical_project_cost",project_agency=agency,
            observation_year=year,price_year=year,research_service_kind=kind,allowed_routes=[route],
            cost_basis="원 사업연도의 계약 사례; 미래 단가 환산·사업범위 확인 필요"))
    for suffix,key,prices,kind,route in (
        ("plan_schedule","plan_unit_cost",{"2025":42000000,"2028":44000000},"education_basic_plan","research_plan"),
        ("survey_schedule","survey_unit_cost",{"2025":22000000,"2028":24000000},"meal_staffing_standard","research_survey"),
    ):
        rows.append(evidence_row(**common,evidence_key=f"2211348:{suffix}",variable_key=key,
            value=prices,unit="KRW/occurrence/year",source_ref="2211348 첨부25C0254 PDF p.7 표3·5 적용연도 경비",
            scope="2025·2028년 각1회 적용한 참고 추계",variable_role="applied_scheduled_price",
            research_service_kind=kind,allowed_routes=[route],value_years=[2025,2026,2027,2028,2029],
            cost_basis="단가 환산 결과가 포함된 발생연도별 경비; CPI 중복 적용 금지, 다른 연도 외삽 금지"))
    rows.append(evidence_row(**common,evidence_key="2211348:survey_plan_linked_cycle",
        variable_key="recurrence_interval_years",value=3,unit="year",
        source_ref="2211348 첨부25C0254 PDF p.6: 주기 미규정으로 기본계획과 같은3년 재검토 가정",
        scope="기본계획 연계 적정인력 기준 재검토",variable_role="cycle_assumption",
        research_service_kind="meal_staffing_standard",research_cycle_basis="linked_plan_cycle",
        allowed_routes=["research_survey"],requires_user_confirmation=True,
        cost_basis="조사 자체의 법정 주기 아님. 계획과 함께 재검토한다는 가정 후보"))
    return rows


def reviewed_school_meal_research_payloads(db_path):
    common=dict(bill_no="2211348",agency="교육부",policy_domain="학교급식",start_year=2025,years=5,
        cutoff_date="2026-10-03",evidence_mode="development_review",variable_db_path=db_path,
        use_unmatched_source_as_reference=True,
        unmatched_source_reference_note="사용자 요청으로 첨부25C0254를 정답기준 회귀 참고. 현재 원문 시행일·공청회와는 별도 범위이며 새 정확도 평가가 아님")
    plan=dict(common,route_key="research_plan",research_service_kind="education_basic_plan",
        selected_evidence_keys=["2211348:plan_schedule"],
        explicit_inputs={"recurrence_interval_years":dict(value=3,unit="year",source_ref="기본계획3년 주기 원문·참고 추계 공통")})
    survey=dict(common,route_key="research_survey",research_service_kind="meal_staffing_standard",
        research_cycle_basis="linked_plan_cycle",linked_plan_recurrence_years=3,
        selected_evidence_keys=["2211348:survey_schedule","2211348:survey_plan_linked_cycle"])
    return [plan,survey]
