from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import GENERATED_DIR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search the local assembly RAG seed index.")
    parser.add_argument("query", help="Search query.")
    parser.add_argument(
        "--index",
        type=Path,
        default=GENERATED_DIR / "assembly_rag_seed" / "chunks.jsonl",
        help="chunks.jsonl path.",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Number of results.")
    return parser.parse_args()


def score_text(query: str, text: str) -> float:
    tokens = set(re.findall(r"[0-9A-Za-z가-힣]{2,}", query.lower()))
    body = text.lower()
    return sum(1.0 for t in tokens if t in body) / max(len(tokens), 1)


def compact_text(text: str, limit: int = 260) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def main() -> None:
    args = parse_args()

    index_path = args.index
    if not index_path.exists():
        index_path = index_path.parent / "chunks_with_local_vectors.jsonl"

    results: list[dict[str, Any]] = []
    with index_path.open(encoding="utf-8") as file:
        for line in file:
            row = json.loads(line)
            score = score_text(args.query, row.get("text", ""))
            if score <= 0:
                continue
            results.append({"score": score, **row})

    results.sort(key=lambda row: row["score"], reverse=True)
    for row in results[: args.top_k]:
        print(
            json.dumps(
                {
                    "score": round(row["score"], 4),
                    "billNo": row.get("billNo"),
                    "billName": row.get("billName"),
                    "documentType": row.get("documentType"),
                    "documentName": row.get("documentName"),
                    "text": compact_text(row.get("text", "")),
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
