"""Audit the current source-only committee entity gate on all 50 local bills.

This is a pre-retrieval diagnostic. It never opens answer PDFs and never
calls an LLM. A noisy or missing target entity would otherwise make a RAG
evaluation measure bad query construction rather than evidence retrieval.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
from typing import Any

from backend.article_extraction_engine import extract_pdf_text, split_articles_regex
from backend.committee_gate import group_committee_articles
from backend.scripts.build_committee50_manifest import build_manifest


_SUSPICIOUS_NAME = re.compile(
    r"그밖에|사항외|경우|규정한|필요하다|인정하여|제외한|"
    r"바에따라|관련된|규정한사항|바라에따라|위원장이|제외하여|포함하여"
)


def _compact(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value)


def _nested_duplicates(names: list[str]) -> list[tuple[str, str]]:
    compact = {name: _compact(name) for name in names}
    pairs: list[tuple[str, str]] = []
    for left, left_norm in compact.items():
        for right, right_norm in compact.items():
            if left == right:
                continue
            if len(right_norm) >= 4 and right_norm in left_norm and len(left_norm) > len(right_norm):
                pairs.append((left, right))
    return sorted(set(pairs))


def audit() -> dict[str, Any]:
    manifest = build_manifest()
    rows: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        source = Path(case["source_pdf"]["resolved_path"])
        text = extract_pdf_text(source.read_bytes())
        articles = split_articles_regex(text)
        entities = group_committee_articles(articles)
        names = [entity.name for entity in entities]
        suspicious = [name for name in names if _SUSPICIOUS_NAME.search(name)]
        nested = _nested_duplicates(names)
        rows.append(
            {
                "bill_no": case["bill_no"],
                "article_count": len(articles),
                "entity_count": len(entities),
                "entity_names": names,
                "suspicious_names": suspicious,
                "nested_duplicate_pairs": [list(pair) for pair in nested],
                "source_gate_status": (
                    "missing"
                    if not names
                    else "noisy"
                    if suspicious or nested
                    else "clean_candidate"
                ),
            }
        )

    statuses = Counter(row["source_gate_status"] for row in rows)
    return {
        "schema_version": "committee50-source-entity-audit-v1",
        "evaluation_policy": "source_pdf_only_no_llm_no_answer_pdf",
        "summary": {
            "case_count": len(rows),
            "article_extraction_success": sum(row["article_count"] > 0 for row in rows),
            "entity_detection_success": sum(row["entity_count"] > 0 for row in rows),
            "status_distribution": dict(sorted(statuses.items())),
            "safe_for_unreviewed_retrieval": sum(
                row["source_gate_status"] == "clean_candidate" for row in rows
            ),
        },
        "cases": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print("problem_cases")
    for row in payload["cases"]:
        if row["source_gate_status"] != "clean_candidate":
            print(
                row["bill_no"],
                row["source_gate_status"],
                f"entities={row['entity_count']}",
                f"suspicious={len(row['suspicious_names'])}",
                f"nested={len(row['nested_duplicate_pairs'])}",
            )


if __name__ == "__main__":
    main()
