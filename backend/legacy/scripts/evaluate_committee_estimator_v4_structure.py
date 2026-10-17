"""Evaluate v4 structural extraction and formula routing.

The expected families are evaluator-only labels derived from the official
cost-estimate calculation descriptions.  Runtime code never imports this
module and never reads an answer PDF.  These five cases are regression cases,
not an unseen holdout, because their errors informed the v4 architecture.
"""
from __future__ import annotations

import json
import re

from backend.analyzer_v2 import (
    _extract_pdf_text_from_bytes,
    split_articles,
    strip_appendices,
)
from backend.legacy.committee.committee_estimator_v4.pipeline import ENGINE_VERSION
from backend.legacy.committee.committee_estimator_v4.structure import (
    extract_committee_nodes,
    select_formula_plan,
)
from backend.legacy.scripts.run_estimator_v2 import _pdf


EXPECTED: dict[str, tuple[tuple[str, str], ...]] = {
    "2124970": (
        ("대전특별자치시지원위원회", "committee_support_bundle"),
        ("연구개발위원회", "analog_flat_operating_budget"),
    ),
    "2215935": (
        ("시민고충처리위원회", "multi_instance_operating_baseline"),
    ),
    "2216468": (
        ("대구경북특별시지원위원회", "committee_support_bundle"),
        ("대구경북특별시종합계획심의회", "meeting_allowance"),
    ),
    "2216517": (
        ("전남광주통합특별시지원위원회", "committee_support_bundle"),
        ("기본계획심의회", "meeting_allowance"),
        ("갯벌관리위원회", "meeting_allowance"),
    ),
    "2216520": (
        ("충남대전통합특별시지원위원회", "committee_support_bundle"),
        ("기본계획심의회", "meeting_allowance"),
        ("산림복지심의위원회", "meeting_allowance"),
        ("섬발전심의위원회", "meeting_allowance"),
        ("갯벌관리위원회", "meeting_allowance"),
    ),
}


def _key(value: str) -> str:
    return re.sub(r"[ㆍ·・\s]+", "", value or "")


def main() -> None:
    rows: list[dict[str, object]] = []
    for bill_no, expected in EXPECTED.items():
        source = _pdf(bill_no, False)
        if source is None:
            rows.append({"bill_no": bill_no, "failure": "source_pdf_missing"})
            continue
        raw = _extract_pdf_text_from_bytes(source.read_bytes())
        articles, _ = split_articles(strip_appendices(raw))
        nodes = extract_committee_nodes(articles)
        actual = [
            (node.name, select_formula_plan(node).family)
            for node in nodes
        ]
        checks: list[dict[str, object]] = []
        for expected_name, expected_family in expected:
            matched = next(
                (
                    (name, family)
                    for name, family in actual
                    if _key(expected_name) in _key(name)
                    or _key(name) in _key(expected_name)
                ),
                None,
            )
            checks.append({
                "expected_name": expected_name,
                "expected_family": expected_family,
                "detected_name": matched[0] if matched else None,
                "detected_family": matched[1] if matched else None,
                "pass": bool(matched and matched[1] == expected_family),
            })
        rows.append({
            "bill_no": bill_no,
            "article_count": len(articles),
            "all_candidate_count": len(actual),
            "expected_checks": checks,
        })

    checks = [
        check
        for row in rows
        for check in row.get("expected_checks", [])
    ]
    print(json.dumps({
        "evaluation_type": "v4_relation_and_formula_regression",
        "engine_version": ENGINE_VERSION,
        "bill_count": len(EXPECTED),
        "official_formula_unit_count": len(checks),
        "detected_count": sum(bool(row["detected_name"]) for row in checks),
        "formula_family_pass_count": sum(bool(row["pass"]) for row in checks),
        "formula_family_accuracy": round(
            sum(bool(row["pass"]) for row in checks) / len(checks), 3
        ) if checks else None,
        "rows": rows,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
