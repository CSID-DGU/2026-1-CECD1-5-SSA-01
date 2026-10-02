"""Web-facing ERCE formula catalog and deterministic calculation boundary."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from backend.erce.engine import estimate_routed_item
from backend.erce.health_insurance_care_evidence import care_reference_candidates
from backend.erce.variable_evidence_store import find_variable_candidates
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


def calculate_erce_web_item(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Run the actual ERCE estimator with user-confirmed variables only."""
    route_key = str(payload.get("route_key") or "")
    if not route_key:
        raise ValueError("route_key가 필요합니다.")
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
    missing = [key for key in FORMULAS[formula.formula_key]["required"] if key not in inputs]
    start_year = payload.get("start_year") or inputs.get("start_year", {}).get("value")
    if route_key in {"infertility_leave_civil_proxy", "infertility_leave_budget_proxy",
                     "health_insurance_general_support_change"} and start_year is None:
        missing.append("start_year")
    if payload.get("selected_evidence_keys"):
        raise ValueError("웹 연결에서는 근거 DB 자동 선택을 아직 지원하지 않습니다.")
    if missing:
        result = {
            "status": "needs_input", "routeKey": route_key,
            "formulaKey": formula.formula_key, "formula": formula.expression,
            "missingVariables": missing,
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
        return result
    try:
        years = int(payload.get("years") or 5)
    except (TypeError, ValueError) as exc:
        raise ValueError("years는 1~30 사이의 정수여야 합니다.") from exc
    if not 1 <= years <= 30:
        raise ValueError("years는 1~30 사이의 정수여야 합니다.")
    engine_payload = {
        "route_key": route_key,
        "bill_no": str(payload.get("bill_no") or ""),
        "years": years,
        "start_year": start_year,
        "cutoff_date": str(payload.get("cutoff_date") or ""),
        "agency": str(payload.get("agency") or ""),
        "policy_domain": str(payload.get("policy_domain") or ""),
        "subtype": str(payload.get("subtype") or ""),
        "explicit_inputs": inputs,
        "evidence_mode": "holdout",
        "allow_ai_assumptions": False,
    }
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
        "routeKey": route_key,
        "formulaKey": estimate.formula_key,
        "formula": estimate.formula,
        "annualAmountsThousand": list(estimate.annual_amounts_thousand),
        "sourceRefs": list(estimate.source_refs),
        "resolvedVariables": {key: asdict(value) for key, value in estimate.resolved_variables.items()},
    }
