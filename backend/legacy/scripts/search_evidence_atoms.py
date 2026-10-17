"""Inspect the sidecar narrative-evidence index without changing estimates."""
from __future__ import annotations

import argparse
import json

from backend.erce_web.estimator_v2.evidence_index import (
    evidence_atoms,
    evidence_dataset_fingerprint,
    search_evidence_atoms,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--exclude-bill", action="append", default=[])
    parser.add_argument("--cutoff-date")
    parser.add_argument(
        "--scope",
        action="append",
        choices=[
            "support_office",
            "organization_operation",
            "committee_operation",
            "personnel",
            "research_plan",
            "facility_system",
            "subsidy",
            "tax_revenue",
        ],
    )
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    scopes = set(
        args.scope
        or [
            "support_office",
            "organization_operation",
            "committee_operation",
        ]
    )
    hits = search_evidence_atoms(
        args.query,
        allowed_scopes=scopes,
        exclude_bill_nos=set(args.exclude_bill),
        cutoff_date=args.cutoff_date,
        k=args.k,
        refresh=args.refresh,
    )
    if args.json:
        print(
            json.dumps(
                {
                    "index_version": evidence_dataset_fingerprint(),
                    "atom_count": len(evidence_atoms()),
                    "hits": [hit.to_dict() for hit in hits],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    print(
        f"atoms={len(evidence_atoms())} "
        f"fingerprint={evidence_dataset_fingerprint()}"
    )
    for index, hit in enumerate(hits, start=1):
        atom = hit.atom
        print(
            f"{index:2d}. {atom.bill_no} sem={hit.semantic_similarity:.4f} "
            f"recall={hit.recall_score:.4f} scopes={','.join(atom.scopes)}"
        )
        print(f"    {atom.bill_name} / entities={','.join(atom.entities[:3])}")
        compact_source = " ".join(atom.source_text.split())
        print(f"    {compact_source[:360]}")


if __name__ == "__main__":
    main()
