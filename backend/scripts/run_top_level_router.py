"""Run the deterministic top-level disposition router from JSON."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.estimator_v2.org_admin_resolver import DEFAULT_SIDECAR_DIR, load_sidecar
from backend.estimator_v2.top_level_router import route_bill, routing_request_from_dict


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    parser.add_argument("--sidecar-dir", type=Path, default=DEFAULT_SIDECAR_DIR)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    payload = json.loads(args.request.read_text(encoding="utf-8"))
    profiles, evidence = load_sidecar(args.sidecar_dir)
    result = route_bill(
        routing_request_from_dict(payload),
        organization_profiles=profiles,
        organization_evidence=evidence,
    ).to_dict()
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
        print(f"result={args.out}")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
