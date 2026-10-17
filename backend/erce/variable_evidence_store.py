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
    compensation_population_scope: str = "", survivor_group: str = "",
    excluded_bill_nos: Iterable[str] = (),
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
    excluded = list(excluded_bill_nos)
    if excluded:
        sql += " AND source_bill_no NOT IN (" + ",".join("?" for _ in excluded) + ")"
        values.extend(excluded)
    sql += " ORDER BY evidence_key"
    with closing(sqlite3.connect(db_path)) as db:
        rows = [json.loads(row[0]) for row in db.execute(sql, values)]
    return [row for row in rows if row.get("review_status") == "reviewed"
            and (not compensation_population_scope or not row.get("compensation_population_scope")
                 or row["compensation_population_scope"] == compensation_population_scope)
            and (not survivor_group or not row.get("survivor_group")
                 or row["survivor_group"] == survivor_group)
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
            if row["source_bill_no"] in (payload.get("excluded_bill_nos") or []):
                raise ValueError(f"selected DB evidence is from an excluded bill: {key}")
            if row.get("reuse_policy") == "target_only" and not same_target:
                raise ValueError(f"selected DB evidence belongs to a different target: {key}")
            if row.get("requires_applicability_note") and not same_target and not str(reasons.get(key) or "").strip():
                raise ValueError(f"selected comparable evidence needs applicability reason: {key}")
            if row.get("variable_role") == "constraint" or row.get("value_kind") == "upper_limit":
                cap_scenario = (
                    row.get("variable_key") == "grant_cap_per_reference_period"
                    and route == "transfer_spouse_leave_extension"
                    and payload.get("use_upper_limit_as_scenario") is True
                    and str(payload.get("upper_limit_scenario_note") or "").strip()
                )
                scholarship_cap_scenario = (
                    row.get("variable_key") in {"existing_support_cap", "new_support_cap"}
                    and row.get("scholarship_calculation") == "tuition_capped_delta"
                    and route == "transfer_recipient_delta"
                    and payload.get("scholarship_calculation") == "tuition_capped_delta"
                    and str(payload.get("scholarship_support_confirmation_note") or "").strip()
                )
                if not (cap_scenario or scholarship_cap_scenario):
                    raise ValueError(f"constraint is not an automatic payment amount: {key}")
            if row.get("allowed_routes") and route not in row["allowed_routes"]:
                raise ValueError(f"selected DB evidence service/formula mismatch: {key}")
            for row_field, payload_field in (("care_channel", "care_channel"),
                                             ("support_derivation", "support_derivation"),
                                             ("support_fiscal_scope", "support_fiscal_scope"),
                                             ("loan_income_band", "loan_income_band"),
                                             ("student_loan_region", "student_loan_region"),
                                             ("center_kind", "center_kind"),
                                             ("child_allowance_scenario", "child_allowance_scenario"),
                                             ("child_population_geography", "child_population_geography"),
                                             ("recipient_population_basis", "recipient_population_basis"),
                                             ("disability_benefit_scope", "disability_benefit_scope"),
                                             ("disability_population_basis", "disability_population_basis"),
                                             ("disability_composition_basis", "disability_composition_basis"),
                                             ("disability_cpi_basis", "disability_cpi_basis"),
                                             ("pension_income_band", "pension_income_band"),
                                             ("pension_rate_basis", "pension_rate_basis"),
                                             ("pension_history_usage", "pension_history_usage"),
                                             ("pension_baseline_version", "pension_baseline_version"),
                                             ("pension_standard_vintage", "pension_standard_vintage"),
                                             ("pension_distribution_basis", "pension_distribution_basis"),
                                             ("pension_group", "pension_group"),
                                             ("low_income_scope", "low_income_scope"),
                                             ("replay_purpose", "replay_purpose"),
                                             ("population_geography", "population_geography"),
                                             ("statistical_sex", "statistical_sex"),
                                             ("population_vintage", "population_vintage"),
                                             ("benefit_index_base_year", "benefit_index_base_year"),
                                             ("child_index_base_year", "child_index_base_year"),
                                             ("parent_benefit_age", "parent_benefit_age"),
                                             ("single_parent_population_scope", "single_parent_population_scope"),
                                             ("single_parent_projection", "single_parent_projection"),
                                             ("jobseeker_cohort", "jobseeker_cohort"),
                                             ("management_fee_scenario", "management_fee_scenario"),
                                             ("management_price_base_year", "management_price_base_year"),
                                             ("moving_price_base_year", "moving_price_base_year"),
                                             ("repair_recipient_scope", "repair_recipient_scope"),
                                             ("grandparent_count_basis", "grandparent_count_basis"),
                                             ("grandparent_allowance_mode", "grandparent_allowance_mode"),
                                             ("foreign_parent_fee_basis", "foreign_parent_fee_basis"),
                                             ("medical_unit_basis", "medical_unit_basis"),
                                             ("rail_beneficiary_scope", "rail_beneficiary_scope"),
                                             ("rail_operator_scope", "rail_operator_scope"),
                                             ("disability_child_scope", "disability_child_scope"),
                                             ("disabled_worker_scope", "disabled_worker_scope"),
                                             ("wage_gap_scenario", "wage_gap_scenario"),
                                             ("levy_payer_scope", "levy_payer_scope"),
                                             ("levy_band_model", "levy_band_model"),
                                             ("assistant_operand_basis", "assistant_operand_basis"),
                                             ("worker_support_model", "worker_support_model"),
                                             ("worker_forecast_basis", "worker_forecast_basis"),
                                             ("levy_sector_model", "levy_sector_model"),
                                             ("levy_tariff_basis", "levy_tariff_basis"),
                                             ("classroom_price_basis", "classroom_price_basis"),
                                             ("workplace_form", "workplace_form"),
                                             ("application_growth_scenario", "application_growth_scenario"),
                                             ("research_service_function", "research_service_function"),
                                             ("regional_population_scope", "regional_population_scope"),
                                             ("research_cost_scope", "research_cost_scope"),
                                             ("committee_role_profile", "committee_role_profile"),
                                             ("child_support_model", "child_support_model"),
                                             ("advance_amount_basis", "advance_amount_basis"),
                                             ("statutory_standard_table_required", "statutory_standard_table_required"),
                                             ("meeting_mode", "meeting_mode"),
                                             ("repair_increment_base_year", "repair_increment_base_year"),
                                             ("housing_income_cutoff", "housing_income_cutoff"),
                                             ("livelihood_floor_projection", "livelihood_floor_projection"),
                                             ("parent_population_basis", "parent_population_basis"),
                                             ("birth_order_share_scenario", "birth_order_share_scenario"),
                                             ("birth_order_population_basis", "birth_order_population_basis"),
                                             ("scenario_key", "benefit_scenario"),
                                             ("insurance_line", "insurance_line"),
                                             ("system_kind", "system_kind"),
                                             ("compensation_population_scope", "compensation_population_scope"),
                                             ("survivor_group", "survivor_group"),
                                             ("veteran_support_kind", "veteran_support_kind"),
                                             ("veteran_population_group", "veteran_population_group"),
                                             ("noise_support_component", "noise_support_component"),
                                             ("committee_identity", "committee_identity"),
                                             ("committee_workload_proxy", "committee_workload_proxy"),
                                             ("service_cost_basis", "service_cost_basis"),
                                             ("awareness_price_projection", "awareness_price_projection"),
                                             ("awareness_scale_profile", "awareness_scale_profile"),
                                             ("commemorative_event_scale", "commemorative_event_scale"),
                                             ("event_price_projection", "event_price_projection"),
                                             ("public_financing_scope", "public_financing_scope"),
                                             ("loan_penalty_profile", "loan_penalty_profile"),
                                             ("scholarship_population_group", "scholarship_population_group"),
                                             ("scholarship_income_band", "scholarship_income_band"),
                                             ("scholarship_policy_reference_year", "scholarship_policy_reference_year"),
                                             ("scholarship_calculation", "scholarship_calculation"),
                                             ("scholarship_cohort", "scholarship_cohort"),
                                             ("scholarship_program", "scholarship_program"),
                                             ("university_kind", "university_kind"),
                                             ("staff_pay_profile", "staff_pay_profile"),
                                             ("school_sector", "school_sector"),
                                             ("staffing_target_group", "staffing_target_group"),
                                             ("research_service_kind", "research_service_kind"),
                                             ("research_cycle_basis", "research_cycle_basis"),
                                             ("personnel_cost_component", "personnel_cost_component"),
                                             ("payer", "payer")):
                if row.get(row_field) not in (None, "") and row[row_field] != payload.get(payload_field):
                    raise ValueError(f"selected DB evidence {payload_field} mismatch: {key}")
            for feature, required in (row.get("required_workload_features") or {}).items():
                actual_feature = (payload.get("workload_features") or {}).get(feature)
                if actual_feature is not required:
                    raise ValueError(f"selected DB evidence workload mismatch ({feature}): {key}")
            if row.get("recipient_population_basis"):
                for age_field in ("population_age_min", "population_age_max"):
                    if row.get(age_field) != payload.get(age_field):
                        raise ValueError(f"selected DB evidence {age_field} mismatch: {key}")
            if row.get("already_adjusted_for_execution") and any(
                name in (payload.get(layer) or {})
                for layer in ("explicit_inputs", "actual_inputs", "official_inputs", "calculated_inputs", "selected_variable_inputs")
                for name in ("participation_rate", "growth_rate", "growth_rates_by_year")
            ):
                raise ValueError(f"selected DB evidence already includes execution/projection adjustment: {key}")
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
                frozen_scholarship = (
                    row.get("scholarship_calculation") == "tuition_capped_delta"
                    and row.get("variable_role") == "constraint"
                    and row.get("source_class") == "official_standard"
                    and payload.get("scholarship_policy_projection") == "freeze_reference_policy"
                    and str(payload.get("scholarship_policy_confirmation_note") or "").strip()
                    and int(payload["start_year"]) >= row["scholarship_policy_reference_year"]
                )
                if not frozen_scholarship:
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
            if row.get("source_bill_version_match") is False and not (
                payload.get("use_unmatched_source_as_reference") is True
                and str(payload.get("unmatched_source_reference_note") or "").strip()
            ):
                raise ValueError(f"selected DB evidence needs unmatched-source reference confirmation: {key}")
            if row.get("requires_reference_scenario") and (
                payload.get("estimate_purpose") != "reference_scenario"
                or not str(payload.get("reference_notice") or "").strip()
            ):
                raise ValueError(f"selected DB evidence requires a labelled reference scenario: {key}")
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
