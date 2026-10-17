"""Run the organization/admin target-excluded holdout protocol.

The default command is source-plan plus exclusion validation.  It does not
open answer PDFs.  ``--score-official`` is an explicit evaluation phase and
reads only the answer paths recorded in the frozen catalog after prediction
state has been produced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import fitz

from backend.erce_web.config import GENERATED_DIR
from backend.erce_web.estimator_v2.org_admin_resolver import (
    OrgAdminPlanRequest,
    load_sidecar,
    resolve_org_admin_plan,
)
from backend.legacy.scripts.evaluate_assembly_batch import _parse_first_cost_table


ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / "backend/legacy/fixtures/org_admin_target_excluded_cases.json"
DEFAULT_SIDECAR = GENERATED_DIR / "org_admin_sidecar_v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _route_for_component(component: str) -> str:
    return "committee" if component in {"committee_meeting", "committee_operation"} else "organization"


def _source_plan(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        source = ROOT / str(case["source_pdf"])
        components = tuple(case["source_only_plan"]["components"])
        route = "committee" if all(_route_for_component(x) == "committee" for x in components) else "organization"
        result = resolve_org_admin_plan(
            OrgAdminPlanRequest(
                route=route,
                components=components,
                target_bill_no=str(case["bill_no"]),
                cutoff_date=str(case.get("propose_date") or ""),
            )
        )
        rows.append(
            {
                "bill_no": str(case["bill_no"]),
                "source_exists": source.exists(),
                "source_sha256": _sha256(source) if source.exists() else "",
                "resolver_status": result.status,
                "year_totals_thousand": result.year_totals_thousand,
                "rows": [
                    {
                        "component": row.component,
                        "status": row.status,
                        "formula_key": row.formula_key,
                        "missing_variables": row.missing_variables,
                        "reason_codes": row.reason_codes,
                    }
                    for row in result.rows
                ],
            }
        )
    return rows


def _target_exclusion(cases: list[dict[str, Any]], sidecar_dir: Path) -> list[dict[str, Any]]:
    profiles, evidence = load_sidecar(sidecar_dir)
    rows: list[dict[str, Any]] = []
    for case in cases:
        bill_no = str(case["bill_no"])
        target_profiles = [
            profile
            for profile in profiles
            if str((profile.get("raw_attributes") or {}).get("bill_no") or "") == bill_no
        ]
        checks: list[dict[str, Any]] = []
        for profile in target_profiles:
            component = str(profile.get("component") or "")
            route = _route_for_component(component)
            result = resolve_org_admin_plan(
                OrgAdminPlanRequest(
                    route=route,
                    components=(component,),
                    target_bill_no=bill_no,
                    target_bill_id=str(profile.get("bill_id") or ""),
                    cutoff_date=str(case.get("propose_date") or ""),
                    selected_profile_keys={component: str(profile.get("profile_key") or "")},
                    context_gates_passed=True,
                    diagnostic_allow_candidate_evidence=True,
                ),
                profiles=profiles,
                evidence=evidence,
            )
            codes = result.rows[0].reason_codes
            checks.append(
                {
                    "profile_key": str(profile.get("profile_key") or ""),
                    "component": component,
                    "blocked": "TARGET_PROFILE_EXCLUDED" in codes,
                    "reason_codes": codes,
                }
            )
        rows.append(
            {
                "bill_no": bill_no,
                "target_profiles": len(target_profiles),
                "blocked_profiles": sum(1 for check in checks if check["blocked"]),
                "all_blocked": bool(target_profiles) and all(check["blocked"] for check in checks),
                "checks": checks,
            }
        )
    return rows


def _official_score(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        answer = ROOT / str(case["answer_pdf"])
        if not answer.exists():
            rows.append({"bill_no": str(case["bill_no"]), "answer_exists": False})
            continue
        text = "\n".join(page.get_text() for page in fitz.open(answer))
        parsed = _parse_first_cost_table(text)
        rows.append(
            {
                "bill_no": str(case["bill_no"]),
                "answer_exists": True,
                "official_years_million": parsed.get("years"),
                "official_total_million": parsed.get("total"),
                "answer_sha256": _sha256(answer),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--sidecar-dir", type=Path, default=DEFAULT_SIDECAR)
    parser.add_argument("--score-official", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    cases = list(catalog.get("cases") or [])
    payload: dict[str, Any] = {
        "protocol": catalog.get("schema_version"),
        "answer_access": "score_only" if args.score_official else "not_opened",
        "source_plan": _source_plan(cases),
        "target_exclusion": _target_exclusion(cases, args.sidecar_dir),
    }
    if args.score_official:
        payload["official_score"] = _official_score(cases)

    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
        print(f"result={args.out}")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
