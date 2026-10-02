from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from backend.erce.health_insurance_care_evidence import (
    care_reference_candidates, health_insurance_care_rows, health_insurance_care_answer_rows,
)
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.web_bridge import calculate_erce_web_item


def test_pre_bill_care_rates_are_reusable_candidates_not_target_answers():
    rows = health_insurance_care_rows()
    prices = {row["scenario_key"]: row["value"] for row in rows
              if row["variable_key"] == "insurer_daily_benefit"}
    assert prices == {"A": 14634, "B": 17217, "C": 17935}
    assert not any(row["source_bill_no"] == "2200100" for row in rows)
    assert not any(row["value"] == 1200 for row in rows)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "evidence.sqlite3"
        assert save_variable_rows(rows, path) == 6
        candidates = care_reference_candidates(
            cutoff_date="2024-06-03", target_bill_no="2200100", db_path=path)
        assert len(candidates) == 6
        assert {row["value"] for row in candidates
                if row["variable_key"] == "government_support_rate"} == {.141}
        assert len(care_reference_candidates(
            cutoff_date="2024-02-21", target_bill_no="2200100", db_path=path)) == 1
        assert care_reference_candidates(
            cutoff_date="2023-10-09", target_bill_no="2200100", db_path=path) == []


def test_web_returns_hints_without_automatically_filling_formula_inputs():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "evidence.sqlite3"
        save_variable_rows(health_insurance_care_rows(), path)
        def candidates(**kwargs):
            return care_reference_candidates(**kwargs, db_path=path)
        with patch("backend.erce.web_bridge.care_reference_candidates", side_effect=candidates):
            result = calculate_erce_web_item({
                "route_key": "health_insurance_treasury_support",
                "bill_no": "2200100", "cutoff_date": "2024-06-03", "years": 5,
                "policy_domain": "건강보험 요양병원 간병급여",
            })
        assert result["status"] == "needs_input"
        assert result["missingVariables"] == [
            "insurance_benefit_cohorts", "government_support_rate"]
        assert len(result["referenceCandidates"]) == 6
        assert all(row["requiresConfirmation"] for row in result["referenceCandidates"])
        other = calculate_erce_web_item({
            "route_key": "health_insurance_treasury_support", "bill_no": "other",
            "cutoff_date": "2024-06-03", "policy_domain": "건강보험 의약품급여",
        })
        assert "referenceCandidates" not in other


def test_post_answer_observations_can_help_later_bills_but_not_the_source_bill():
    rows = health_insurance_care_answer_rows()
    assert len(rows) == 22
    assert all(row["source_bill_no"] == "2200100" for row in rows)
    assert all(row["available_at"] == "2024-07-15" for row in rows)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "evidence.sqlite3"
        save_variable_rows(health_insurance_care_rows() + rows, path)
        assert len(care_reference_candidates(
            cutoff_date="2024-06-03", target_bill_no="2200100", db_path=path)) == 6
        assert len(care_reference_candidates(
            cutoff_date="2024-08-01", target_bill_no="2200100", db_path=path)) == 6
        later = care_reference_candidates(
            cutoff_date="2024-08-01", target_bill_no="later-bill", db_path=path)
        assert len(later) == 28
        assert any(row["stay_band"] == "181-210" and row["scenario_key"] == "A"
                   for row in later)
