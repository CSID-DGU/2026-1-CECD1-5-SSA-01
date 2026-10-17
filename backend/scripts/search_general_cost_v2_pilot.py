"""Search the isolated v2 goods-services pilot DB.

Retrieval is intentionally two-stage: structured route filters first, then FTS
and optional cached-vector similarity.  Evidence, formula and operands are
returned together so a match cannot silently detach a number from its source.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Any

from backend.scripts.build_general_cost_v2_pilot import DEFAULT_DB


def _terms(query: str) -> list[str]:
    return [term for term in re.findall(r"[0-9A-Za-z가-힣]+", query) if len(term) >= 2]


def _fts_query(query: str) -> str:
    terms = _terms(query)
    return " OR ".join(f'"{term}"' for term in terms)


def _ngrams(text: str, n: int = 2) -> set[str]:
    compact = re.sub(r"[^0-9A-Za-z가-힣]", "", text or "").lower()
    if not compact:
        return set()
    return {compact[index:index + n] for index in range(max(1, len(compact) - n + 1))}


def _lexical_overlap(query: str, text: str) -> float:
    left, right = _ngrams(query), _ngrams(text)
    return len(left & right) / max(len(left), 1)


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    norm_left = math.sqrt(sum(value * value for value in left))
    norm_right = math.sqrt(sum(value * value for value in right))
    return dot / (norm_left * norm_right) if norm_left and norm_right else 0.0


def search(
    database: Path,
    query: str,
    *,
    mechanism: str = "",
    component: str = "",
    query_item_id: str = "",
    query_vector: list[float] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    conditions = ["i.cost_nature = 'goods_services'"]
    parameters: list[Any] = []
    if mechanism:
        if mechanism == "information_system":
            conditions.append("i.mechanism like ?")
            parameters.append("information_system%")
        else:
            conditions.append("i.mechanism = ?")
            parameters.append(mechanism)
    if component:
        conditions.append("i.component = ?")
        parameters.append(component)
    where = " and ".join(conditions)

    fts = _fts_query(query)
    fts_scores: dict[str, float] = {}
    if fts:
        try:
            rows = connection.execute(
                f"""select i.item_id, bm25(cost_items_fts) as rank
                    from cost_items_fts
                    join cost_items i on i.item_id = cost_items_fts.item_id
                    where cost_items_fts match ? and {where}
                    order by rank limit 100""",
                [fts, *parameters],
            ).fetchall()
            for index, row in enumerate(rows):
                fts_scores[str(row["item_id"])] = 1.0 / (1.0 + index)
        except sqlite3.OperationalError:
            fts_scores = {}

    effective_query_vector = list(query_vector or [])
    if query_item_id and not effective_query_vector:
        row = connection.execute(
            "select vector_json from item_embeddings where item_id = ?", (query_item_id,)
        ).fetchone()
        if row:
            effective_query_vector = [float(value) for value in json.loads(row["vector_json"])]

    candidates = connection.execute(
        f"""select i.*, f.formula_key, f.selection_status, f.missing_variables_json,
                   e.vector_json
            from cost_items i
            left join item_formula_links f on f.item_id = i.item_id
            left join item_embeddings e on e.item_id = i.item_id
            where {where}""",
        parameters,
    ).fetchall()
    ranked: list[tuple[float, sqlite3.Row, float, float]] = []
    for row in candidates:
        if query_item_id and row["item_id"] == query_item_id:
            continue
        searchable = " ".join(
            str(row[key] or "")
            for key in ("item_name", "bill_name", "mechanism", "component")
        )
        lexical = max(fts_scores.get(str(row["item_id"]), 0.0), _lexical_overlap(query, searchable))
        semantic = 0.0
        if effective_query_vector and row["vector_json"]:
            semantic = _cosine(effective_query_vector, json.loads(row["vector_json"]))
        score = lexical if not effective_query_vector else 0.30 * lexical + 0.70 * semantic
        ranked.append((score, row, lexical, semantic))
    ranked.sort(key=lambda value: (-value[0], str(value[1]["bill_no"]), str(value[1]["item_name"])))

    results: list[dict[str, Any]] = []
    for score, row, lexical, semantic in ranked[:limit]:
        item_id = str(row["item_id"])
        variables = [dict(value) for value in connection.execute(
            """select canonical_key,raw_name,normalized_value,normalized_unit,basis_year,
                      source_class,transfer_policy,review_status
               from variables where item_id=? order by canonical_key,raw_name""",
            (item_id,),
        )]
        amounts = [dict(value) for value in connection.execute(
            """select year_label,year_offset,amount_thousand,formula_text,is_total,review_status
               from amount_observations where item_id=? order by is_total,year_offset""",
            (item_id,),
        )]
        evidence = [dict(value) for value in connection.execute(
            """select entity_type,page_no,locator_query,quote_text,locator_method,locator_score,chunk_id
               from evidence_links
               where (entity_type='item' and entity_id=?)
                  or (entity_type='formula' and entity_id like ?)
                  or (entity_type='variable' and entity_id in
                      (select variable_id from variables where item_id=?))
                  or (entity_type='amount' and entity_id in
                      (select observation_id from amount_observations where item_id=?))
               order by entity_type,page_no""",
            (item_id, f"{item_id}:%", item_id, item_id),
        )]
        results.append({
            "score": round(score, 6),
            "lexical_score": round(lexical, 6),
            "semantic_score": round(semantic, 6),
            "item_id": item_id,
            "bill_no": row["bill_no"],
            "bill_name": row["bill_name"],
            "item_name": row["item_name"],
            "cost_nature": row["cost_nature"],
            "mechanism": row["mechanism"],
            "component": row["component"],
            "priced_scopes": json.loads(row["priced_scopes_json"]),
            "formula_key": row["formula_key"],
            "formula_readiness": row["selection_status"],
            "missing_variables": json.loads(row["missing_variables_json"] or "[]"),
            "review_status": row["review_status"],
            "variables": variables,
            "amounts": amounts,
            "evidence": evidence,
        })
    connection.close()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Search v2 goods-services pilot DB")
    parser.add_argument("query")
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--mechanism", default="")
    parser.add_argument("--component", default="")
    parser.add_argument("--query-item-id", default="")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    results = search(
        args.database, args.query, mechanism=args.mechanism, component=args.component,
        query_item_id=args.query_item_id, limit=args.limit,
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
