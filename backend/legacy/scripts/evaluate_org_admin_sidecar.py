"""Offline readiness and historical-replay benchmark for the sidecar.

This does not measure unseen-bill end-to-end accuracy. It measures whether a
historical official item contains one coherent normalized operand set and,
for simple multiplicative formulas, whether it reproduces the official
constant annual amount in the immutable TAG seed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
import re
import statistics
from typing import Any, Iterable

from backend.config import GENERATED_DIR
from backend.legacy.scripts.audit_org_admin_variables import DEFAULT_SEED_DIRS


DEFAULT_SIDECAR_DIR = GENERATED_DIR / "org_admin_sidecar_v1"
DEFAULT_OUTPUT = DEFAULT_SIDECAR_DIR / "benchmark.json"


@dataclass(frozen=True)
class FormulaSpec:
    formula_key: str
    route: str
    components: frozenset[str]
    required_keys: tuple[str, ...]
    aggregate_keys: tuple[str, ...] = ()
    forbidden_keys: tuple[str, ...] = ()
    allow_addition: bool = False


FORMULA_SPECS = (
    FormulaSpec(
        "COMMITTEE_MEETING_V1",
        "committee",
        frozenset({"committee_meeting", "committee_operation"}),
        ("paid_member_count", "annual_meetings", "meeting_unit_price"),
        forbidden_keys=("committee_instance_count",),
    ),
    FormulaSpec(
        "COMMITTEE_MULTI_INSTANCE_V1",
        "committee",
        frozenset({"committee_meeting", "committee_operation"}),
        (
            "committee_instance_count",
            "paid_member_count",
            "annual_meetings",
            "meeting_unit_price",
        ),
        aggregate_keys=("committee_instance_count",),
        allow_addition=True,
    ),
    FormulaSpec(
        "ORG_PERSONNEL_AVERAGE_V1",
        "organization",
        frozenset({"personnel"}),
        ("headcount", "salary_per_person"),
    ),
    FormulaSpec(
        "ORG_EMPLOYER_CONTRIBUTION_V1",
        "organization",
        frozenset({"employer_contribution"}),
        ("total_salary", "employer_contribution_rate"),
    ),
    FormulaSpec(
        "ORG_BASIC_EXPENSE_RATIO_V1",
        "organization",
        frozenset({"basic_expense"}),
        ("total_salary", "basic_expense_ratio"),
    ),
    FormulaSpec(
        "ORG_BASIC_EXPENSE_PER_PERSON_V1",
        "organization",
        frozenset({"basic_expense"}),
        ("headcount", "basic_expense_per_person"),
    ),
    FormulaSpec(
        "ORG_ASSET_PER_PERSON_V1",
        "organization",
        frozenset({"asset"}),
        ("headcount", "asset_unit_price_per_person"),
    ),
    FormulaSpec(
        "ORG_SPACE_RENT_V1",
        "organization",
        frozenset({"space"}),
        ("required_area", "rent_unit_price", "rent_duration_months"),
    ),
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_amounts(seed_dirs: Iterable[Path]) -> dict[str, list[dict[str, Any]]]:
    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for seed_dir in seed_dirs:
        for row in _read_jsonl(seed_dir / "cost_estimate_amounts.jsonl"):
            item_id = str(row.get("item_id") or "")
            if not item_id or row.get("is_total"):
                continue
            key = (
                item_id,
                row.get("year_label"),
                row.get("year_offset"),
                row.get("amount_thousand"),
                row.get("formula_text"),
            )
            deduped[key] = row
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in deduped.values():
        grouped[str(row["item_id"])].append(row)
    return grouped


def unique_operands(
    rows: Iterable[dict[str, Any]],
    required_keys: Iterable[str],
    aggregate_keys: Iterable[str] = (),
) -> tuple[dict[str, float], dict[str, str]] | None:
    """Require one value and one normalized unit per operand inside one item."""
    values: dict[str, float] = {}
    units: dict[str, str] = {}
    aggregate = set(aggregate_keys)
    for key in required_keys:
        matching = [
            row
            for row in rows
            if row.get("canonical_key") == key
            and row.get("normalized_value") is not None
            and row.get("unit_status") == "normalized"
        ]
        distinct_values = {float(row["normalized_value"]) for row in matching}
        distinct_units = {str(row.get("normalized_unit") or "") for row in matching}
        if not distinct_values or len(distinct_units) != 1 or "" in distinct_units:
            return None
        if key in aggregate:
            values[key] = sum(float(row["normalized_value"]) for row in matching)
        elif len(distinct_values) == 1:
            values[key] = next(iter(distinct_values))
        else:
            return None
        units[key] = next(iter(distinct_units))
    return values, units


def official_constant_annual_amount(rows: Iterable[dict[str, Any]]) -> float | None:
    """Return thousand KRW only for one unambiguous constant annual series."""
    by_year: dict[int, set[int]] = defaultdict(set)
    for row in rows:
        try:
            offset = int(row.get("year_offset"))
            amount = int(row.get("amount_thousand"))
        except (TypeError, ValueError):
            continue
        if amount > 0:
            by_year[offset].add(amount)
    if not by_year or any(len(values) != 1 for values in by_year.values()):
        return None
    annual_values = {next(iter(values)) for values in by_year.values()}
    if len(annual_values) != 1:
        return None
    return float(next(iter(annual_values)))


def official_formula_texts(rows: Iterable[dict[str, Any]]) -> tuple[str, ...]:
    """Return distinct formula labels attached to positive annual amounts."""
    return tuple(
        sorted(
            {
                str(row.get("formula_text") or "").strip()
                for row in rows
                if row.get("year_offset") is not None
                and row.get("amount_thousand") not in (None, 0)
                and str(row.get("formula_text") or "").strip()
            }
        )
    )


def is_simple_multiplicative_formula(
    formula_texts: Iterable[str],
    factor_count: int,
    *,
    allow_addition: bool = False,
) -> bool:
    """Heuristic gate separating an N-factor product from composite formulas.

    Historical labels sometimes repeat the symbolic expression and its numeric
    substitution, so a parenthesized N-factor expression is also accepted.
    Additive formulas and formulas with an extra multiplier are rejected.
    """
    expected_operators = factor_count - 1
    for raw_text in formula_texts:
        text = str(raw_text or "")
        if not allow_addition and ("+" in text or "＋" in text):
            continue
        operator_count = text.count("×") + text.count("*")
        if operator_count == expected_operators:
            return True
        parenthetical_counts = [
            part.count("×") + part.count("*")
            for part in re.findall(r"\(([^()]*)\)", text)
        ]
        if (
            operator_count == expected_operators * 2
            and expected_operators in parenthetical_counts
        ):
            return True
        if factor_count == 2 and operator_count == 0 and "곱" in text:
            return True
    return False


def is_suspected_scale_anomaly(predicted: float, official: float) -> bool:
    """Flag near-exact powers-of-ten disagreement in the stored amount scale."""
    if predicted <= 0 or official <= 0:
        return False
    ratio = max(predicted / official, official / predicted)
    return any(abs(ratio - scale) / scale <= 0.02 for scale in (10, 100, 1_000))


def predicted_thousand(values: dict[str, float]) -> float:
    product = 1.0
    for value in values.values():
        product *= value
    return product / 1_000.0


def relative_error_pct(predicted: float, official: float) -> float:
    if official == 0:
        return 0.0 if predicted == 0 else float("inf")
    return abs(predicted - official) / official * 100.0


def evaluate(
    profiles: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    amounts: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    evidence_by_profile: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in evidence:
        evidence_by_profile[str(row["profile_key"])].append(row)

    formula_results: dict[str, dict[str, Any]] = {}
    replay_rows: list[dict[str, Any]] = []
    for spec in FORMULA_SPECS:
        eligible = [
            profile
            for profile in profiles
            if profile.get("route") == spec.route
            and profile.get("component") in spec.components
        ]
        ready: list[tuple[dict[str, Any], dict[str, float], dict[str, str]]] = []
        for profile in eligible:
            profile_evidence = evidence_by_profile.get(str(profile["profile_key"]), [])
            if any(
                row.get("canonical_key") in spec.forbidden_keys
                and row.get("normalized_value") is not None
                and row.get("unit_status") == "normalized"
                for row in profile_evidence
            ):
                continue
            operands = unique_operands(
                profile_evidence,
                spec.required_keys,
                spec.aggregate_keys,
            )
            if operands:
                ready.append((profile, operands[0], operands[1]))

        errors: list[float] = []
        exact_rounding = 0
        within_5 = 0
        within_10 = 0
        within_20 = 0
        simple_errors: list[float] = []
        simple_exact_rounding = 0
        simple_within_5 = 0
        scale_anomalies = 0
        non_anomalous_simple_errors: list[float] = []
        for profile, values, units in ready:
            amount_rows = amounts.get(str(profile["source_item_key"]), [])
            official = official_constant_annual_amount(amount_rows)
            if official is None:
                continue
            formula_texts = official_formula_texts(amount_rows)
            formula_shape_compatible = is_simple_multiplicative_formula(
                formula_texts,
                len(spec.required_keys),
                allow_addition=spec.allow_addition,
            )
            predicted = predicted_thousand(values)
            error = relative_error_pct(predicted, official)
            errors.append(error)
            exact_rounding += abs(predicted - official) <= max(1.0, official * 0.001)
            within_5 += error <= 5.0
            within_10 += error <= 10.0
            within_20 += error <= 20.0
            scale_anomaly = (
                formula_shape_compatible
                and is_suspected_scale_anomaly(predicted, official)
            )
            if formula_shape_compatible:
                simple_errors.append(error)
                simple_exact_rounding += abs(predicted - official) <= max(
                    1.0, official * 0.001
                )
                simple_within_5 += error <= 5.0
                scale_anomalies += scale_anomaly
                if not scale_anomaly:
                    non_anomalous_simple_errors.append(error)
            replay_rows.append(
                {
                    "formula_key": spec.formula_key,
                    "source_item_key": profile["source_item_key"],
                    "item_name": profile["item_name"],
                    "operands": values,
                    "units": units,
                    "predicted_thousand": round(predicted, 3),
                    "official_thousand": official,
                    "absolute_error_pct": round(error, 4),
                    "formula_texts": formula_texts,
                    "formula_shape_compatible": formula_shape_compatible,
                    "suspected_reference_scale_anomaly": scale_anomaly,
                }
            )

        formula_results[spec.formula_key] = {
            "eligible_profiles": len(eligible),
            "same_item_operand_ready": len(ready),
            "same_item_readiness_pct": round(len(ready) / len(eligible) * 100, 2)
            if eligible
            else 0.0,
            "constant_annual_replay_cases": len(errors),
            "exact_with_rounding": exact_rounding,
            "within_5_pct": within_5,
            "within_10_pct": within_10,
            "within_20_pct": within_20,
            "mape_pct": round(statistics.mean(errors), 3) if errors else None,
            "simple_formula_replay_cases": len(simple_errors),
            "simple_formula_exact_with_rounding": simple_exact_rounding,
            "simple_formula_within_5_pct": simple_within_5,
            "simple_formula_mape_pct": round(statistics.mean(simple_errors), 3)
            if simple_errors
            else None,
            "composite_or_unverified_formula_cases": len(errors) - len(simple_errors),
            "suspected_reference_scale_anomalies": scale_anomalies,
            "non_anomalous_simple_formula_cases": len(non_anomalous_simple_errors),
            "non_anomalous_simple_formula_mape_pct": round(
                statistics.mean(non_anomalous_simple_errors), 3
            )
            if non_anomalous_simple_errors
            else None,
        }

    mapped_evidence = [row for row in evidence if row.get("canonical_key")]
    unit_normalized = [row for row in mapped_evidence if row.get("unit_status") == "normalized"]
    reusable_candidates = [
        row
        for row in unit_normalized
        if row.get("transfer_policy") in {
            "versioned_official",
            "comparable_only",
            "scope_check_required",
        }
    ]
    return {
        "benchmark_scope": "local_sidecar_data_readiness_and_historical_formula_replay",
        "limitations": [
            "This is not unseen-bill end-to-end accuracy.",
            "Replay uses one coherent historical item and excludes ambiguous operands.",
            "A replay match does not make a precedent value transferable to another bill.",
        ],
        "data_readiness": {
            "profiles": len(profiles),
            "evidence_rows": len(evidence),
            "canonical_mapped_rows": len(mapped_evidence),
            "unit_normalized_rows": len(unit_normalized),
            "unit_normalized_pct_of_all_evidence": round(
                len(unit_normalized) / len(evidence) * 100, 2
            )
            if evidence
            else 0.0,
            "potentially_reusable_candidates_before_context_gates": len(reusable_candidates),
            "review_status": dict(Counter(str(row.get("review_status")) for row in evidence)),
        },
        "formula_results": formula_results,
        "aggregate_replay": {
            "cases": len(replay_rows),
            "exact_with_rounding": sum(
                row["absolute_error_pct"] <= 0.1 for row in replay_rows
            ),
            "within_5_pct": sum(row["absolute_error_pct"] <= 5 for row in replay_rows),
            "within_10_pct": sum(row["absolute_error_pct"] <= 10 for row in replay_rows),
            "within_20_pct": sum(row["absolute_error_pct"] <= 20 for row in replay_rows),
            "mape_pct": round(
                statistics.mean(row["absolute_error_pct"] for row in replay_rows), 3
            )
            if replay_rows
            else None,
        },
        "replay_rows": sorted(
            replay_rows,
            key=lambda row: (
                row["formula_key"],
                row["absolute_error_pct"],
                row["source_item_key"],
            ),
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sidecar-dir", type=Path, default=DEFAULT_SIDECAR_DIR)
    parser.add_argument("--seed-dir", action="append", type=Path, dest="seed_dirs")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    profiles = _read_jsonl(args.sidecar_dir / "item_profiles.jsonl")
    evidence = _read_jsonl(args.sidecar_dir / "variable_evidence.jsonl")
    if not profiles or not evidence:
        raise SystemExit("sidecar backfill is missing; run backfill_org_admin_sidecar first")
    payload = evaluate(
        profiles,
        evidence,
        load_amounts(tuple(args.seed_dirs or DEFAULT_SEED_DIRS)),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    visible = {
        key: payload[key]
        for key in ("data_readiness", "formula_results", "aggregate_replay")
    }
    print(json.dumps(visible, ensure_ascii=False, indent=2))
    print(f"report={args.out}")


if __name__ == "__main__":
    main()
