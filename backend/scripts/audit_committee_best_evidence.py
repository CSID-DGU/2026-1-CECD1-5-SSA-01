"""Measure exact and component evidence recall on the manually audited pilot.

Unlike the decision score, this audit also checks whether useful partial
evidence appears in the ranked candidate list.  A safe abstention is not
treated as proof that retrieval coverage is adequate.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts import evaluate_committee_precedent_routes as routes


DEFAULT_CASES = ROOT / "backend/generated/committee_precedent_pilot/pilot_cases.json"
DEFAULT_LABELS = (
    ROOT / "backend/generated/committee_precedent_pilot/manual_best_evidence_labels.json"
)


def _first_rank(ranking: list[dict[str, Any]], bill_nos: set[str]) -> int | None:
    return next(
        (index for index, row in enumerate(ranking, start=1) if row["bill_no"] in bill_nos),
        None,
    )


def audit(cases_path: Path, labels_path: Path) -> dict[str, Any]:
    cases = {
        str(case["bill_no"]): case
        for case in json.loads(cases_path.read_text(encoding="utf-8"))
    }
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    metadata = routes._load_metadata()
    candidates = routes._load_candidate_texts(metadata)
    idf = routes._idf_by_token(candidates.values())
    results: list[dict[str, Any]] = []

    for label in labels:
        bill_no = str(label["bill_no"])
        case = cases[bill_no]
        passages = routes._target_passages(case)
        eligible = [
            candidate
            for candidate in candidates.values()
            if routes._eligible_at_cutoff(
                candidate,
                target_bill_no=bill_no,
                cutoff_date=str(case.get("cutoff_date") or case["propose_date"]),
            )
        ]
        ranking = sorted(
            (
                routes._relation_candidate(case, passages, candidate, idf)
                for candidate in eligible
            ),
            key=lambda row: (
                float(row["relation_score"]),
                row["available_date"],
                row["bill_no"],
            ),
            reverse=True,
        )
        decision, selected = routes._select_relation_candidate(ranking)
        exact = {str(value) for value in label.get("exact_bill_nos") or []}
        component = {
            str(value) for value in label.get("primary_component_bill_nos") or []
        }
        supporting = {str(value) for value in label.get("supporting_bill_nos") or []}
        blocked = {str(value) for value in label.get("metadata_blocked_bill_nos") or []}
        results.append(
            {
                "bill_no": bill_no,
                "status": label["evidence_status"],
                "decision": decision,
                "selected": selected,
                "exact_rank": _first_rank(ranking, exact),
                "component_rank": _first_rank(ranking, component),
                "supporting_rank": _first_rank(ranking, supporting),
                "metadata_blocked_present": sorted(blocked & set(candidates)),
                "top5": [str(row["bill_no"]) for row in ranking[:5]],
                "audit_note": label["audit_note"],
            }
        )

    exact_rows = [row for row in results if row["status"] == "exact_document"]
    component_rows = [
        row
        for row in results
        if row["status"] in {"related_but_stale", "component_bundle"}
    ]
    none_rows = [row for row in results if row["status"] == "none"]

    def recall(rows: list[dict[str, Any]], field: str, cutoff: int) -> str:
        hits = sum(
            row[field] is not None and int(row[field]) <= cutoff
            for row in rows
        )
        return f"{hits}/{len(rows)}"

    return {
        "case_count": len(results),
        "exact_recall_at_1": recall(exact_rows, "exact_rank", 1),
        "exact_recall_at_10": recall(exact_rows, "exact_rank", 10),
        "component_recall_at_5": recall(component_rows, "component_rank", 5),
        "component_recall_at_10": recall(component_rows, "component_rank", 10),
        "safe_none_abstention": (
            f"{sum(row['decision'] == 'abstain' for row in none_rows)}/{len(none_rows)}"
        ),
        "metadata_blocked_count": sum(
            bool(row["metadata_blocked_present"]) for row in results
        ),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = audit(args.cases, args.labels)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(
        f"cases={payload['case_count']} "
        f"exact@1={payload['exact_recall_at_1']} "
        f"exact@10={payload['exact_recall_at_10']} "
        f"component@5={payload['component_recall_at_5']} "
        f"component@10={payload['component_recall_at_10']} "
        f"safe_none={payload['safe_none_abstention']} "
        f"metadata_blocked={payload['metadata_blocked_count']}"
    )
    for row in payload["results"]:
        print(
            f"{row['bill_no']} status={row['status']} decision={row['decision']} "
            f"selected={row['selected'] or '-'} exact_rank={row['exact_rank'] or '-'} "
            f"component_rank={row['component_rank'] or '-'} "
            f"supporting_rank={row['supporting_rank'] or '-'} "
            f"blocked={','.join(row['metadata_blocked_present']) or '-'} "
            f"top5={','.join(row['top5'])}"
        )


if __name__ == "__main__":
    main()
