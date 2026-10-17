"""Comparable central policy committee costs, not universal frequency or tariff."""
from math import isfinite
from backend.erce.reviewed_variable_rows import evidence_row
from backend.erce.variable_resolver import resolve_formula_variables,selected_precedent_inputs

PROFILE="central_social_policy_committee"
EXPANSION="social_security_committee_expansion"


def central_social_committee_rows():
    common=dict(source_bill_no="2215239",available_at="2026-01-05",reviewed_at="2026-10-08",
        source_ref="2215239 비용추계서25C6927 PDF3~5쪽;사회보장위원회운영사례",
        agency="보건복지부",policy_domain="중앙사회정책심의",scope="중앙정책심의위원회 민간위촉위원회의",
        service_function=PROFILE,support_derivation=PROFILE,committee_role_profile="central_social_policy_deliberation",
        variable_role="committee_comparable",allowed_routes=["committee_components"],
        requires_applicability_note=True,independently_verified=False,obtained_from="reviewed_answer",
        limitation="분기1회·민간위촉수당준용가정.분야이름만으로연4회나단가자동확정금지.국고공식상한이아닌사례지급액")
    rows=[evidence_row(evidence_key="2215239:central_committee:annual_meetings",variable_key="annual_meetings",
        value=4,unit="meeting/year",**common)]
    for mode,price in (("face_to_face",200000),("written",100000)):
        rows.append(evidence_row(evidence_key=f"2215239:central_committee:meeting_price:{mode}",
            variable_key="committee_meeting_price",value=price,unit="KRW/person/meeting",meeting_mode=mode,**common))
    for key,value,unit in (("plan_unit_cost",90000000,"KRW/plan"),("recurrence_interval_years",5,"year")):
        rows.append(evidence_row(evidence_key=f"2215239:governance_plan:{key}",variable_key=key,value=value,unit=unit,
            source_bill_no="2215239",available_at="2026-01-05",reviewed_at="2026-10-08",
            source_ref="2215239 비용추계서25C6927 PDF3쪽;2022장애인활동지원서비스고도화연구8900만원준용",
            agency="보건복지부",policy_domain="장애인활동지원",scope="당사자관계·서비스고도화발전방안 정책연구",
            service_function="activity_support_governance_plan",research_service_function="activity_support_governance_plan",
            research_cost_scope="research_contract_only",support_derivation="",variable_role="comparable_research_operand",
            allowed_routes=["research_plan"],requires_applicability_note=True,
            independently_verified=False,obtained_from="reviewed_answer",price_year=2022,original_contract_cost=89000000,
            limitation="2022관계기반서비스고도화연구9000만원준용가정.2018신규서비스개발4000만원과다른과업;최신공식고정요율아님"))
    expansion_common = dict(source_bill_no="2209259", available_at="2025-04-22", reviewed_at="2026-10-10",
        source_ref="2209259 비용추계서25C1706 PDF3~4쪽; 2023·2024 사회보장위원회 본회의 실적",
        agency="보건복지부", policy_domain="사회보장위원회", scope="기존 사회보장위원회 본회의 위원 확대",
        service_function=EXPANSION, support_derivation=EXPANSION,
        committee_role_profile="social_security_existing_committee_expansion",
        variable_role="committee_expansion_comparable", allowed_routes=["committee_components"],
        requires_applicability_note=True, independently_verified=False, obtained_from="reviewed_answer",
        limitation="당연직1명은 구성 참고 가정. 연3회는2023·2024 실적 기반 대면 가정. 신규위원회 전체 운영비나 분과회의 비용 아님")
    for key, value, unit in (("incremental_unpaid_members", 1, "person"),
                             ("annual_meetings", 3, "meeting/year")):
        rows.append(evidence_row(evidence_key=f"2209259:committee_expansion:{key}",
                                 variable_key=key, value=value, unit=unit, **expansion_common))
    for mode, price in (("face_to_face", 200000), ("written", 100000)):
        rows.append(evidence_row(evidence_key=f"2209259:committee_expansion:meeting_price:{mode}",
                                 variable_key="committee_meeting_price", value=price,
                                 unit="KRW/person/meeting", meeting_mode=mode, **expansion_common))
    return rows


def prepare_social_security_expansion(payload):
    if (payload.get("route_key") != "committee_components"
            or payload.get("committee_role_profile") != "social_security_existing_committee_expansion"
            or payload.get("meeting_mode") not in {"face_to_face", "written"}):
        raise ValueError("existing social-security committee role/mode mismatch")
    notes = ("committee_scale_note", "meeting_frequency_note", "committee_payment_note")
    if payload.get("expansion_scenario_confirmed") is not True or not all(
            str(payload.get(key) or "").strip() for key in notes):
        return {**payload, "support_missing_operands": ["committee_expansion_confirmation"],
                "support_derivation_trace": []}
    layers = dict(target_explicit=payload.get("explicit_inputs"), target_current_actual=payload.get("actual_inputs"),
                  official_standard=payload.get("official_inputs"), calculated_estimate=payload.get("calculated_inputs"),
                  precedent_assumption=selected_precedent_inputs(payload))
    if any(key in (layer or {}) for layer in layers.values() for key in ("growth_rate", "growth_rates_by_year")):
        raise ValueError("frozen committee reference must not add growth")
    upper, _ = resolve_formula_variables(("committee_components",), **layers)
    if upper:
        return payload
    units = dict(old_member_limit="person", new_member_limit="person", incremental_unpaid_members="person",
                 annual_meetings="meeting/year", committee_meeting_price="KRW/person/meeting")
    resolved, missing = resolve_formula_variables(tuple(units), **layers)
    if missing:
        return {**payload, "support_missing_operands": list(missing), "support_derivation_trace": []}
    for key, row in resolved.items():
        x = row.value
        if (row.unit != units[key] or not row.source_ref or isinstance(x, bool)
                or not isinstance(x, (int, float)) or not isfinite(x) or x < 0):
            raise ValueError("invalid committee expansion operand/unit")
    v = {key: row.value for key, row in resolved.items()}
    counts = (v["old_member_limit"], v["new_member_limit"], v["incremental_unpaid_members"])
    increase = counts[1] - counts[0]
    if any(x != int(x) for x in counts) or increase < 0 or counts[2] > increase:
        raise ValueError("invalid incremental committee composition")
    paid = increase - counts[2]
    calculated = dict(payload.get("calculated_inputs") or {})
    calculated["committee_components"] = dict(value=[dict(paid_members=paid,
        annual_meetings=v["annual_meetings"], meeting_unit_price=v["committee_meeting_price"])],
        unit="component_bundle", is_assumption=True,
        source_ref="; ".join(dict.fromkeys(row.source_ref for row in resolved.values())))
    return {**payload, "calculated_inputs": calculated, "support_missing_operands": [],
            "support_derivation_trace": [dict(old_limit=counts[0], new_limit=counts[1],
                incremental_unpaid_members=counts[2], paid_members=paid, annual_meetings=v["annual_meetings"],
                meeting_price=v["committee_meeting_price"], meeting_mode=payload["meeting_mode"],
                composition_assumption=payload["committee_scale_note"],
                expression="(개정정원상한−기존정원상한−추가무급위원)×연본회의×회의방식별수당")]}


def prepare_central_social_committee(payload):
    if payload.get("route_key")!="committee_components" or payload.get("committee_role_profile")!="central_social_policy_deliberation":
        raise ValueError("central policy committee role/route mismatch")
    if payload.get("meeting_mode") not in ("face_to_face","written") or payload.get("exclude_duty_public_officials") is not True:
        raise ValueError("committee meeting mode/public official treatment required")
    if not all(str(payload.get(k) or "").strip() for k in
        ("support_derivation_note","committee_scale_note","meeting_frequency_note","committee_payment_note")):
        raise ValueError("committee comparable applicability notes required")
    layers=dict(target_explicit=payload.get("explicit_inputs"),target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(payload))
    if any(k in (layer or {}) for layer in layers.values() for k in ("growth_rate","growth_rates_by_year")):
        raise ValueError("committee frozen comparable forbids duplicate growth")
    upper,_=resolve_formula_variables(("committee_components",),**layers)
    if upper:return payload
    units={"committee_total_members":"person","unpaid_chair_count":"person","equal_member_categories":"category",
        "paid_member_categories":"category","annual_meetings":"meeting/year","committee_meeting_price":"KRW/person/meeting"}
    r,missing=resolve_formula_variables(tuple(units),**layers)
    if missing:return {**payload,"support_missing_operands":list(missing),"support_derivation_trace":[]}
    for k,row in r.items():
        x=row.value
        if row.unit!=units[k] or not row.source_ref or isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x) or x<0:
            raise ValueError("invalid central committee parameter/unit")
    v={k:row.value for k,row in r.items()}
    total=v["committee_total_members"];chair=v["unpaid_chair_count"];groups=v["equal_member_categories"];paid_groups=v["paid_member_categories"]
    if any(x!=int(x) for x in (total,chair,groups,paid_groups)) or groups<=0 or total<=chair or not 0<=paid_groups<=groups or (total-chair)%groups:
        raise ValueError("committee equal-category composition mismatch")
    paid=(total-chair)/groups*paid_groups
    component=dict(paid_members=paid,annual_meetings=v["annual_meetings"],meeting_unit_price=v["committee_meeting_price"])
    calculated=dict(payload.get("calculated_inputs") or {})
    calculated["committee_components"]=dict(value=[component],unit="component_bundle",is_assumption=True,
        source_ref="; ".join(dict.fromkeys(row.source_ref for row in r.values())))
    return {**payload,"calculated_inputs":calculated,"support_missing_operands":[],
        "support_derivation_trace":[dict(total_members=total,unpaid_chairs=chair,category_count=groups,paid_categories=paid_groups,
            paid_members=paid,annual_meetings=v["annual_meetings"],meeting_price=v["committee_meeting_price"],meeting_mode=payload["meeting_mode"],
            expression="(전체위원−무급위원장)/동수범주수×유급범주수×연회의×유형별수당;부위원장중복가산없음")]}
