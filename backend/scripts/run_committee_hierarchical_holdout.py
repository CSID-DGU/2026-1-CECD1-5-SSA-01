"""Run and freeze the isolated hierarchical committee evidence engine."""
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

from backend.committee_hierarchical_evidence_engine import ENGINE_VERSION, evaluate


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(source_manifest: Path) -> dict[str, Any]:
    cases = json.loads(source_manifest.read_text(encoding="utf-8"))
    engine_path = ROOT / "backend/committee_hierarchical_evidence_engine.py"
    results = [evaluate(case).to_dict() for case in cases]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine_version": ENGINE_VERSION,
        "source_manifest": str(source_manifest),
        "source_manifest_sha256": _sha256(source_manifest),
        "engine_sha256": _sha256(engine_path),
        "case_count": len(cases),
        "results": results,
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
        f"hierarchical predictions={payload['case_count']} output={args.output} "
        f"engine_sha256={payload['engine_sha256']}"
    )
    for row in payload["results"]:
        print(
            row["bill_no"],
            row["route"],
            row["decision"],
            f"precedent={row['package']['selected_bill_no'] or '-'}",
            f"targets={len(row['components'])}",
        )


if __name__ == "__main__":
    main()
