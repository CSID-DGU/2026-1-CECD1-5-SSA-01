"""ERCE orchestration after an AI-routed cost item is supplied."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from backend.erce.evidence_registry import select_committee_pack
from backend.erce.formula_registry import formula_for_route, DIRECT_FORMULA_ROUTE_KEYS
from backend.erce.variable_resolver import ResolvedVariable, resolve_formula_variables, selected_precedent_inputs
from backend.economic_forecast_registry import get_forecast_series
from backend.general_cost_resolver import FORMULAS, request_from_dict, resolve_general_cost
from backend.research_service_unit_cost_registry import research_service_formula_inputs
from backend.erce.evaluation_evidence_registry import evaluation_formula_inputs
from backend.erce.notification_evidence_registry import notification_formula_inputs
from backend.erce.diagnostic_evidence_registry import diagnostic_formula_inputs
from backend.erce.route_tree import route_for_path
from backend.erce.variable_evidence_store import evidence_payload_from_db


@dataclass(frozen=True)
class ERCEEstimate:
    route_key: str
    subtype: str
    formula_key: str
    formula: str
    evidence_key: str
    annual_amounts_thousand: tuple[int | None, ...]
    source_refs: tuple[str, ...]
    resolved_variables: dict[str, ResolvedVariable]
    evidence_mode: str = "holdout"


def estimate_routed_item(payload: Mapping[str, Any]) -> ERCEEstimate:
    """Select formula/evidence deterministically from an AI route decision."""
    mode = str(payload.get("evidence_mode") or "holdout")
    if mode not in {"holdout", "development_review"}:
        raise ValueError("invalid evidence_mode")
    payload = evidence_payload_from_db(payload)
    result = _estimate_hydrated_item(payload)
    keys = payload.get("selected_evidence_keys") or []
    return replace(result, evidence_mode=mode,
                   evidence_key=",".join(keys) if keys else result.evidence_key)


def _estimate_hydrated_item(payload: Mapping[str, Any]) -> ERCEEstimate:
    route_key = str(payload.get("route_key") or "")
    if "route_path" in payload:
        tree_route = route_for_path(payload["route_path"])
        if route_key and route_key != tree_route:
            raise ValueError("route_key disagrees with route_path formula leaf")
        route_key = tree_route
        payload = {**payload, "route_key": route_key}
    subtype = str(payload.get("subtype") or "")
    formula = formula_for_route(route_key)
    if route_key in DIRECT_FORMULA_ROUTE_KEYS:
        return _estimate_direct_formula_item(payload, formula)
    if route_key == "information_system_project_plan":
        return _estimate_project_plan_item(payload, formula)
    if route_key == "diagnostic_test_subsidy":
        return _estimate_diagnostic_item(payload, formula)
    if route_key == "legal_notification":
        return _estimate_notification_item(payload, formula)
    if route_key == "evaluation_panel_with_initial_study":
        return _estimate_evaluation_item(payload, formula)
    if route_key in {"research_plan", "research_survey"}:
        return _estimate_research_item(payload, formula)
    if route_key != "committee_operation":
        raise NotImplementedError(
            "use the connected general resolver for non-committee ERCE routes"
        )
    pack, rate = select_committee_pack(
        agency=str(payload.get("agency") or ""),
        subtype=subtype,
        as_of_date=str(payload.get("cutoff_date") or ""),
        policy_domain=str(payload.get("policy_domain") or ""),
        target_bill_no=str(payload.get("bill_no") or ""),
    )
    resolved, missing = resolve_formula_variables(
        (
            "committee_instances",
            "paid_members",
            "annual_meetings",
            "meeting_unit_price",
        ),
        target_explicit=payload.get("explicit_inputs"),
        target_current_actual=payload.get("actual_inputs"),
        official_standard={
            "meeting_unit_price": {
                "value": rate.won_per_person_meeting,
                "unit": "KRW/person/meeting",
                "source_ref": rate.source_ref,
            }
        },
        precedent_assumption={
            "committee_instances": {
                "value": pack.committee_instances,
                "unit": "committee",
                "source_ref": pack.source_ref,
            },
            "paid_members": {
                "value": pack.paid_members,
                "unit": "person/committee",
                "source_ref": pack.source_ref,
            },
            "annual_meetings": {
                "value": pack.annual_meetings,
                "unit": "meeting/year",
                "source_ref": pack.source_ref,
            },
        },
        ai_assumption=payload.get("ai_assumptions"),
        allow_ai_assumption=bool(payload.get("allow_ai_assumptions", False)),
    )
    if missing:
        raise ValueError("missing ERCE formula variables: " + ", ".join(missing))
    committee_instances = int(resolved["committee_instances"].value)
    paid_members = int(resolved["paid_members"].value)
    annual_meetings = int(resolved["annual_meetings"].value)
    meeting_unit_price = float(resolved["meeting_unit_price"].value)
    years = int(payload.get("years") or 5)
    start_year = int(payload.get("start_year")) if payload.get("start_year") is not None else None
    prices: float | list[float] = meeting_unit_price
    if pack.growth_series_key:
        if start_year is None or pack.growth_application_start_year is None:
            raise ValueError("growth-backed committee evidence requires start_year")
        series = get_forecast_series(pack.growth_series_key)
        factor = 1.0
        yearly_prices: list[float] = []
        for year in range(start_year, start_year + years):
            if year >= pack.growth_application_start_year:
                try:
                    factor *= 1.0 + series.rates_by_year[year]
                except KeyError as exc:
                    raise ValueError(f"forecast missing year: {year}") from exc
            yearly_prices.append(meeting_unit_price * factor)
        prices = yearly_prices
    components = [{
        "paid_members": paid_members,
        "annual_meetings": annual_meetings,
        "instances_per_year": committee_instances,
        "meeting_unit_price": prices,
    }]
    # The common resolver accepts annual_meetings directly; expand multiple
    # investigation/advisory bodies as separate identical components.
    if committee_instances > 1:
        components = [
            {
                "paid_members": paid_members,
                "annual_meetings": annual_meetings,
                "meeting_unit_price": prices,
            }
            for _ in range(committee_instances)
        ]
    resolution = resolve_general_cost(request_from_dict({
        "cost_nature": "goods_services",
        "component": "event_meeting",
        "formula_key": formula.formula_key,
        "years": years,
        "start_year": start_year,
        "inputs": {
            "committee_components": {
                "value": components,
                "unit": "component_bundle",
                "source": "erce_evidence_registry",
                "source_ref": f"{pack.source_ref}; {rate.source_ref}",
                "evidence_keys": [pack.key, rate.key],
            },
            "first_year_fraction": {
                "value": float(payload.get("first_year_fraction", 1.0)),
                "unit": "ratio",
                "source": "target_effective_date",
                "source_ref": str(payload.get("effective_date_ref") or ""),
            },
        },
    }))
    return ERCEEstimate(
        route_key=route_key,
        subtype=subtype,
        formula_key=formula.formula_key,
        formula=formula.expression,
        evidence_key=pack.key,
        annual_amounts_thousand=tuple(resolution.annual_amounts_thousand),
        source_refs=(pack.source_ref, rate.source_ref),
        resolved_variables=resolved,
        evidence_mode=str(payload.get("evidence_mode") or "holdout"),
    )


def _estimate_direct_formula_item(payload: Mapping[str, Any], formula: Any) -> ERCEEstimate:
    """Wire registered formulas without any precedent selection or invented values."""
    definition = FORMULAS[formula.formula_key]
    required = tuple(definition["required"])
    selected = selected_precedent_inputs(payload)
    resolved, missing = resolve_formula_variables(
        required,
        target_explicit=payload.get("explicit_inputs"),
        target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),
        calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected,
    )
    if missing:
        raise ValueError("missing ERCE formula variables: " + ", ".join(missing))
    optional_keys = tuple(dict.fromkeys((*definition.get("optional", ()),
        "growth_rates_by_year", "base_year", "first_year_fraction", "duration")))
    optional, _ = resolve_formula_variables(
        optional_keys,
        target_explicit=payload.get("explicit_inputs"),
        target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),
        calculated_estimate=payload.get("calculated_inputs"),
        precedent_assumption=selected,
    )
    resolved.update(optional)
    result = resolve_general_cost(request_from_dict({
        "cost_nature": formula.cost_nature, "component": formula.route_key,
        "formula_key": formula.formula_key, "years": int(payload.get("years") or 5),
        "start_year": payload.get("start_year"),
        "target_bill_no": str(payload.get("bill_no") or ""),
        "inputs": {name: {"value": row.value, "unit": row.unit,
                          "source": row.source_class, "source_ref": row.source_ref}
                   for name, row in resolved.items()},
    }))
    if result.status != "computed_review":
        raise ValueError("invalid ERCE formula variables: " + ", ".join(result.missing_variables))
    return ERCEEstimate(
        route_key=formula.route_key, subtype=str(payload.get("subtype") or ""),
        formula_key=formula.formula_key, formula=formula.expression,
        evidence_key="target_formula_inputs",
        annual_amounts_thousand=tuple(result.annual_amounts_thousand),
        source_refs=tuple(dict.fromkeys(row.source_ref for row in resolved.values())),
        resolved_variables=resolved,
    )


def _estimate_project_plan_item(payload: Mapping[str, Any], formula: Any) -> ERCEEstimate:
    # Project totals are not comparable unit rates: require this target's plan.
    years = int(payload.get("years") or 5)
    start_year = int(payload["start_year"])
    if payload.get("budget_start_year") != start_year:
        raise ValueError("project plan budget_start_year must match target start_year")
    resolved, missing = resolve_formula_variables(
        ("annual_project_budget",),
        target_explicit=payload.get("explicit_inputs"),
        target_current_actual=payload.get("actual_inputs"),
    )
    if missing:
        raise ValueError("missing ERCE formula variables: " + ", ".join(missing))
    row = resolved["annual_project_budget"]
    if row.unit != "KRW/year" or not row.source_ref.strip():
        raise ValueError("project plan requires KRW/year and target-plan source_ref")
    result = resolve_general_cost(request_from_dict({
        "cost_nature": "goods_services", "component": "information_system_project_plan",
        "formula_key": formula.formula_key, "years": years, "start_year": start_year,
        "inputs": {"annual_project_budget": {
            "value": row.value, "unit": row.unit,
            "source": row.source_class, "source_ref": row.source_ref,
        }},
    }))
    if result.status != "computed_review":
        raise ValueError("invalid ERCE project budget: " + ", ".join(result.missing_variables))
    return ERCEEstimate(
        route_key=str(payload["route_key"]), subtype="target_project_budget",
        formula_key=formula.formula_key, formula=formula.expression,
        evidence_key="target_project_plan", annual_amounts_thousand=tuple(result.annual_amounts_thousand),
        source_refs=(row.source_ref,), resolved_variables=resolved,
    )


def _estimate_diagnostic_item(payload: Mapping[str, Any], formula: Any) -> ERCEEstimate:
    key = "target_evidence"
    try:
        key, benchmark = diagnostic_formula_inputs(
            agency=str(payload.get("agency") or ""),
            policy_domain=str(payload.get("policy_domain") or ""),
            cutoff_date=str(payload.get("cutoff_date") or ""),
            target_bill_no=str(payload.get("bill_no") or ""),
        )
    except KeyError:
        benchmark = {}
    benchmark = {**benchmark, **selected_precedent_inputs(payload)}
    resolved, missing = resolve_formula_variables(
        ("annual_recipients", "test_unit_cost", "existing_annual_cost"),
        target_explicit=payload.get("explicit_inputs"),
        target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),
        precedent_assumption=benchmark,
    )
    if missing:
        raise ValueError("missing ERCE formula variables: " + ", ".join(missing))
    result = resolve_general_cost(request_from_dict({
        "cost_nature": "transfer", "component": "diagnostic_test_subsidy",
        "formula_key": formula.formula_key, "years": int(payload.get("years") or 5),
        "start_year": payload.get("start_year"),
        "inputs": {name: {"value": row.value, "unit": row.unit,
                          "source": row.source_class, "source_ref": row.source_ref}
                   for name, row in resolved.items()},
    }))
    if result.status != "computed_review":
        raise ValueError("invalid ERCE diagnostic variables: " + ", ".join(result.missing_variables))
    return ERCEEstimate(
        route_key=str(payload["route_key"]), subtype="diagnostic_fee_support",
        formula_key=formula.formula_key, formula=formula.expression,
        evidence_key=key, annual_amounts_thousand=tuple(result.annual_amounts_thousand),
        source_refs=tuple(dict.fromkeys(row.source_ref for row in resolved.values())),
        resolved_variables=resolved,
    )


def _estimate_notification_item(payload: Mapping[str, Any], formula: Any) -> ERCEEstimate:
    years = int(payload.get("years") or 5)
    key = "target_evidence"
    try:
        key, benchmark = notification_formula_inputs(
            agency=str(payload.get("agency") or ""),
            policy_domain=str(payload.get("policy_domain") or ""),
            cutoff_date=str(payload.get("cutoff_date") or ""),
            start_year=int(payload["start_year"]), years=years,
            target_bill_no=str(payload.get("bill_no") or ""),
        )
    except KeyError:
        benchmark = {}
    benchmark = {**benchmark, **selected_precedent_inputs(payload)}
    resolved, missing = resolve_formula_variables(
        ("annual_case_count", "action_rate", "notices_per_case", "notice_unit_price"),
        target_explicit=payload.get("explicit_inputs"),
        target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),
        precedent_assumption=benchmark,
    )
    if missing:
        raise ValueError("missing ERCE formula variables: " + ", ".join(missing))
    result = resolve_general_cost(request_from_dict({
        "cost_nature": "goods_services", "component": "legal_notification",
        "formula_key": formula.formula_key, "years": years,
        "start_year": payload.get("start_year"),
        "inputs": {
            name: {"value": row.value, "unit": row.unit,
                   "source": row.source_class, "source_ref": row.source_ref}
            for name, row in resolved.items()
        },
    }))
    if result.status != "computed_review":
        raise ValueError("invalid ERCE notification variables: " + ", ".join(result.missing_variables))
    return ERCEEstimate(
        route_key=str(payload["route_key"]), subtype="postal_service",
        formula_key=formula.formula_key, formula=formula.expression,
        evidence_key=key, annual_amounts_thousand=tuple(result.annual_amounts_thousand),
        source_refs=tuple(dict.fromkeys(row.source_ref for row in resolved.values())),
        resolved_variables=resolved,
    )


def _estimate_evaluation_item(payload: Mapping[str, Any], formula: Any) -> ERCEEstimate:
    key = "target_evidence"
    try:
        key, benchmark = evaluation_formula_inputs(
            agency=str(payload.get("agency") or ""),
            policy_domain=str(payload.get("policy_domain") or ""),
            cutoff_date=str(payload.get("cutoff_date") or ""),
            start_year=int(payload["start_year"]),
            target_bill_no=str(payload.get("bill_no") or ""),
        )
    except KeyError:
        benchmark = {}
    benchmark = {**benchmark, **selected_precedent_inputs(payload)}
    resolved, missing = resolve_formula_variables(
        ("committee_components", "initial_study_cost"),
        target_explicit=payload.get("explicit_inputs"),
        target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),
        precedent_assumption=benchmark,
    )
    if missing:
        raise ValueError("missing ERCE formula variables: " + ", ".join(missing))
    result = resolve_general_cost(request_from_dict({
        "cost_nature": "goods_services",
        "component": "evaluation_panel",
        "formula_key": formula.formula_key,
        "years": int(payload.get("years") or 5),
        "start_year": payload.get("start_year"),
        "inputs": {
            name: {"value": row.value, "unit": row.unit,
                   "source": row.source_class, "source_ref": row.source_ref}
            for name, row in resolved.items()
        },
    }))
    return ERCEEstimate(
        route_key=str(payload["route_key"]), subtype="evaluation_panel",
        formula_key=formula.formula_key, formula=formula.expression,
        evidence_key=key, annual_amounts_thousand=tuple(result.annual_amounts_thousand),
        source_refs=tuple(dict.fromkeys(row.source_ref for row in resolved.values())),
        resolved_variables=resolved,
    )


def _estimate_research_item(payload: Mapping[str, Any], formula: Any) -> ERCEEstimate:
    route = str(payload["route_key"])
    unit_key = "plan_unit_cost" if route == "research_plan" else "survey_unit_cost"
    required = (unit_key, "recurrence_interval_years")
    try:
        benchmark = research_service_formula_inputs(
            route, str(payload.get("agency") or ""),
            as_of_date=str(payload.get("cutoff_date") or ""),
            policy_domain=str(payload.get("policy_domain") or ""),
            target_bill_no=str(payload.get("bill_no") or ""),
        )
    except KeyError:
        benchmark = {}
    benchmark = {**benchmark, **selected_precedent_inputs(payload)}
    # Published budget comparables remain assumptions about the NEW target.
    # A law's explicit annual/three-year frequency overrides any comparable.
    resolved, missing = resolve_formula_variables(
        required,
        target_explicit=payload.get("explicit_inputs"),
        target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),
        precedent_assumption=benchmark,
    )
    # Phase is independent of statutory recurrence: an existing survey may
    # put the next occurrence after the first estimation year.
    optional, _ = resolve_formula_variables(
        ("first_occurrence_offset_years",),
        target_explicit=payload.get("explicit_inputs"),
        target_current_actual=payload.get("actual_inputs"),
        official_standard=payload.get("official_inputs"),
        precedent_assumption=benchmark,
    )
    resolved.update(optional)
    if missing:
        raise ValueError("missing ERCE formula variables: " + ", ".join(missing))
    result = resolve_general_cost(request_from_dict({
        "cost_nature": "goods_services",
        "component": route,
        "formula_key": formula.formula_key,
        "years": int(payload.get("years") or 5),
        "start_year": payload.get("start_year"),
        "inputs": {
            key: {"value": row.value, "unit": row.unit,
                  "source": row.source_class, "source_ref": row.source_ref}
            for key, row in resolved.items()
        },
    }))
    refs = tuple(dict.fromkeys(row.source_ref for row in resolved.values()))
    keys = benchmark.get(unit_key, {}).get("evidence_keys", [])
    return ERCEEstimate(
        route_key=route,
        subtype=str(payload.get("subtype") or ""),
        formula_key=formula.formula_key,
        formula=formula.expression,
        evidence_key=keys[0] if keys else "target_evidence",
        annual_amounts_thousand=tuple(result.annual_amounts_thousand),
        source_refs=refs,
        resolved_variables=resolved,
    )


__all__ = ["ERCEEstimate", "estimate_routed_item"]
