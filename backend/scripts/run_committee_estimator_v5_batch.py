"""Run committee estimator v5 over a local directory of source PDFs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.committee_estimator_v5 import estimate_committee_from_pdf_v5


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    results: dict[str, dict] = {}
    for source in sorted(args.source_dir.glob("*_*.pdf")):
        bill_no = source.name.split("_", 1)[0]
        print(f"running {bill_no}: {source.name}", flush=True)
        result = estimate_committee_from_pdf_v5(
            source.read_bytes(),
            filename=source.name,
            refresh=args.refresh,
        )
        results[bill_no] = result.to_dict()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
