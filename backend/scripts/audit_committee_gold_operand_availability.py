"""Measure value presence separately from usable evidence in the dev gold set.

The script is diagnostic only.  Gold values never enter a recommender.  It
answers whether a miss is caused by retrieval or by missing/unsafe evidence.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.committee_component_evidence_engine import (
    ATOM_PATH,
    PROFILE_PATH,
    _available_dates,
    _compact,
    _kind,
    _price_value,
)


GOLD_PATH = ROOT / "backend/fixtures/committee_component_dev_gold.json"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _value(atom: dict[str, Any], role: str) -> float | None:
    if role == "meeting_unit_price":
        return _price_value(atom)
    try:
        return float(atom.get("normalized_value"))
    except (TypeError, ValueError):
        return None


def _available(profile: dict[str, Any], target: dict[str, Any]) -> bool:
    bill_no = str(profile.get("bill_no") or "")
    date = str(_available_dates().get(bill_no) or "")
    return bool(
        bill_no
        and bill_no != str(target["bill_no"])
        and date
        and date <= str(target["cutoff_date"])
    )


def _subject_safe(atom: dict[str, Any], profile: dict[str, Any], role: str) -> bool:
    kind = _kind(atom)
    if role == "meeting_unit_price":
        return kind in {"official_guideline", "official_guideline_prior"}
    if kind != "reported_actual":
        return False
    name = _compact(str(profile.get("normalized_name") or ""))
    text = _compact(str(atom.get("source_text") or ""))
    return bool(name and name in text)


def audit() -> dict[str, Any]:
    profiles = _jsonl(PROFILE_PATH)
    atoms = _jsonl(ATOM_PATH)
    profiles_by_key = {str(row["profile_key"]): row for row in profiles}
    gold = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    output: list[dict[str, Any]] = []
    roles = ("paid_members", "annual_meetings", "meeting_unit_price")
    for target in gold:
        role_rows: dict[str, Any] = {}
        for role in roles:
            expected = target["operands"].get(role)
            if expected is None:
                continue
            exact_any: list[dict[str, Any]] = []
            exact_available: list[dict[str, Any]] = []
            exact_safe: list[dict[str, Any]] = []
            for atom in atoms:
                if atom.get("evidence_role") != role:
                    continue
                value = _value(atom, role)
                if value is None or abs(value - float(expected)) > 0.5:
                    continue
                profile = profiles_by_key.get(str(atom.get("profile_key") or ""), {})
                row = {
                    "bill_no": str(profile.get("bill_no") or ""),
                    "committee_name": str(profile.get("normalized_name") or ""),
                    "kind": _kind(atom),
                    "source_text": str(atom.get("source_text") or "")[:260],
                }
                exact_any.append(row)
                if _available(profile, target):
                    exact_available.append(row)
                    if _subject_safe(atom, profile, role):
                        exact_safe.append(row)
            role_rows[role] = {
                "expected": expected,
                "exact_value_anywhere": len(exact_any),
                "exact_value_available_at_cutoff": len(exact_available),
                "exact_value_subject_safe": len(exact_safe),
                "safe_examples": exact_safe[:3],
            }
        output.append(
            {
                "bill_no": target["bill_no"],
                "committee_name": target["committee_name"],
                "formula_kind": target["formula_kind"],
                "roles": role_rows,
            }
        )
    return {"case_count": len(output), "results": output}


def main() -> None:
    print(json.dumps(audit(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
