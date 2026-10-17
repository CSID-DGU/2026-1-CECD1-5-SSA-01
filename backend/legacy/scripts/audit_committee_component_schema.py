"""Audit whether committee evidence is fit for component-level transfer.

This is an offline diagnostic.  It does not import into the estimator or
change the database.  The audit distinguishes storage integrity from
evidence fitness: a perfectly joined row can still be an assumption that
must not be transferred to a new bill.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.erce_web.estimator import tag_db


PROFILE_PATH = ROOT / "backend/generated/committee_evidence_v1/committee_profiles.jsonl"
ATOM_PATH = ROOT / "backend/generated/committee_evidence_v1/committee_evidence_atoms.jsonl"
OPERAND_ROLES = ("paid_members", "annual_meetings", "meeting_unit_price")
FORMULA_SIGNATURES = {
    "paid_members*annual_meetings*meeting_unit_price",
    "committee_instances*paid_members*annual_meetings*meeting_unit_price",
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _positive_values(rows: list[dict[str, Any]], role: str) -> set[float]:
    values: set[float] = set()
    for row in rows:
        if row.get("evidence_role") != role:
            continue
        try:
            value = float(row.get("normalized_value"))
        except (TypeError, ValueError):
            continue
        if value > 0:
            values.add(value)
    return values


def audit() -> dict[str, Any]:
    profiles = _read_jsonl(PROFILE_PATH)
    atoms = _read_jsonl(ATOM_PATH)
    atoms_by_profile: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for atom in atoms:
        atoms_by_profile[str(atom["profile_key"])].append(atom)

    tag_item_keys = set(tag_db._load()["items"])
    source_item_keys = {
        str(atom["source_item_key"])
        for atom in atoms
        if atom.get("source_item_key")
    }

    formula_profiles = [
        profile
        for profile in profiles
        if profile.get("formula_signature") in FORMULA_SIGNATURES
    ]
    formula_ready = 0
    formula_unambiguous = 0
    formula_all_direct = 0
    formula_high_grade = 0
    profiles_with_assumption_operand = 0
    for profile in formula_profiles:
        rows = atoms_by_profile[str(profile["profile_key"])]
        values = {role: _positive_values(rows, role) for role in OPERAND_ROLES}
        if all(values[role] for role in OPERAND_ROLES):
            formula_ready += 1
        if all(len(values[role]) == 1 for role in OPERAND_ROLES):
            formula_unambiguous += 1

        operand_rows = [
            row
            for row in rows
            if row.get("evidence_role") in OPERAND_ROLES
            and row.get("normalized_value") not in (None, "")
        ]
        if operand_rows and all(row.get("transferability") == "direct" for row in operand_rows):
            formula_all_direct += 1

        grade_by_role = {
            "paid_members": {"reported_actual"},
            "annual_meetings": {"reported_actual"},
            "meeting_unit_price": {"reported_actual", "official_guideline"},
        }
        if all(
            any(
                row.get("evidence_role") == role
                and row.get("normalized_value") not in (None, "")
                and row.get("derivation_type") in grade_by_role[role]
                for row in rows
            )
            for role in OPERAND_ROLES
        ):
            formula_high_grade += 1
        if any(row.get("derivation_type") == "assumption" for row in operand_rows):
            profiles_with_assumption_operand += 1

    signatures: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for profile in formula_profiles:
        signatures[
            (
                profile.get("function_class"),
                profile.get("lifecycle"),
                profile.get("total_member_count"),
                bool(profile.get("has_subcommittee")),
                bool(profile.get("has_secretariat")),
            )
        ].append(profile)
    ambiguous_signature_groups = 0
    ambiguous_signature_profiles = 0
    for group in signatures.values():
        if len(group) < 2:
            continue
        meeting_values: set[float] = set()
        price_values: set[float] = set()
        for profile in group:
            rows = atoms_by_profile[str(profile["profile_key"])]
            meeting_values.update(_positive_values(rows, "annual_meetings"))
            price_values.update(_positive_values(rows, "meeting_unit_price"))
        if len(meeting_values) > 1 or len(price_values) > 1:
            ambiguous_signature_groups += 1
            ambiguous_signature_profiles += len(group)

    numeric_operands = [
        atom
        for atom in atoms
        if atom.get("evidence_role") in OPERAND_ROLES
        and atom.get("normalized_value") not in (None, "")
    ]
    price_outliers = [
        {
            "profile_key": atom["profile_key"],
            "value": atom.get("normalized_value"),
            "unit": atom.get("normalized_unit"),
            "source_text": str(atom.get("source_text") or "")[:240],
        }
        for atom in numeric_operands
        if atom.get("evidence_role") == "meeting_unit_price"
        and float(atom.get("normalized_value") or 0) > 1_000_000
    ]

    normalized_name_groups: dict[str, set[str]] = defaultdict(set)
    for profile in profiles:
        normalized_name_groups[str(profile.get("normalized_name") or "")].add(
            str(profile.get("bill_no") or "")
        )
    history_groups = {
        name: bill_nos
        for name, bill_nos in normalized_name_groups.items()
        if name and len(bill_nos) > 1
    }

    return {
        "storage_integrity": {
            "profiles": len(profiles),
            "atoms": len(atoms),
            "orphan_atoms": sum(
                str(atom["profile_key"])
                not in {str(profile["profile_key"]) for profile in profiles}
                for atom in atoms
            ),
            "source_item_keys": len(source_item_keys),
            "source_item_keys_joined_to_tag": len(source_item_keys & tag_item_keys),
            "source_item_keys_unjoined": len(source_item_keys - tag_item_keys),
            "same_normalized_name_history_groups": len(history_groups),
        },
        "review_state": {
            "profile_status": dict(Counter(str(row.get("profile_status")) for row in profiles)),
            "profiles_requiring_review": sum(bool(row.get("requires_review")) for row in profiles),
            "atom_review_status": dict(Counter(str(row.get("review_status")) for row in atoms)),
            "atom_transferability": dict(Counter(str(row.get("transferability")) for row in atoms)),
        },
        "formula_fitness": {
            "canonical_formula_profiles": len(formula_profiles),
            "profiles_with_all_three_numeric_operands": formula_ready,
            "profiles_with_one_unambiguous_value_per_operand": formula_unambiguous,
            "profiles_with_all_numeric_operands_marked_direct": formula_all_direct,
            "profiles_with_high_grade_actual_or_guideline_for_all_operands": formula_high_grade,
            "profiles_with_at_least_one_assumption_operand": profiles_with_assumption_operand,
        },
        "operand_quality": {
            "numeric_operand_atoms": len(numeric_operands),
            "derivation_type": dict(Counter(str(row.get("derivation_type")) for row in numeric_operands)),
            "transferability": dict(Counter(str(row.get("transferability")) for row in numeric_operands)),
            "basis_year_present": sum(row.get("basis_year") is not None for row in numeric_operands),
            "validity_window_present": sum(
                row.get("valid_from") is not None or row.get("valid_to") is not None
                for row in numeric_operands
            ),
            "meeting_unit_price_over_1m_count": len(price_outliers),
            "meeting_unit_price_over_1m_examples": price_outliers[:10],
        },
        "ranking_separability": {
            "structural_signature_groups": len(signatures),
            "ambiguous_multi_profile_signature_groups": ambiguous_signature_groups,
            "profiles_in_ambiguous_signature_groups": ambiguous_signature_profiles,
            "note": (
                "Identical function/lifecycle/member/subcommittee/secretariat metadata "
                "still contains different meeting-frequency or unit-price values."
            ),
        },
        "schema_gaps": [
            "No explicit evidence_subject_name/type separates target assumptions from external comparator facts.",
            "No measurement_scope distinguishes per-person/per-meeting price from whole-meeting or annual operating cost.",
            "All atoms are still candidate review status, so verified evidence cannot be selected in production.",
            "Operational frequency needs workload/actual-use metadata beyond generic committee structure.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = audit()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
