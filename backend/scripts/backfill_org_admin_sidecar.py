"""Build the organization/admin sidecar from immutable TAG JSONL seeds.

Default behavior is local-only.  ``--upload`` performs idempotent Supabase
upserts after ``20260911_org_admin_variable_sidecar_v1.sql`` is applied.
No existing assembly/TAG row is deleted or updated.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import urllib.error
import urllib.request
from typing import Any, Iterable

from backend.config import GENERATED_DIR, get_env
from backend.scripts.audit_org_admin_variables import (
    DEFAULT_SEED_DIRS,
    build_candidates,
    load_raw,
)


BACKFILL_VERSION = "org-admin-sidecar-backfill-v2"
CLASSIFIER_VERSION = "org-admin-item-classifier-v1"
DEFAULT_OUTPUT_DIR = GENERATED_DIR / "org_admin_sidecar_v1"


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def stable_key(prefix: str, *parts: Any) -> str:
    payload = "|".join(_compact(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def _number(value: Any) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


_CURRENCY_SCALE = {
    "원": 1.0,
    "천원": 1_000.0,
    "만원": 10_000.0,
    "백만원": 1_000_000.0,
    "억원": 100_000_000.0,
}
_RATE_KEYS = {
    "employer_contribution_rate",
    "wage_growth_rate",
    "basic_expense_ratio",
    "price_growth_rate",
    "management_fee_ratio",
}
_PERSON_COUNT_KEYS = {"headcount", "paid_member_count", "committee_member_count"}
_AMOUNT_KEYS = {
    "total_salary",
    "asset_amount",
    "basic_expense_amount",
    "committee_operating_amount",
    "annual_operating_amount",
}


def normalize_value_unit(
    canonical_key: str | None,
    value: Any,
    raw_unit: str,
    variable_name: str = "",
) -> tuple[float | int | None, str | None, str, list[str]]:
    """Normalize only when scale and denominator are defensible."""
    numeric = _number(value)
    unit = _compact(raw_unit).replace("㎡", "m2")
    name = _compact(variable_name)
    flags: list[str] = []
    if numeric is None:
        return None, None, "missing", ["missing_numeric_value"]
    if not canonical_key:
        return None, None, "not_normalized", ["unmapped_variable"]

    if canonical_key in _RATE_KEYS:
        if "%" in unit:
            return numeric / 100.0, "ratio", "normalized", flags
        if unit in {"비율", "ratio"} and 0 <= numeric <= 1:
            return numeric, "ratio", "normalized", flags
        return None, None, "ambiguous", ["rate_unit_or_scale_ambiguous"]

    if canonical_key in _PERSON_COUNT_KEYS:
        if unit in {"명", "인", "person"}:
            return numeric, "person", "normalized", flags
        return None, None, "ambiguous", ["person_unit_mismatch"]

    if canonical_key == "committee_instance_count":
        if unit in {"개", "개소", "곳", "기관", "instance"}:
            return numeric, "instance", "normalized", flags
        return None, None, "ambiguous", ["committee_instance_unit_mismatch"]

    if canonical_key == "annual_meetings":
        if unit in {"회", "회/년", "meeting/year"}:
            return numeric, "meeting/year", "normalized", flags
        return None, None, "ambiguous", ["meeting_frequency_unit_mismatch"]

    if canonical_key == "annual_case_volume":
        if unit in {"건", "명", "건/년", "case/year"}:
            return numeric, "case/year", "normalized", ["subject_unit_collapsed_to_case"]
        return None, None, "ambiguous", ["case_volume_unit_mismatch"]

    if canonical_key == "cases_per_meeting":
        if unit in {"건", "명", "건/회", "case/meeting"}:
            return numeric, "case/meeting", "normalized", ["subject_unit_collapsed_to_case"]
        return None, None, "ambiguous", ["cases_per_meeting_unit_mismatch"]

    if canonical_key == "required_area":
        if unit in {"m2", "제곱미터"}:
            return numeric, "m2", "normalized", flags
        return None, None, "ambiguous", ["area_unit_mismatch"]

    if canonical_key == "duration":
        if unit in {"년", "year"}:
            return numeric, "year", "normalized", flags
        if unit in {"개월", "월", "month"}:
            return numeric, "month", "normalized", flags
        return None, None, "ambiguous", ["duration_unit_mismatch"]

    if canonical_key == "start_timing":
        if unit in {"년", "year"}:
            return numeric, "year", "normalized", flags
        return None, None, "ambiguous", ["timing_unit_mismatch"]

    currency_prefix = next(
        (prefix for prefix in sorted(_CURRENCY_SCALE, key=len, reverse=True) if unit.startswith(prefix)),
        None,
    )
    if currency_prefix is None:
        return None, None, "ambiguous", ["currency_unit_unrecognized"]
    normalized = numeric * _CURRENCY_SCALE[currency_prefix]

    if canonical_key == "meeting_unit_price":
        return normalized, "KRW/person/meeting", "normalized", flags
    if canonical_key == "asset_unit_price_per_person":
        return normalized, "KRW/person", "normalized", flags
    if canonical_key == "basic_expense_per_person":
        time_unit = "month" if "월" in unit else "year"
        return normalized, f"KRW/person/{time_unit}", "normalized", flags
    if canonical_key == "rent_unit_price":
        if any(token in unit for token in ("m2", "㎡", "평")):
            area = "pyeong" if "평" in unit else "m2"
            time_unit = "month" if "월" in unit else "unknown_time"
            if time_unit == "unknown_time":
                flags.append("rent_time_basis_unknown")
            return normalized, f"KRW/{area}/{time_unit}", "normalized", flags
        return None, None, "ambiguous", ["rent_denominator_missing"]
    if canonical_key in {"salary_by_grade", "salary_per_person"}:
        if "월" in unit or "월보수" in name or "월평균" in name:
            return normalized, "KRW/person/month", "normalized", flags
        if any(token in unit for token in ("/년", "연간", "year")):
            return normalized, "KRW/person/year", "normalized", flags
        return normalized, "KRW/person", "ambiguous", ["salary_time_basis_unknown"]
    if canonical_key in _AMOUNT_KEYS:
        if canonical_key in {"total_salary", "basic_expense_amount", "annual_operating_amount"}:
            return normalized, "KRW/year", "normalized", flags
        return normalized, "KRW", "normalized", flags
    return None, None, "not_normalized", ["normalizer_not_implemented"]


def load_structure_metadata(
    seed_dirs: Iterable[Path],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Index non-oracle bill metadata for temporal and target exclusions."""
    by_structure: dict[str, dict[str, Any]] = {}
    by_bill_id: dict[str, dict[str, Any]] = {}
    for directory in seed_dirs:
        path = directory / "cost_estimate_structures.jsonl"
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                metadata = {
                    key: row.get(key)
                    for key in (
                        "bill_no",
                        "bill_name",
                        "propose_date",
                        "age",
                        "committee",
                    )
                    if row.get(key) not in (None, "")
                }
                structure_id = str(row.get("struct_id") or "")
                bill_id = str(row.get("bill_id") or "")
                if structure_id:
                    by_structure[structure_id] = metadata
                if bill_id:
                    by_bill_id[bill_id] = metadata
    return by_structure, by_bill_id


def build_sidecar_rows(seed_dirs: Iterable[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    seed_dirs = tuple(seed_dirs)
    items, variables = load_raw(seed_dirs)
    selected, candidates = build_candidates(items, variables)
    metadata_by_structure, metadata_by_bill_id = load_structure_metadata(seed_dirs)

    profiles: list[dict[str, Any]] = []
    profile_key_by_item: dict[str, str] = {}
    for item_id, classification in selected.items():
        item = items[item_id]
        structure_id = str(item.get("struct_id") or "")
        bill_id = str(item.get("bill_id") or "")
        metadata = (
            metadata_by_structure.get(structure_id)
            or metadata_by_bill_id.get(bill_id)
            or {}
        )
        profile_key = stable_key("orgitem", item_id)
        profile_key_by_item[item_id] = profile_key
        profiles.append(
            {
                "profile_key": profile_key,
                "source_item_key": item_id,
                "raw_structure_key": structure_id,
                "bill_id": bill_id or None,
                "item_name": str(item.get("item_name") or ""),
                "item_category": str(item.get("item_category") or "") or None,
                "route": classification.route,
                "component": classification.component,
                "classification_confidence": classification.confidence,
                "classification_reason": classification.reason,
                "classifier_version": CLASSIFIER_VERSION,
                "review_status": "candidate",
                "raw_attributes": metadata,
            }
        )

    evidence: list[dict[str, Any]] = []
    for candidate in candidates:
        fingerprint = stable_key(
            "rawvar",
            candidate.raw_item_id,
            candidate.raw_variable_type,
            candidate.raw_variable_name,
            candidate.raw_value,
            candidate.raw_unit,
            candidate.source_text,
        )
        normalized_value, normalized_unit, unit_status, flags = normalize_value_unit(
            candidate.canonical_key,
            candidate.raw_value,
            candidate.raw_unit,
            candidate.raw_variable_name,
        )
        if len(candidate.basis_year_candidates) != 1:
            flags.append(
                "basis_year_missing"
                if not candidate.basis_year_candidates
                else "multiple_basis_years"
            )
        if candidate.mapping_confidence != "high":
            flags.append("mapping_not_high_confidence")
        evidence.append(
            {
                "evidence_key": stable_key("orgev", fingerprint),
                "profile_key": profile_key_by_item[candidate.raw_item_id],
                "raw_variable_fingerprint": fingerprint,
                "canonical_key": candidate.canonical_key,
                "raw_variable_type": candidate.raw_variable_type or None,
                "raw_variable_name": candidate.raw_variable_name,
                "raw_value": _number(candidate.raw_value),
                "raw_unit": candidate.raw_unit or None,
                "normalized_value": normalized_value,
                "normalized_unit": normalized_unit,
                "source_class": candidate.source_class,
                "transfer_policy": candidate.transfer_policy,
                "source_text": candidate.source_text,
                "basis_year_candidates": list(candidate.basis_year_candidates),
                "basis_year": (
                    candidate.basis_year_candidates[0]
                    if len(candidate.basis_year_candidates) == 1
                    else None
                ),
                "mapping_confidence": candidate.mapping_confidence,
                "normalization_status": candidate.normalization_status,
                "unit_status": unit_status,
                "review_status": "candidate",
                "quality_flags": sorted(set(flags)),
                "transform_version": BACKFILL_VERSION,
            }
        )
    return profiles, evidence


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _upsert(base_url: str, key: str, table: str, rows: list[dict[str, Any]]) -> None:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    for start in range(0, len(rows), 250):
        body = json.dumps(rows[start:start + 250], ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/rest/v1/{table}",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60):
                pass
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"{table} HTTP {exc.code}: {message}") from exc


def _upload(profiles: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> None:
    base_url = get_env("SUPABASE_URL").rstrip("/")
    key = get_env("SUPABASE_SERVICE_ROLE_KEY")
    if not base_url or not key:
        raise SystemExit("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY is required")
    _upsert(base_url, key, "org_admin_item_profiles", profiles)
    _upsert(base_url, key, "org_admin_variable_evidence", evidence)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-dir", action="append", type=Path, dest="seed_dirs")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upsert sidecar rows after the migration has been applied.",
    )
    args = parser.parse_args()
    seed_dirs = tuple(args.seed_dirs or DEFAULT_SEED_DIRS)
    profiles, evidence = build_sidecar_rows(seed_dirs)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    profile_path = args.output_dir / "item_profiles.jsonl"
    evidence_path = args.output_dir / "variable_evidence.jsonl"
    summary_path = args.output_dir / "summary.json"
    _write_jsonl(profile_path, profiles)
    _write_jsonl(evidence_path, evidence)
    summary = {
        "backfill_version": BACKFILL_VERSION,
        "profiles": len(profiles),
        "evidence": len(evidence),
        "canonical_key": dict(Counter(row.get("canonical_key") or "unmapped" for row in evidence)),
        "normalization_status": dict(Counter(row["normalization_status"] for row in evidence)),
        "unit_status": dict(Counter(row["unit_status"] for row in evidence)),
        "transfer_policy": dict(Counter(row["transfer_policy"] for row in evidence)),
        "review_status": "all_candidate",
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.upload:
        _upload(profiles, evidence)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
