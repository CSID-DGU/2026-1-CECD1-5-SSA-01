"""Structure regression for the fifteen pre-v5 committee bills."""
from __future__ import annotations

import json
import re

from backend.analyzer_v2 import (
    _extract_pdf_text_from_bytes,
    split_articles,
    strip_appendices,
)
from backend.committee_estimator_v5.structure import (
    extract_committee_events,
    plan_committee_cost,
)
from backend.scripts.evaluate_committee_estimator_v4_audit10 import UNITS as AUDIT_UNITS
from backend.scripts.evaluate_committee_estimator_v4_structure import EXPECTED as STRUCTURE_EXPECTED
from backend.scripts.run_estimator_v2 import _pdf


def _key(value: str) -> str:
    return re.sub(r"[ㆍ·・\s]+", "", value or "")


def _matches(expected: str, actual: str) -> bool:
    expected = _key(expected)
    actual = _key(actual)
    return bool(expected and actual and (expected in actual or actual in expected))


def main() -> None:
    expected: dict[str, list[tuple[str, str]]] = {
        bill_no: list(units) for bill_no, units in STRUCTURE_EXPECTED.items()
    }
    for unit in AUDIT_UNITS:
        expected.setdefault(unit.bill_no, []).append((unit.name, unit.family))

    rows = []
    for bill_no, units in expected.items():
        source = _pdf(bill_no, False)
        if source is None:
            rows.append({"bill_no": bill_no, "failure": "source_missing"})
            continue
        raw = _extract_pdf_text_from_bytes(source.read_bytes())
        articles, _ = split_articles(strip_appendices(raw))
        actual = [
            (event.name, plan_committee_cost(event))
            for event in extract_committee_events(raw, articles)
        ]
        checks = []
        for expected_name, expected_family in units:
            match = next(
                (
                    (name, plan)
                    for name, plan in actual
                    if _matches(expected_name, name)
                ),
                None,
            )
            exact = bool(match and match[1].family == expected_family)
            compatible_alternative = bool(
                match
                and expected_family == "analog_flat_operating_budget"
                and "structurally_identical_whole_budget_precedent"
                in match[1].evidence_alternatives
            )
            checks.append({
                "expected_name": expected_name,
                "expected_family": expected_family,
                "detected_name": match[0] if match else None,
                "detected_family": match[1].family if match else None,
                "detected": bool(match),
                "exact_family_match": exact,
                "compatible_formula_path": exact or compatible_alternative,
            })
        rows.append({"bill_no": bill_no, "checks": checks})

    checks = [check for row in rows for check in row.get("checks", [])]
    payload = {
        "evaluation_type": "v5_prior_fifteen_structure_regression",
        "bill_count": len(expected),
        "official_formula_unit_count": len(checks),
        "detected_count": sum(bool(value["detected"]) for value in checks),
        "exact_family_match_count": sum(
            bool(value["exact_family_match"]) for value in checks
        ),
        "compatible_formula_path_count": sum(
            bool(value["compatible_formula_path"]) for value in checks
        ),
        "rows": rows,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
