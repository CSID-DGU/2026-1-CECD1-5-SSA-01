"""Evaluate retrieval quality for the isolated goods-services v2 pilot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import time
from typing import Any

from backend.erce_web.config import get_env
from backend.legacy.scripts.build_general_cost_v2_pilot import DEFAULT_DB, DEFAULT_OUTPUT_DIR
from backend.legacy.scripts.search_general_cost_v2_pilot import search


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE = ROOT / "backend/legacy/fixtures/general_cost_v2_goods_pilot_queries.json"
DEFAULT_OUTPUT = DEFAULT_OUTPUT_DIR / "retrieval_benchmark.json"


def _is_expected(row: dict[str, Any], case: dict[str, Any]) -> bool:
    return (
        str(row.get("bill_no")) == str(case["expected_bill_no"])
        and str(case["expected_item_contains"]) in str(row.get("item_name") or "")
    )


def _embed_queries(queries: list[str]) -> list[list[float]]:
    api_key = get_env("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    from backend.legacy.scripts.embed_chunks import embed_batch
    return embed_batch(queries, api_key)


def evaluate_mode(
    database: Path,
    cases: list[dict[str, Any]],
    *,
    mode: str,
    vectors: list[list[float]] | None = None,
) -> dict[str, Any]:
    routed = mode.endswith("_routed")
    hybrid = mode.startswith("hybrid_")
    details = []
    latencies = []
    reciprocal_ranks = []
    top1 = top3 = evidence_hits = 0
    for index, case in enumerate(cases):
        started = time.perf_counter()
        rows = search(
            database,
            str(case["query"]),
            mechanism=str(case["expected_mechanism"]) if routed else "",
            query_vector=(vectors[index] if hybrid and vectors else None),
            limit=5,
        )
        latencies.append((time.perf_counter() - started) * 1000)
        rank = next((position for position, row in enumerate(rows, start=1) if _is_expected(row, case)), None)
        top1 += int(rank == 1)
        top3 += int(rank is not None and rank <= 3)
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        expected_row = rows[rank - 1] if rank else None
        evidence_ok = bool(
            expected_row
            and expected_row.get("evidence")
            and all(link.get("page_no") is not None for link in expected_row["evidence"])
        )
        evidence_hits += int(evidence_ok)
        details.append({
            "case_id": case["case_id"],
            "rank": rank,
            "expected_bill_no": case["expected_bill_no"],
            "expected_item_contains": case["expected_item_contains"],
            "top_results": [
                {
                    "bill_no": row["bill_no"],
                    "item_name": row["item_name"],
                    "mechanism": row["mechanism"],
                    "score": row["score"],
                    "formula_key": row["formula_key"],
                    "formula_readiness": row["formula_readiness"],
                }
                for row in rows[:3]
            ],
            "expected_evidence_complete": evidence_ok,
        })
    count = len(cases)
    sorted_latency = sorted(latencies)
    return {
        "mode": mode,
        "cases": count,
        "top1_accuracy": round(top1 / count, 6),
        "top3_accuracy": round(top3 / count, 6),
        "mrr": round(statistics.mean(reciprocal_ranks), 6),
        "expected_evidence_completeness": round(evidence_hits / count, 6),
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 3),
            "p50": round(statistics.median(latencies), 3),
            "p95": round(sorted_latency[max(0, int(count * 0.95) - 1)], 3),
            "max": round(max(latencies), 3),
        },
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate v2 goods-services pilot retrieval")
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--with-embeddings", action="store_true")
    args = parser.parse_args()
    cases = json.loads(args.fixture.read_text(encoding="utf-8"))
    vectors = None
    embedding_ms = None
    if args.with_embeddings:
        started = time.perf_counter()
        vectors = _embed_queries([str(case["query"]) for case in cases])
        embedding_ms = round((time.perf_counter() - started) * 1000, 3)
    modes = ["lexical_unfiltered", "lexical_routed"]
    if vectors:
        modes.extend(("hybrid_unfiltered", "hybrid_routed"))
    report = {
        "fixture": str(args.fixture),
        "database": str(args.database),
        "query_embedding_batch_ms": embedding_ms,
        "modes": [
            evaluate_mode(args.database, cases, mode=mode, vectors=vectors)
            for mode in modes
        ],
        "limitations": [
            "development pilot only; validation holdout is untouched",
            "five queries are a schema/retrieval smoke test, not a production confidence interval",
            "routed modes use the gold mechanism and therefore do not measure router accuracy",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

