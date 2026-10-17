"""Run a source-only committee precedent holdout without reading gold files."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.committee_precedent_resolver import resolve


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(source_manifest: Path) -> dict[str, Any]:
    cases = json.loads(source_manifest.read_text(encoding="utf-8"))
    resolver_path = ROOT / "backend" / "committee_precedent_resolver.py"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_manifest": str(source_manifest),
        "source_manifest_sha256": _sha256(source_manifest),
        "resolver_sha256": _sha256(resolver_path),
        "case_count": len(cases),
        "results": [resolve(case).to_dict() for case in cases],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"frozen holdout predictions={payload['case_count']} "
        f"output={args.output} resolver_sha256={payload['resolver_sha256']}"
    )
    for row in payload["results"]:
        print(
            row["bill_no"],
            row["decision"],
            row["selected_bill_no"] or "-",
            f"score={row['relation_score']:.4f}",
            f"missing={','.join(row['missing_components']) or '-'}",
            f"conflicts={','.join(row['conflicts']) or '-'}",
        )


if __name__ == "__main__":
    main()
