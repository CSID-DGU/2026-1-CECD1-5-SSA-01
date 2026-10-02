"""Evidence-priority resolver for ERCE formula variables.

An assumption may fill an empty formula slot, but it can never overwrite a
value stated in the target law, a target-specific actual, or an official rate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ResolvedVariable:
    key: str
    value: Any
    unit: str
    source_class: str
    source_ref: str
    is_assumption: bool


SOURCE_PRIORITY: tuple[str, ...] = (
    "target_explicit",
    "target_current_actual",
    "official_standard",
    "calculated_estimate",
    "precedent_assumption",
    "ai_assumption",
)


def selected_precedent_inputs(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate AI-selected variable evidence; this function does no searching."""
    selected = dict(payload.get("selected_variable_inputs") or {})
    for key, row in selected.items():
        if not isinstance(row, Mapping):
            raise ValueError(f"selected variable needs evidence metadata: {key}")
        source_bill = str(row.get("source_bill_no") or "")
        available = str(row.get("available_at") or "")
        cutoff = str(payload.get("cutoff_date") or "")
        from datetime import date
        try:
            future = date.fromisoformat(available) > date.fromisoformat(cutoff)
        except ValueError as exc:
            raise ValueError(f"selected variable needs valid dates: {key}") from exc
        if not source_bill or not str(row.get("source_ref") or "").strip():
            raise ValueError(f"selected variable needs source: {key}")
        same_target = source_bill == str(payload.get("bill_no") or "")
        reviewed_development = (payload.get("evidence_mode") == "development_review"
                                and row.get("review_status") == "reviewed")
        if future or (same_target and not reviewed_development):
            raise ValueError(f"selected variable is future/self evidence: {key}")
    return selected


def _candidate(key: str, value: Any, source_class: str) -> ResolvedVariable | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        raw = value.get("value")
        if raw is None:
            return None
        return ResolvedVariable(
            key=key,
            value=raw,
            unit=str(value.get("unit") or ""),
            source_class=source_class,
            source_ref=str(value.get("source_ref") or ""),
            is_assumption=(source_class in {"precedent_assumption", "ai_assumption"}
                           or (source_class == "calculated_estimate" and bool(value.get("is_assumption", True)))),
        )
    return ResolvedVariable(
        key=key,
        value=value,
        unit="",
        source_class=source_class,
        source_ref="",
        is_assumption=source_class in {"precedent_assumption", "ai_assumption", "calculated_estimate"},
    )


def resolve_formula_variables(
    required_keys: tuple[str, ...],
    *,
    target_explicit: Mapping[str, Any] | None = None,
    target_current_actual: Mapping[str, Any] | None = None,
    official_standard: Mapping[str, Any] | None = None,
    calculated_estimate: Mapping[str, Any] | None = None,
    precedent_assumption: Mapping[str, Any] | None = None,
    ai_assumption: Mapping[str, Any] | None = None,
    allow_ai_assumption: bool = False,
) -> tuple[dict[str, ResolvedVariable], tuple[str, ...]]:
    layers: dict[str, Mapping[str, Any]] = {
        "target_explicit": target_explicit or {},
        "target_current_actual": target_current_actual or {},
        "official_standard": official_standard or {},
        "calculated_estimate": calculated_estimate or {},
        "precedent_assumption": precedent_assumption or {},
        "ai_assumption": ai_assumption or {},
    }
    resolved: dict[str, ResolvedVariable] = {}
    for key in required_keys:
        for source_class in SOURCE_PRIORITY:
            if source_class == "ai_assumption" and not allow_ai_assumption:
                continue
            candidate = _candidate(key, layers[source_class].get(key), source_class)
            if candidate is not None:
                resolved[key] = candidate
                break
    missing = tuple(key for key in required_keys if key not in resolved)
    return resolved, missing


__all__ = [
    "ResolvedVariable",
    "SOURCE_PRIORITY",
    "resolve_formula_variables",
]
