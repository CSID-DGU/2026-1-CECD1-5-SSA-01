"""Summarize local committee50 evidence gaps before any remote DB write."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any


V1_ATOMS = Path("backend/generated/committee_evidence_v1/committee_evidence_atoms.jsonl")


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build(hierarchy_path: Path, semantic_v2_path: Path) -> dict[str, Any]:
    hierarchy = _json(hierarchy_path)
    semantic = _json(semantic_v2_path)
    results = hierarchy["results"]

    exact_links = []
    required = Counter()
    suggested = Counter()
    uncovered = Counter()
    target_count = 0
    for result in results:
        package = result["package"]
        if result["route"] == "exact_legislative_package":
            exact_links.append(
                {
                    "target_bill_no": result["bill_no"],
                    "source_bill_no": package["selected_bill_no"],
                    "link_type": package["relation_route"],
                    "relation_score": package["relation_score"],
                    "status": "candidate",
                    "policy": "review locally before creating committee_precedent_links row",
                }
            )
            continue
        for component in result["components"]:
            target_count += 1
            available = {row["role"] for row in component["suggestions"]}
            suggested.update(available)
            for role in component["missing_roles"]:
                required[role] += 1
                if role not in available:
                    uncovered[role] += 1

    v1_atom_count = sum(
        1 for line in V1_ATOMS.read_text(encoding="utf-8").splitlines() if line.strip()
    )
    promoted = len(semantic["observations"])
    return {
        "schema_version": "committee50-db-cleanup-preview-v1",
        "write_policy": "local_preview_only_no_supabase_mutation",
        "summary": {
            "bill_count": len(results),
            "exact_package_candidates": len(exact_links),
            "hitl_component_targets": target_count,
            "required_operand_count": dict(sorted(required.items())),
            "suggested_operand_count": dict(sorted(suggested.items())),
            "uncovered_operand_count": dict(sorted(uncovered.items())),
            "v1_atom_count": v1_atom_count,
            "safe_v2_observation_count": promoted,
            "quarantined_v1_atom_count": v1_atom_count - promoted,
        },
        "exact_link_candidates": exact_links,
        "safe_v2_summary": semantic["summary"],
        "recommended_order": [
            "Fix and freeze source cost-event/entity extraction before retrieval scoring.",
            "Review exact link candidates as provenance edges, not numeric target labels.",
            "Promote only safe v2 observations; retain ambiguous v1 atoms in quarantine.",
            "Prioritize subject-scoped annual_meetings and paid_members observations.",
            "Re-run regression, then evaluate a new unseen holdout.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hierarchy", type=Path, required=True)
    parser.add_argument("--semantic-v2", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build(args.hierarchy, args.semantic_v2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    for row in payload["exact_link_candidates"]:
        print(
            f"{row['target_bill_no']} -> {row['source_bill_no']} "
            f"route={row['link_type']} score={row['relation_score']}"
        )


if __name__ == "__main__":
    main()
