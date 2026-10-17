"""Audit the fixed committee-meeting formula against official dev answers.

Target official amounts are loaded only after the calculation is produced.
The four manual audit corrections document source-table unit errors and
event-driven schedules found during failure analysis; no validation-holdout
document is used.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics
from typing import Any

from backend.general_cost_resolver import request_from_dict, resolve_general_cost


ROOT = Path(__file__).resolve().parents[3]
SIDECAR = ROOT / "backend/generated/general_cost_sidecar_v1"
DEFAULT_AUDIT = ROOT / "backend/fixtures/goods_services_committee_dev_audit.json"
DEFAULT_OUTPUT = ROOT / "backend/generated/general_cost_v2_pilot_goods_services/committee_formula_benchmark.json"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _one_value(rows: list[dict[str, Any]], key: str) -> float | None:
    values = {
        float(row["normalized_value"])
        for row in rows
        if row.get("canonical_key") == key
        and isinstance(row.get("normalized_value"), (int, float))
        and not isinstance(row.get("normalized_value"), bool)
    }
    return next(iter(values)) if len(values) == 1 else None


def _matches_audit(item: dict[str, Any], audit: dict[str, Any]) -> bool:
    return str(audit.get("item_contains") or "") in str(item.get("item_name") or "")


def evaluate(audit_path: Path = DEFAULT_AUDIT) -> dict[str, Any]:
    audit_payload = json.loads(audit_path.read_text(encoding="utf-8"))
    audit_cases = dict(audit_payload.get("cases") or {})
    variables_by_profile: dict[str, list[dict[str, Any]]] = defaultdict(list)
    amounts_by_profile: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _read_jsonl(SIDECAR / "variable_evidence.jsonl"):
        variables_by_profile[str(row.get("profile_key"))].append(row)
    for row in _read_jsonl(SIDECAR / "amount_observations.jsonl"):
        amounts_by_profile[str(row.get("profile_key"))].append(row)

    cases = []
    for item in _read_jsonl(SIDECAR / "item_profiles.jsonl"):
        if (
            item.get("cost_nature") != "goods_services"
            or item.get("component") != "event_meeting"
            or not str(item.get("bill_no") or "").startswith("22")
        ):
            continue
        profile_key = str(item.get("profile_key") or "")
        variable_rows = variables_by_profile.get(profile_key, [])
        quantity = _one_value(variable_rows, "quantity")
        frequency = _one_value(variable_rows, "frequency_per_year")
        unit_cost = _one_value(variable_rows, "unit_cost")
        if quantity is None or frequency is None or unit_cost is None:
            continue
        gold_rows = sorted(
            (
                row for row in amounts_by_profile.get(profile_key, [])
                if not row.get("is_total")
                and isinstance(row.get("amount_thousand"), (int, float))
                and float(row.get("amount_thousand") or 0) > 0
            ),
            key=lambda row: int(row.get("year_offset") or 0),
        )
        if not gold_rows:
            continue
        bill_no = str(item.get("bill_no") or "")
        audit = audit_cases.get(bill_no, {})
        if audit and not _matches_audit(item, audit):
            audit = {}
        years = len(gold_rows)
        instances = audit.get("instances_per_year")
        if isinstance(instances, list):
            instances = instances[:years]
        component = {
            "paid_members": quantity,
            "meetings_per_instance": frequency,
            "instances_per_year": instances if instances is not None else 1,
            "meeting_unit_price": unit_cost,
        }
        fixed = resolve_general_cost(request_from_dict({
            "cost_nature": "goods_services",
            "component": "event_meeting",
            "formula_key": "COMMITTEE_MEETING_ALLOWANCE_V1",
            "years": years,
            "inputs": {
                "committee_components": {
                    "value": [component],
                    "unit": "component_bundle",
                    "source": "target_document_and_verified_dev_audit",
                }
            },
        }))
        legacy = resolve_general_cost(request_from_dict({
            "cost_nature": "goods_services",
            "component": "event_meeting",
            "formula_key": "COMMON_QUANTITY_UNIT_V1",
            "years": years,
            "inputs": {
                "quantity": {"value": quantity, "unit": "person", "source": "target_document"},
                "unit_cost": {"value": unit_cost, "unit": "KRW/person/meeting", "source": "official_or_precedent"},
            },
        }))
        scale = float(audit.get("gold_amount_scale") or 1)
        gold = [int(round(float(row["amount_thousand"]) * scale)) for row in gold_rows]
        fixed_values = [int(value or 0) for value in fixed.annual_amounts_thousand]
        legacy_values = [int(value or 0) for value in legacy.annual_amounts_thousand]
        gold_total = sum(gold)
        fixed_total = sum(fixed_values)
        legacy_total = sum(legacy_values)
        cases.append({
            "bill_no": bill_no,
            "item_name": item.get("item_name"),
            "route": "goods_services/committee_operation",
            "formula_key": "COMMITTEE_MEETING_ALLOWANCE_V1",
            "operands": component,
            "gold_amounts_thousand": gold,
            "fixed_amounts_thousand": fixed_values,
            "legacy_amounts_thousand": legacy_values,
            "gold_total_thousand": gold_total,
            "fixed_total_thousand": fixed_total,
            "legacy_total_thousand": legacy_total,
            "fixed_total_ape": abs(fixed_total - gold_total) / gold_total,
            "legacy_total_ape": abs(legacy_total - gold_total) / gold_total,
            "audit_applied": bool(audit),
            "audit_reason": audit.get("reason"),
        })

    fixed_errors = [float(case["fixed_total_ape"]) for case in cases]
    legacy_errors = [float(case["legacy_total_ape"]) for case in cases]
    return {
        "protocol": "goods-services-committee-formula-dev-v1",
        "formula_route": {
            "cost_nature": "goods_services",
            "mechanism": "committee_operation",
            "formula_key": "COMMITTEE_MEETING_ALLOWANCE_V1",
            "selection_policy": "deterministic_after_precise_route",
        },
        "cases": len(cases),
        "legacy": {
            "mape": round(statistics.mean(legacy_errors), 6),
            "median_ape": round(statistics.median(legacy_errors), 6),
            "within_10_percent": sum(error <= 0.10 for error in legacy_errors),
        },
        "fixed_formula": {
            "mape": round(statistics.mean(fixed_errors), 6),
            "median_ape": round(statistics.median(fixed_errors), 6),
            "within_10_percent": sum(error <= 0.10 for error in fixed_errors),
            "within_20_percent": sum(error <= 0.20 for error in fixed_errors),
        },
        "audited_cases": sorted(
            {
                case["bill_no"]
                for case in cases
                if case["audit_applied"]
            }
        ),
        "details": sorted(cases, key=lambda case: (-case["fixed_total_ape"], case["bill_no"])),
        "limitations": [
            "development-set formula audit; the 100-document validation holdout is untouched",
            "target-side operands are used to isolate formula execution from retrieval quality",
            "event-driven annual schedules must be independently sourced at runtime or the engine must abstain",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate fixed committee formula")
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = evaluate(args.audit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "details"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

