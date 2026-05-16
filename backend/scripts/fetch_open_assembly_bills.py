from __future__ import annotations

import argparse
import getpass
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import GENERATED_DIR, get_env


API_URL = "https://open.assembly.go.kr/portal/openapi/nzmimeepazxkubdpn"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch member-proposed bill metadata from Open Assembly API."
    )
    parser.add_argument("--age", default="21", help="National Assembly term, e.g. 21.")
    parser.add_argument("--page", type=int, default=1, help="Page index.")
    parser.add_argument("--size", type=int, default=10, help="Page size.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON output path. Defaults to stdout only.",
    )
    return parser.parse_args()


def get_api_key() -> str:
    key = get_env("OPEN_ASSEMBLY_API_KEY")
    if key:
        return key

    entered = getpass.getpass("OPEN_ASSEMBLY_API_KEY: ").strip()
    if not entered:
        raise SystemExit("OPEN_ASSEMBLY_API_KEY is required.")
    return entered


def build_url(api_key: str, args: argparse.Namespace) -> str:
    query = {
        "KEY": api_key,
        "Type": "json",
        "pIndex": str(args.page),
        "pSize": str(args.size),
        "AGE": args.age,
    }
    return f"{API_URL}?{urllib.parse.urlencode(query)}"


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "cost-estimation-system/0.1",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def summarize(payload: dict[str, Any]) -> dict[str, Any]:
    root = payload.get("nzmimeepazxkubdpn")
    if not isinstance(root, list):
        return payload

    rows: list[dict[str, Any]] = []
    total_count: int | None = None
    result: dict[str, Any] | None = None

    for item in root:
        if "head" in item:
            for head_item in item["head"]:
                if "list_total_count" in head_item:
                    total_count = head_item["list_total_count"]
                if "RESULT" in head_item:
                    result = head_item["RESULT"]
        if "row" in item:
            rows = item["row"]

    sample = [
        {
            "BILL_ID": row.get("BILL_ID"),
            "BILL_NO": row.get("BILL_NO"),
            "BILL_NAME": row.get("BILL_NAME"),
            "PROPOSER": row.get("PROPOSER"),
            "PROPOSE_DT": row.get("PROPOSE_DT"),
            "COMMITTEE": row.get("COMMITTEE"),
            "PROC_RESULT": row.get("PROC_RESULT"),
            "DETAIL_LINK": row.get("DETAIL_LINK"),
        }
        for row in rows[: min(len(rows), 5)]
    ]

    return {
        "result": result,
        "totalCount": total_count,
        "fetchedRows": len(rows),
        "sample": sample,
    }


def main() -> None:
    args = parse_args()
    api_key = get_api_key()
    payload = fetch_json(build_url(api_key, args))
    summary = summarize(payload)

    if args.output:
        output_path = args.output
        if not output_path.is_absolute():
            output_path = GENERATED_DIR / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        summary["savedTo"] = str(output_path)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
