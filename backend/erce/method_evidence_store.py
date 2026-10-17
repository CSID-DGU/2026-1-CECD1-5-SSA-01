"""Search reviewed estimation methods separately from numerical evidence.

Search returns candidates, never a route decision or a payment amount. The AI
must record applicability and confirm the method's assumptions before use.
Portable SQL + JSON shares the existing local evidence DB, without embeddings.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable, Mapping

from backend.erce.formula_registry import formula_for_route
from backend.erce.variable_evidence_store import DEFAULT_VARIABLE_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS erce_method_cases (
    method_key TEXT PRIMARY KEY,
    source_bill_no TEXT NOT NULL,
    family_key TEXT NOT NULL,
    available_at TEXT NOT NULL,
    row_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS erce_method_lookup
ON erce_method_cases(available_at, source_bill_no, family_key);
CREATE TABLE IF NOT EXISTS erce_method_variable_links (
    method_key TEXT NOT NULL REFERENCES erce_method_cases(method_key),
    evidence_key TEXT NOT NULL REFERENCES erce_variable_evidence(evidence_key),
    PRIMARY KEY(method_key, evidence_key)
);
"""


def save_method_rows(rows: Iterable[Mapping[str, Any]], db_path: Path = DEFAULT_VARIABLE_DB) -> int:
    rows = list(rows)
    for row in rows:
        for key in ("method_key", "source_bill_no", "family_key", "available_at",
                    "source_ref", "payer", "baseline_check", "limitation"):
            if not str(row.get(key) or "").strip():
                raise ValueError(f"method evidence needs {key}")
        date.fromisoformat(row["available_at"])
        if row.get("review_status") != "reviewed":
            raise ValueError("only reviewed methods can be stored")
        if not row.get("match_groups") or any(not group for group in row["match_groups"]):
            raise ValueError("method evidence needs nonempty match groups")
        if row.get("evidence_kind") == "non_estimation":
            if row.get("allowed_routes") or row.get("variable_evidence_keys"):
                raise ValueError("non-estimation evidence cannot provide calculation routes or values")
            for key in ("source_quote", "required_confirmations", "reestimate_when", "fiscal_effect"):
                if not row.get(key):
                    raise ValueError(f"non-estimation evidence needs {key}")
        elif not row.get("allowed_routes"):
            raise ValueError("method evidence needs allowed routes")
        for route in row["allowed_routes"]:
            formula_for_route(route)
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as db, db:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript(SCHEMA)
        for row in rows:
            db.execute("""INSERT INTO erce_method_cases VALUES (?,?,?,?,?)
                ON CONFLICT(method_key) DO UPDATE SET
                source_bill_no=excluded.source_bill_no, family_key=excluded.family_key,
                available_at=excluded.available_at, row_json=excluded.row_json""",
                (row["method_key"], row["source_bill_no"], row["family_key"],
                 row["available_at"], json.dumps(dict(row), ensure_ascii=False, allow_nan=False)))
            db.execute("DELETE FROM erce_method_variable_links WHERE method_key=?", (row["method_key"],))
            for key in row.get("variable_evidence_keys", []):
                db.execute("INSERT INTO erce_method_variable_links VALUES (?,?)", (row["method_key"], key))
    return len(rows)


def _eligible(row: Mapping[str, Any], *, cutoff_date: str, target_bill_no: str,
              target_family_key: str, excluded_bill_nos: Iterable[str], evidence_mode: str) -> bool:
    if row.get("review_status") != "reviewed" or row["available_at"] > cutoff_date:
        return False
    if row["source_bill_no"] in excluded_bill_nos:
        return False
    if evidence_mode == "holdout":
        if target_bill_no and row["source_bill_no"] == target_bill_no:
            return False
        if target_family_key and row["family_key"] == target_family_key:
            return False
    return True


def _rows(db_path: Path, cutoff_date: str) -> list[dict[str, Any]]:
    if not Path(db_path).exists():
        return []
    with closing(sqlite3.connect(db_path)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='erce_method_cases'").fetchone():
            return []
        return [json.loads(row[0]) for row in db.execute(
            "SELECT row_json FROM erce_method_cases WHERE available_at<=? ORDER BY method_key", (cutoff_date,))]


def find_method_candidates(*, query: str, cutoff_date: str, target_bill_no: str = "",
                           target_family_key: str = "", excluded_bill_nos: Iterable[str] = (),
                           evidence_mode: str = "holdout", limit: int = 5,
                           db_path: Path = DEFAULT_VARIABLE_DB) -> list[dict[str, Any]]:
    date.fromisoformat(cutoff_date)
    if evidence_mode not in {"holdout", "development_review"}:
        raise ValueError("invalid evidence_mode")
    if not 1 <= limit <= 20:
        raise ValueError("method candidate limit must be 1..20")
    text = re.sub(r"\s+", "", query).lower()
    candidates = []
    # Deliberately do not filter by the AI's provisional route: that route may
    # itself be wrong. Lexical recall is measured before adding vector search.
    for row in _rows(db_path, cutoff_date):
        if not _eligible(row, cutoff_date=cutoff_date, target_bill_no=target_bill_no,
                         target_family_key=target_family_key, excluded_bill_nos=excluded_bill_nos,
                         evidence_mode=evidence_mode):
            continue
        matches = [[term for term in group if re.sub(r"\s+", "", term).lower() in text]
                   for group in row["match_groups"]]
        if all(matches):
            candidates.append({**row, "matched_terms": [term for group in matches for term in group],
                               "selection_status": "candidate_only"})
    return sorted(candidates, key=lambda row: (-len(row["matched_terms"]), row["method_key"]))[:limit]


def validate_non_estimation_review(payload: Mapping[str, Any], *,
                                   db_path: Path = DEFAULT_VARIABLE_DB) -> dict[str, Any]:
    """Confirm a sourced review, never turn absent DB values into zero cost.

    Confirmation notes are reviewer statements, not automatic proof that all
    external sources were searched. Return their provenance for later audit.
    """
    key = str(payload.get("decision_evidence_key") or "")
    cutoff = str(payload.get("cutoff_date") or "")
    date.fromisoformat(cutoff)
    mode = str(payload.get("evidence_mode") or "holdout")
    if mode not in {"holdout", "development_review"}:
        raise ValueError("invalid evidence_mode")
    row = next((r for r in _rows(db_path, cutoff) if r["method_key"] == key), None)
    if row is None or row.get("evidence_kind") != "non_estimation" or not _eligible(
            row, cutoff_date=cutoff, target_bill_no=str(payload.get("bill_no") or ""),
            target_family_key=str(payload.get("target_family_key") or ""),
            excluded_bill_nos=payload.get("excluded_bill_nos") or (), evidence_mode=mode):
        raise ValueError("non-estimation evidence missing, future or excluded")
    category=row.get("decision_category")
    if category=="no_incremental_cost":
        if payload.get("reliable_estimation_basis_available") is not True:
            raise ValueError("existing-service exclusion requires a positive evidence basis")
    elif payload.get("reliable_estimation_basis_available") is not False:
        raise ValueError("review whether reliable estimation basis is available first")
    notes = payload.get("decision_confirmations") or {}
    if not isinstance(notes, Mapping):
        raise ValueError("decision confirmations must be an object")
    for condition in row["required_confirmations"]:
        if not isinstance(notes.get(condition), str) or not notes[condition].strip():
            raise ValueError(f"decision confirmation required: {condition}")
    facts=payload.get("decision_facts") or {}
    if not isinstance(facts,Mapping):
        raise ValueError("decision facts must be an object")
    for condition,expected in row.get("required_facts",{}).items():
        if facts.get(condition) is not expected:
            raise ValueError(f"decision fact mismatch: {condition}")
    decision="no_incremental_cost" if category=="no_incremental_cost" else "out_of_scope" if category=="outside_estimate_scope" else "not_estimated"
    return dict(decision=decision, amount=None,
                source_decision_label=row.get("source_decision_label", "미추계"),
                decision_evidence_key=key, reason=row["reason"],
                source_ref=row["source_ref"], source_quote=row["source_quote"],
                additional_source_quote=row.get("additional_source_quote",""),
                fiscal_effect=row["fiscal_effect"], confirmed_conditions=dict(notes),confirmed_facts=dict(facts),
                reestimate_when=row["reestimate_when"], limitation=row["limitation"])


def validate_selected_methods(payload: Mapping[str, Any], *,
                              db_path: Path = DEFAULT_VARIABLE_DB) -> list[dict[str, Any]]:
    keys = payload.get("selected_method_keys") or []
    if not isinstance(keys, (list, tuple)) or any(not isinstance(key, str) for key in keys) or len(set(keys)) != len(keys):
        raise ValueError("selected_method_keys must be a unique list")
    if not keys:
        return []
    cutoff = str(payload.get("cutoff_date") or "")
    date.fromisoformat(cutoff)
    mode = str(payload.get("evidence_mode") or "holdout")
    if mode not in {"holdout", "development_review"}:
        raise ValueError("invalid evidence_mode")
    indexed = {row["method_key"]: row for row in _rows(db_path, cutoff)}
    route = str(payload.get("route_key") or "")
    if payload.get("route_path"):
        from backend.erce.route_tree import route_for_path
        route = route_for_path(payload["route_path"])
    reasons = payload.get("method_selection_reasons") or {}
    confirmations = payload.get("method_confirmations") or {}
    if not isinstance(reasons, Mapping) or not isinstance(confirmations, Mapping):
        raise ValueError("method reasons and confirmations must be objects")
    result = []
    for key in keys:
        row = indexed.get(key)
        if row is None or not _eligible(row, cutoff_date=cutoff,
                target_bill_no=str(payload.get("bill_no") or ""),
                target_family_key=str(payload.get("target_family_key") or ""),
                excluded_bill_nos=payload.get("excluded_bill_nos") or (), evidence_mode=mode):
            raise ValueError(f"method is missing, future or excluded: {key}")
        if row.get("evidence_kind") == "non_estimation":
            raise ValueError("non-estimation evidence cannot be used as a calculation method")
        if route not in row["allowed_routes"]:
            raise ValueError(f"method/formula route mismatch: {key}")
        if row.get("levy_band_model") and row["levy_band_model"] != payload.get("levy_band_model"):
            raise ValueError(f"method levy band model mismatch: {key}")
        for field in ("worker_support_model","worker_forecast_basis","levy_sector_model","ombudsman_component"):
            if row.get(field) and row[field] != payload.get(field):
                raise ValueError(f"method {field} mismatch: {key}")
        if row.get("birth_order_share_scenario") and row["birth_order_share_scenario"] != payload.get("birth_order_share_scenario"):
            raise ValueError(f"method birth order share scenario mismatch: {key}")
        if row.get("management_fee_scenario") and row["management_fee_scenario"] != payload.get("management_fee_scenario"):
            raise ValueError(f"method management fee scenario mismatch: {key}")
        if payload.get("payer") != row["payer"]:
            raise ValueError(f"method payer must be confirmed: {key}")
        if not isinstance(reasons.get(key), str) or not reasons[key].strip():
            raise ValueError(f"method applicability reason required: {key}")
        notes = confirmations.get(key) or {}
        if not isinstance(notes, Mapping):
            raise ValueError(f"method confirmations must be an object: {key}")
        for condition in row["required_confirmations"]:
            if not isinstance(notes.get(condition), str) or not notes[condition].strip():
                raise ValueError(f"method confirmation required ({condition}): {key}")
        result.append({**row, "applicability_reason": reasons[key], "confirmed_assumptions": dict(notes)})
    return result
