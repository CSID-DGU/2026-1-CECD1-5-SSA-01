"""Run the deterministic general cost resolver from a JSON request."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.erce_web.general_cost_resolver import request_from_dict, resolve_general_cost


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.request.read_text(encoding="utf-8"))
    result = resolve_general_cost(request_from_dict(payload)).to_dict()
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
        print(f"result={args.out}")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
