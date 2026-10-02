"""Build downloadable ERCE development PDF bundles by cost category.

Only bills in development_manifest.jsonl are included. The validation holdout
is intentionally excluded even when its symlink appears in by_category.
"""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / "generated/assembly_22_pdfs"
OUTPUT = Path(__file__).resolve().parents[2] / "generated/erce_category_downloads"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    source = args.source
    output = args.output
    output.mkdir(parents=True, exist_ok=True)

    development = {
        row["bill_no"]: row
        for line in (source / "development_manifest.jsonl").open(encoding="utf-8")
        if (row := json.loads(line))["status"] == "complete"
    }
    for category in sorted((source / "by_category").iterdir()):
        if not category.is_dir():
            continue
        bills = sorted(
            bill.name for bill in category.iterdir()
            if bill.name in development and bill.name.isdecimal()
        )
        archive = output / f"ERCE_22대_개발용_{category.name}.zip"
        included = []
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=1, allowZip64=True) as bundle:
            for bill_no in bills:
                directory = source / "by_bill" / bill_no
                required = [directory / "bill_text.pdf", directory / "cost_estimate.pdf"]
                if not all(path.is_file() for path in required):
                    continue
                for filename in ("bill_text.pdf", "cost_estimate.pdf", "metadata.json"):
                    path = directory / filename
                    if path.is_file():
                        bundle.write(path, f"{category.name}/{bill_no}/{filename}")
                included.append(development[bill_no])
            bundle.writestr(
                f"{category.name}/manifest.jsonl",
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in included),
            )
        print(f"{archive.name}: {len(included)} bills, {archive.stat().st_size:,} bytes", flush=True)


if __name__ == "__main__":
    main()
