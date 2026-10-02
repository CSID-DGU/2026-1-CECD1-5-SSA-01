"""Import MPM's official monthly base-pay tables into the local ERCE unit DB."""
from __future__ import annotations

import argparse
from pathlib import Path
from urllib.request import urlopen

from backend.erce.official_salary_store import (
    SOURCE_URL_TEMPLATE, parse_official_salary_html, save_official_salary_rates,
)
from backend.erce.variable_evidence_store import DEFAULT_VARIABLE_DB


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--html-file", type=Path, help="Already downloaded official page")
    parser.add_argument("--db", type=Path, default=DEFAULT_VARIABLE_DB)
    args = parser.parse_args()
    if args.html_file:
        html = args.html_file.read_text(encoding="utf-8")
    else:
        with urlopen(SOURCE_URL_TEMPLATE.format(year=args.year), timeout=30) as response:
            html = response.read().decode("utf-8")
    rows = parse_official_salary_html(html, args.year)
    count = save_official_salary_rates(rows, args.db)
    print(f"Imported {count} official monthly base-pay rates for {args.year} into {args.db}")


if __name__ == "__main__":
    main()
