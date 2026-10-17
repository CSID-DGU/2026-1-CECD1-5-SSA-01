"""Select an auditable precedent and optionally execute its resolver request."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.general_cost_precedent_selector import (
    DEFAULT_SIDECAR_DIR,
    GeneralCostEvidenceStore,
    select_precedent,
    target_from_dict,
)
from backend.general_cost_resolver import request_from_dict, resolve_general_cost


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument("--sidecar-dir", type=Path, default=DEFAULT_SIDECAR_DIR)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--resolver-out", type=Path)
    args = parser.parse_args()

    payload = json.loads(args.target.read_text(encoding="utf-8"))
    target = target_from_dict(payload)
    result = select_precedent(
        target,
        store=GeneralCostEvidenceStore(args.sidecar_dir),
    )
    rendered = result.to_dict()
    if args.out:
        _write(args.out, rendered)
        print(f"selection={args.out}")
    else:
        print(json.dumps(rendered, ensure_ascii=False, indent=2))

    if args.resolver_out:
        if result.resolver_request is None:
            raise SystemExit("selection did not produce an executable resolver request")
        resolution = resolve_general_cost(
            request_from_dict(result.resolver_request)
        ).to_dict()
        _write(args.resolver_out, resolution)
        print(f"resolution={args.resolver_out}")


if __name__ == "__main__":
    main()
