"""Export the local HITL queue for review before a later DB upload.

This command never connects to Supabase and never marks records as uploaded.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.erce_web.hitl_feedback import FEEDBACK_PATH, FEEDBACK_SCHEMA_VERSION


def _load(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        record_id = str(row.get("record_id") or "")
        if not record_id or record_id in seen:
            continue
        seen.add(record_id)
        if row.get("review_status") == "pending":
            rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=FEEDBACK_PATH)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("/private/tmp/hitl_feedback_pending_review.jsonl"),
    )
    args = parser.parse_args()
    rows = _load(args.input)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "schema_version": FEEDBACK_SCHEMA_VERSION,
                "pending_records": len(rows),
                "output": str(args.out),
                "uploaded": False,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
