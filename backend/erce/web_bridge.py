"""Web-facing ERCE formula catalog and deterministic calculation boundary."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from backend.erce.engine import estimate_routed_item
from backend.erce.health_insurance_care_evidence import care_reference_candidates
from backend.erce.variable_evidence_store import (
    DEFAULT_VARIABLE_DB, evidence_payload_from_db, find_variable_candidates,
)
from backend.erce.variable_resolver import resolve_formula_variables, selected_precedent_inputs
from backend.erce.method_evidence_store import find_method_candidates, validate_selected_methods
from backend.erce.formula_registry import formula_for_route
from backend.erce.net_staffing import court_upgrade_precedent_inputs, net_staffing_scenarios
from backend.erce.route_tree import ERCE_ROUTE_TREE
from backend.general_cost_resolver import FORMULAS


def route_options(node: Any = ERCE_ROUTE_TREE, path: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    if isinstance(node, str):
        formula = formula_for_route(node)
        return [{
            "routeKey": node,
            "label": " › ".join(path),
            "formulaKey": formula.formula_key,
            "formula": formula.expression,
            "requiredVariables": list(FORMULAS[formula.formula_key]["required"]),
        }]
    return [
        option
        for name, child in node.items()
        for option in route_options(child, (*path, name))
    ]


def calculate_erce_web_item(payload: Mapping[str, Any], *,
                           variable_db_path: Path = DEFAULT_VARIABLE_DB) -> dict[str, Any]:
    """Run ERCE with explicit values and validated, deliberately selected DB IDs.

    The DB path is a server-side argument, never an arbitrary HTTP file path.
    Candidate retrieval does not silently choose values or policy scenarios.
    """
    route_key = str(payload.get("route_key") or "")
    if not route_key:
        raise ValueError("route_key가 필요합니다.")
    if payload.get("route_path"):
        from backend.erce.route_tree import route_for_path
        if route_for_path(payload["route_path"]) != route_key:
            raise ValueError("route_key disagrees with route_path formula leaf")
    formula = formula_for_route(route_key)
    raw_inputs = payload.get("explicit_inputs") or {}
    if not isinstance(raw_inputs, dict):
        raise ValueError("explicit_inputs 객체가 필요합니다.")
    inputs: dict[str, dict[str, Any]] = {}
    for key, value in raw_inputs.items():
        if not isinstance(value, dict) or "value" not in value:
            raise ValueError(f"{key}: value, unit, source_ref가 필요합니다.")
        if not str(value.get("unit") or "").strip() or not str(value.get("source_ref") or "").strip():
            raise ValueError(f"{key}: 단위와 근거를 입력해야 합니다.")
        inputs[str(key)] = {
            "value": value["value"], "unit": str(value["unit"]),
            "source_ref": str(value["source_ref"]),
        }
    start_year = payload.get("start_year") or inputs.get("start_year", {}).get("value")
    try:
        years = int(payload.get("years") or 5)
    except (TypeError, ValueError) as exc:
        raise ValueError("years는 1~30 사이의 정수여야 합니다.") from exc
    if not 1 <= years <= 30:
        raise ValueError("years는 1~30 사이의 정수여야 합니다.")
    engine_payload = {
        **payload, "route_key": route_key, "explicit_inputs": inputs,
        "years": years, "start_year": start_year,
        "bill_no": str(payload.get("bill_no") or ""),
        "cutoff_date": str(payload.get("cutoff_date") or ""),
        "agency": str(payload.get("agency") or ""),
        "policy_domain": str(payload.get("policy_domain") or ""),
        "subtype": str(payload.get("subtype") or ""),
        "variable_db_path": str(variable_db_path), "evidence_mode": "holdout",
        "allow_ai_assumptions": False,
        # Outside explicit inputs, numerical evidence must come from DB IDs.
        "actual_inputs": {}, "official_inputs": {}, "calculated_inputs": {},
        "selected_variable_inputs": {}, "ai_assumptions": {},
    }
    if not engine_payload.get("selected_evidence_keys"):
        engine_payload.pop("selected_evidence_keys", None)
    methods = validate_selected_methods(engine_payload, db_path=variable_db_path)
    hydrated = evidence_payload_from_db(engine_payload)
    from backend.erce.support_method_operands import prepare_support_operands
    hydrated = prepare_support_operands(hydrated)
    required = tuple(FORMULAS[formula.formula_key]["required"])
    _, missing_keys = resolve_formula_variables(required,
        target_explicit=inputs, target_current_actual=hydrated.get("actual_inputs"),
        official_standard=hydrated.get("official_inputs"),
        calculated_estimate=hydrated.get("calculated_inputs"),
        precedent_assumption=selected_precedent_inputs(hydrated))
    missing = list(missing_keys)
    method_candidates = []
    if payload.get("method_query") and payload.get("cutoff_date"):
        method_candidates = find_method_candidates(query=str(payload["method_query"]),
            cutoff_date=str(payload["cutoff_date"]), target_bill_no=engine_payload["bill_no"],
            target_family_key=str(payload.get("target_family_key") or ""),
            excluded_bill_nos=payload.get("excluded_bill_nos") or (), db_path=variable_db_path)
    if route_key in {"infertility_leave_civil_proxy", "infertility_leave_budget_proxy",
                     "health_insurance_general_support_change"} and start_year is None:
        missing.append("start_year")
    if payload.get("support_derivation") in {"student_income_interest", "center_annual_designation", "child_allowance_net_population", "child_allowance_indexed_population", "child_allowance_under18_indexed_floor", "parent_benefit_age_indexed_floor"} and start_year is None:
        missing.append("start_year")
    if payload.get("support_derivation") in {"child_allowance_birth_order_weighted","child_allowance_reviewed_cpi","jobseeker_livelihood_previous_year","jobseeker_cash_duration_extension","housing_management_fee","owner_energy_repair_grouped","grandparent_care_age_net","child_support_advance_expense","child_support_system_upgrade"} and start_year is None:
        missing.append("start_year")
    if missing:
        result = {
            "status": "needs_input", "routeKey": route_key,
            "formulaKey": formula.formula_key, "formula": formula.expression,
            "missingVariables": missing,
            "missingDerivationVariables": hydrated.get("support_missing_operands", []),
            "derivationTrace": hydrated.get("support_derivation_trace", []),
            "methodCandidates": method_candidates,
            "selectedMethods": methods,
        }
        if (route_key == "health_insurance_treasury_support"
                and payload.get("policy_domain") == "건강보험 요양병원 간병급여"
                and payload.get("cutoff_date")):
            result["referenceCandidates"] = [
                {
                    "evidenceKey": row["evidence_key"],
                    "variableKey": row["variable_key"],
                    "value": row["value"], "unit": row["unit"],
                    "scenarioKey": row.get("scenario_key", ""),
                    "patientGroup": row.get("patient_group", ""),
                    "stayBand": row.get("stay_band", ""),
                    "priceYear": row.get("price_year"),
                    "availableAt": row["available_at"],
                    "sourceRef": row["source_ref"],
                    "sourceUrl": row.get("source_url", ""),
                    "limitation": row.get("limitation", ""),
                    "requiresConfirmation": True,
                }
                for row in care_reference_candidates(
                    cutoff_date=str(payload["cutoff_date"]),
                    target_bill_no=str(payload.get("bill_no") or ""),
                )
            ]
        if route_key == "health_insurance_general_support_change" and payload.get("cutoff_date"):
            result["referenceCandidates"] = [
                {
                    "evidenceKey": row["evidence_key"], "variableKey": row["variable_key"],
                    "value": row["value"], "unit": row["unit"],
                    "availableAt": row["available_at"], "sourceRef": row["source_ref"],
                    "sourceUrl": row.get("source_url", ""), "limitation": row.get("limitation", ""),
                    "requiresConfirmation": True,
                }
                for row in find_variable_candidates(
                    cutoff_date=str(payload["cutoff_date"]),
                    agency="국회예산정책처",
                    policy_domain="건강보험 일반회계 국고지원",
                    target_bill_no=str(payload.get("bill_no") or ""),
                )
                if route_key in row.get("allowed_routes", [])
                and row.get("variable_key") in {
                    "premium_receipts_by_year", "current_general_support_rate",
                }
            ]
        if route_key in {"infertility_leave_civil_proxy", "infertility_leave_budget_proxy"} and payload.get("cutoff_date"):
            result["referenceCandidates"] = [
                {"evidenceKey": row["evidence_key"], "variableKey": row["variable_key"],
                 "value": row["value"], "unit": row["unit"], "sourceRef": row["source_ref"],
                 "availableAt": row["available_at"], "limitation": row.get("limitation", ""),
                 "requiresConfirmation": True}
                for row in find_variable_candidates(
                    cutoff_date=str(payload["cutoff_date"]), target_bill_no=str(payload.get("bill_no") or ""),
                    agency="고용노동부", policy_domain="난임치료휴가 급여")
                if route_key in row.get("allowed_routes", [])
            ]
        if route_key in {"personnel_grade", "personnel_average"} and (
            "headcount_by_grade" in missing or "headcount" in missing
        ):
            staffing_inputs = dict(payload.get("staffing_inputs") or {})
            context = payload.get("staffing_context") or {}
            cutoff = str(payload.get("cutoff_date") or "")
            if context.get("court_upgrade") is True and cutoff:
                staffing_inputs = {
                    **court_upgrade_precedent_inputs(
                        cutoff_date=cutoff,
                        parent_court=str(context.get("parent_court") or ""),
                    ),
                    **staffing_inputs,
                }
            result["staffingScenarios"] = net_staffing_scenarios(
                staffing_inputs,
                cutoff_date=cutoff,
                target_bill_no=str(payload.get("bill_no") or ""),
            )
        if payload.get("cutoff_date"):
            candidates = list(result.get("referenceCandidates") or [])
            existing_keys = {row["evidenceKey"] for row in candidates}
            for variable in dict.fromkeys([*missing, *hydrated.get("support_missing_operands", [])]):
                rows = find_variable_candidates(cutoff_date=str(payload["cutoff_date"]),
                    variable_key=variable, target_bill_no=engine_payload["bill_no"],
                    start_year=start_year, years=years, db_path=variable_db_path,
                    excluded_bill_nos=payload.get("excluded_bill_nos") or ())
                rows = [row for row in rows if route_key in row.get("allowed_routes", [])
                        and row.get("source_bill_no") not in (payload.get("excluded_bill_nos") or [])]
                compatible = []
                for row in rows:
                    try:
                        evidence_payload_from_db({**engine_payload,
                            "selected_evidence_keys": [row["evidence_key"]],
                            "evidence_selection_reasons": {row["evidence_key"]:
                                "사용자에게 제시할 후보로 적용 조건을 검사합니다. 아직 선택하거나 확정하지 않았습니다."}})
                    except (ValueError, TypeError, KeyError):
                        continue
                    compatible.append(row)
                rows = compatible
                rows.sort(key=lambda row: (row.get("source_class") != "official_standard", row["evidence_key"]))
                for row in rows[:5]:
                    if row["evidence_key"] in existing_keys:
                        continue
                    candidates.append({"evidenceKey": row["evidence_key"],
                        "variableKey": variable, "value": row["value"], "unit": row["unit"],
                        "sourceRef": row["source_ref"], "sourceClass": row.get("source_class", ""),
                        "availableAt": row["available_at"], "limitation": row.get("limitation", ""),
                        "scope": row["scope"], "serviceFunction": row["service_function"],
                        "requiresConfirmation": True})
                    existing_keys.add(row["evidence_key"])
            result["referenceCandidates"] = candidates
            result["missingVariableEvidence"] = {
                variable: {
                    "status": "candidates_need_review" if any(
                        row["variableKey"] == variable for row in candidates) else "no_eligible_candidate",
                    "candidateCount": sum(row["variableKey"] == variable for row in candidates),
                    "meaning": "후보가 있으나 적용·선택이 필요합니다." if any(
                        row["variableKey"] == variable for row in candidates)
                        else "현재 변수키·산식·시점·평가제외 조건으로 찾은 후보가 없습니다. DB 전체에 값이 없다는 뜻은 아닙니다.",
                }
                for variable in dict.fromkeys([*missing, *hydrated.get("support_missing_operands", [])])
            }
        return result
    try:
        estimate = estimate_routed_item(engine_payload)
    except ValueError as exc:
        prefix = "missing ERCE formula variables: "
        if str(exc).startswith(prefix):
            return {
                "status": "needs_input", "routeKey": route_key,
                "formulaKey": formula.formula_key, "formula": formula.expression,
                "missingVariables": str(exc)[len(prefix):].split(", "),
            }
        raise
    return {
        "status": "computed_review",
        **({"estimatePurpose": "reference_scenario", "referenceNotice": hydrated.get("reference_notice", "")}
           if hydrated.get("estimate_purpose") == "reference_scenario" else {}),
        "routeKey": route_key,
        "formulaKey": estimate.formula_key,
        "formula": estimate.formula,
        "annualAmountsThousand": list(estimate.annual_amounts_thousand),
        "derivationTrace": hydrated.get("support_derivation_trace", []),
        "evidenceVariables": {key: {"value": row["value"], "unit": row["unit"], "source_ref": row["source_ref"]}
            for key, row in hydrated.get("selected_variable_inputs", {}).items()},
        "sourceRefs": list(estimate.source_refs),
        "methodEvidenceKeys": list(estimate.method_evidence_keys),
        "selectedMethods": methods,
        "methodCandidates": method_candidates,
        "resolvedVariables": {key: asdict(value) for key, value in estimate.resolved_variables.items()},
    }
