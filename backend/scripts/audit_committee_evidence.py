"""Audit committee evidence without changing source TAG rows.

The audit deliberately compares three independent layers:
1. normalized operands, 2. the equation printed in the estimate report, and
3. the legacy annual amount row.  This distinguishes a retrieval problem from
an upstream parsing/unit problem.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import statistics
from typing import Any

from backend.scripts.backfill_committee_evidence import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SEED_DIRS,
    _compact,
    _read_jsonl,
)


_FINAL_RESULT = re.compile(
    r"([\d,.]+)(억원|백만원|만원|천원|원)"
    r"(?:≒([\d,.]+)(억원|백만원|만원|천원|원))?"
)
_UNIT_SCALE = {
    "억원": 100_000_000,
    "백만원": 1_000_000,
    "만원": 10_000,
    "천원": 1_000,
    "원": 1,
}


def _explicit_result_won(formula: str) -> float | None:
    compact = _compact(formula)
    if compact.count("=") != 1:
        return None
    match = _FINAL_RESULT.fullmatch(compact.split("=", 1)[1])
    if not match:
        return None
    value = match.group(3) or match.group(1)
    unit = match.group(4) or match.group(2)
    return float(value.replace(",", "")) * _UNIT_SCALE[unit]


def build_audit(
    profiles: list[dict[str, Any]],
    atoms: list[dict[str, Any]],
    amounts: list[dict[str, Any]],
) -> dict[str, Any]:
    profile_by_key = {str(row["profile_key"]): row for row in profiles}
    roles_by_item: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    formulas_by_item: dict[str, list[str]] = defaultdict(list)
    item_profile: dict[str, str] = {}
    for atom in atoms:
        item_id = str(atom.get("source_item_key") or "")
        if not item_id:
            continue
        item_profile[item_id] = str(atom["profile_key"])
        if atom.get("normalized_value") is not None:
            roles_by_item[item_id][str(atom["evidence_role"])].append(
                float(atom["normalized_value"])
            )
        if atom.get("evidence_role") == "formula_expression" and atom.get("formula_text"):
            formulas_by_item[item_id].append(str(atom["formula_text"]))

    operand_checks: list[dict[str, Any]] = []
    for item_id, roles in roles_by_item.items():
        member_role = next(
            (
                role for role in ("paid_members", "incremental_paid_members")
                if len(set(roles.get(role, []))) == 1
            ),
            None,
        )
        if member_role is None or any(
            len(set(roles.get(role, []))) != 1
            for role in ("annual_meetings", "meeting_unit_price")
        ):
            continue
        if roles.get("committee_instances"):
            # Multi-site formulae can use either a sum or separate products;
            # the expression must be parsed before recomputation.
            continue
        product = (
            next(iter(set(roles[member_role])))
            * next(iter(set(roles["annual_meetings"])))
            * next(iter(set(roles["meeting_unit_price"])))
        )
        result = next(
            (
                parsed
                for formula in formulas_by_item.get(item_id, [])
                if (parsed := _explicit_result_won(formula)) is not None
            ),
            None,
        )
        if result is None or result <= 0:
            continue
        error = abs(product - result) / result * 100
        profile = profile_by_key.get(item_profile.get(item_id, ""), {})
        operand_checks.append({
            "bill_no": profile.get("bill_no"),
            "committee_name": profile.get("committee_name"),
            "item_id": item_id,
            "product_won": product,
            "explicit_result_won": result,
            "absolute_error_pct": round(error, 3),
        })

    amount_checks: list[dict[str, Any]] = []
    for amount in amounts:
        if amount.get("is_total") or amount.get("amount_thousand") is None:
            continue
        formula = str(amount.get("formula_text") or "")
        item_id = str(amount.get("item_id") or "")
        if item_id not in item_profile:
            continue
        result = _explicit_result_won(formula)
        if result is None or result <= 0:
            continue
        stored = float(amount["amount_thousand"]) * 1_000
        error = abs(stored - result) / result * 100
        if error <= 1:
            continue
        profile = profile_by_key.get(item_profile.get(item_id, ""), {})
        amount_checks.append({
            "bill_no": profile.get("bill_no"),
            "committee_name": profile.get("committee_name"),
            "item_id": item_id,
            "stored_amount_won": stored,
            "explicit_result_won": result,
            "absolute_error_pct": round(error, 3),
            "formula_text": formula,
        })

    errors = [row["absolute_error_pct"] for row in operand_checks]
    quarantined = [
        row for row in profiles if row.get("raw_attributes", {}).get("quality_issues")
    ]
    unique_amount_checks = {
        (row["item_id"], row["formula_text"]): row for row in amount_checks
    }
    amount_checks = list(unique_amount_checks.values())
    return {
        "profiles": len(profiles),
        "evidence_atoms": len(atoms),
        "operand_formula_checks": len(operand_checks),
        "operand_formula_within_1pct": sum(value <= 1 for value in errors),
        "operand_formula_within_20pct": sum(value <= 20 for value in errors),
        "operand_formula_median_absolute_error_pct": (
            round(statistics.median(errors), 3) if errors else None
        ),
        "quarantined_profile_fields": len(quarantined),
        "legacy_amount_scale_mismatches": len(amount_checks),
        "legacy_amount_scale_mismatch_examples": sorted(
            amount_checks,
            key=lambda row: (-row["absolute_error_pct"], str(row.get("bill_no") or "")),
        )[:20],
        "operand_formula_mismatch_examples": sorted(
            (row for row in operand_checks if row["absolute_error_pct"] > 20),
            key=lambda row: -row["absolute_error_pct"],
        )[:20],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    profiles = _read_jsonl(args.input_dir / "committee_profiles.jsonl")
    atoms = _read_jsonl(args.input_dir / "committee_evidence_atoms.jsonl")
    amounts: list[dict[str, Any]] = []
    for directory in DEFAULT_SEED_DIRS:
        amounts.extend(_read_jsonl(directory / "cost_estimate_amounts.jsonl"))
    audit = build_audit(profiles, atoms, amounts)
    output = json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
