"""Small local variable store: AI chooses evidence keys, not document totals.

Portable columns and JSON text allow later Postgres/Supabase migration. SQLite
is only the local persistence layer. No similarity ranking chooses a number.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from contextlib import closing
from pathlib import Path
from typing import Any, Iterable, Mapping

DEFAULT_VARIABLE_DB = Path(__file__).resolve().parents[1] / "generated/erce_variable_evidence.sqlite3"
SCHEMA = """
CREATE TABLE IF NOT EXISTS erce_variable_evidence (
    evidence_key TEXT PRIMARY KEY,
    variable_key TEXT NOT NULL,
    agency TEXT NOT NULL,
    policy_domain TEXT NOT NULL,
    scope TEXT NOT NULL,
    available_at TEXT NOT NULL,
    source_bill_no TEXT NOT NULL,
    row_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS erce_variable_lookup
ON erce_variable_evidence(variable_key, available_at, agency, policy_domain);
"""


def save_variable_rows(rows: Iterable[Mapping[str, Any]], db_path: Path = DEFAULT_VARIABLE_DB) -> int:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with closing(sqlite3.connect(db_path)) as db, db:
        db.executescript(SCHEMA)
        for row in rows:
            for key in ("unit", "source_ref", "service_function", "variable_role", "reuse_policy"):
                if not str(row.get(key) or "").strip():
                    raise ValueError(f"variable evidence needs {key}")
            date.fromisoformat(str(row["available_at"]))
            if "value" not in row:
                raise ValueError("variable evidence needs value")
            fields = tuple(str(row[key]) for key in (
                "evidence_key", "variable_key", "agency", "policy_domain", "scope",
                "available_at", "source_bill_no"))
            db.execute("""INSERT INTO erce_variable_evidence VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(evidence_key) DO UPDATE SET
                variable_key=excluded.variable_key, agency=excluded.agency,
                policy_domain=excluded.policy_domain, scope=excluded.scope,
                available_at=excluded.available_at, source_bill_no=excluded.source_bill_no,
                row_json=excluded.row_json""", (*fields, json.dumps(dict(row), ensure_ascii=False, allow_nan=False)))
            count += 1
    return count


def find_variable_candidates(
    *, cutoff_date: str, agency: str = "", policy_domain: str = "",
    variable_key: str | None = None, target_bill_no: str = "",
    evidence_mode: str = "holdout", db_path: Path = DEFAULT_VARIABLE_DB,
    start_year: int | None = None, years: int = 5,
) -> list[dict[str, Any]]:
    """Expose compatible rows to the AI, without selecting or averaging them."""
    if evidence_mode not in {"holdout", "development_review"}:
        raise ValueError("invalid evidence_mode")
    date.fromisoformat(cutoff_date)
    if not Path(db_path).exists():
        return []
    sql = "SELECT row_json FROM erce_variable_evidence WHERE available_at<=?"
    values = [cutoff_date]
    for field, value in (("agency", agency), ("policy_domain", policy_domain)):
        if value:
            sql += f" AND {field}=?"
            values.append(value)
    if variable_key:
        sql += " AND variable_key=?"
        values.append(variable_key)
    if evidence_mode == "holdout" and target_bill_no:
        sql += " AND source_bill_no<>?"
        values.append(target_bill_no)
    sql += " ORDER BY evidence_key"
    with closing(sqlite3.connect(db_path)) as db:
        rows = [json.loads(row[0]) for row in db.execute(sql, values)]
    return [row for row in rows if row.get("review_status") == "reviewed"
            and (row.get("reuse_policy") != "target_only" or row["source_bill_no"] == target_bill_no)
            and (start_year is None or _years_match(row, start_year, years))]


def _years_match(row: Mapping[str, Any], start_year: int, years: int) -> bool:
    period = list(range(start_year, start_year + years))
    if row.get("value_years") and list(row["value_years"]) != period:
        return False
    return all((row.get("valid_from_year") is None or year >= row["valid_from_year"])
               and (row.get("valid_to_year") is None or year <= row["valid_to_year"])
               for year in period)


def evidence_payload_from_db(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Hydrate only AI-selected IDs, maintaining source/temporal/scope gates."""
    keys = payload.get("selected_evidence_keys")
    if keys is None:
        return payload
    if not isinstance(keys, (list, tuple)) or any(not isinstance(key, str) for key in keys) or len(set(keys)) != len(keys):
        raise ValueError("selected_evidence_keys must be a unique list")
    path = Path(payload.get("variable_db_path") or DEFAULT_VARIABLE_DB)
    if not path.exists():
        raise ValueError("ERCE variable evidence database does not exist")
    mode = str(payload.get("evidence_mode") or "holdout")
    if mode not in {"holdout", "development_review"}:
        raise ValueError("invalid evidence_mode")
    cutoff = date.fromisoformat(str(payload.get("cutoff_date") or ""))
    selected = dict(payload.get("selected_variable_inputs") or {})
    official = dict(payload.get("official_inputs") or {})
    actual = dict(payload.get("actual_inputs") or {})
    reasons = payload.get("evidence_selection_reasons") or {}
    route = str(payload.get("route_key") or "")
    if "route_path" in payload:
        from backend.erce.route_tree import route_for_path
        route = route_for_path(payload["route_path"])
    with closing(sqlite3.connect(path)) as db:
        for key in keys:
            stored = db.execute("SELECT row_json FROM erce_variable_evidence WHERE evidence_key=?", (key,)).fetchone()
            if stored is None:
                raise ValueError(f"unknown selected evidence key: {key}")
            row = json.loads(stored[0])
            if row.get("review_status") != "reviewed":
                raise ValueError(f"selected DB evidence is not reviewed: {key}")
            if date.fromisoformat(row["available_at"]) > cutoff:
                raise ValueError(f"selected DB evidence is from the future: {key}")
            same_target = row["source_bill_no"] == str(payload.get("bill_no") or "")
            if row.get("reuse_policy") == "target_only" and not same_target:
                raise ValueError(f"selected DB evidence belongs to a different target: {key}")
            if row.get("variable_role") == "constraint" or row.get("value_kind") == "upper_limit":
                raise ValueError(f"constraint is not an automatic payment amount: {key}")
            if row.get("allowed_routes") and route not in row["allowed_routes"]:
                raise ValueError(f"selected DB evidence service/formula mismatch: {key}")
            for feature, required in (row.get("required_workload_features") or {}).items():
                actual_feature = (payload.get("workload_features") or {}).get(feature)
                if actual_feature is not required:
                    raise ValueError(f"selected DB evidence workload mismatch ({feature}): {key}")
            if row.get("required_staff_grade_profile"):
                profile=payload.get("staff_grade_profile")
                expected={grade:count for grade,count in row["required_staff_grade_profile"].items() if count != 0}
                if not isinstance(profile,Mapping) or {grade:count for grade,count in profile.items() if count != 0} != expected:
                    raise ValueError(f"selected DB evidence staff-grade composition mismatch: {key}")
            if row.get("requires_retroactive_application"):
                applicability = payload.get("retroactive_application") or {}
                if applicability.get("enabled") is not True or not str(applicability.get("source_ref") or "").strip():
                    raise ValueError(f"historical backlog needs explicit retroactive application evidence: {key}")
            if payload.get("start_year") is not None and not _years_match(row, int(payload["start_year"]), int(payload.get("years") or 5)):
                raise ValueError(f"selected DB evidence year mismatch: {key}")
            for dimension in ("agency", "policy_domain", "scope"):
                target = payload.get(dimension)
                if target and str(target) != row[dimension]:
                    # Cross-domain comparables need the AI's recorded applicability
                    # judgement; no implicit semantic match changes their scope.
                    if row.get("reuse_policy") != "comparable" or not str(reasons.get(key) or "").strip():
                        raise ValueError(f"selected DB evidence scope mismatch ({dimension}): {key}")
            if same_target and mode != "development_review":
                raise ValueError(f"selected DB evidence is the target answer: {key}")
            variable = row["variable_key"]
            if row.get("source_class") == "official_standard":
                layer = official
            elif row.get("source_class") == "target_current_actual" and same_target:
                layer = actual
            else:
                layer = selected
            if variable in layer:
                raise ValueError(f"multiple selected values for variable: {variable}")
            layer[variable] = row
    return {**payload, "selected_variable_inputs": selected, "official_inputs": official,
            "actual_inputs": actual}
