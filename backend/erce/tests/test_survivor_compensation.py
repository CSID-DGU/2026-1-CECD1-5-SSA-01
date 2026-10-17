import tempfile
import unittest
from pathlib import Path

from backend.erce.engine import estimate_routed_item
from backend.erce.survivor_compensation_evidence import survivor_compensation_rows
from backend.erce.variable_evidence_store import save_variable_rows, find_variable_candidates


class SurvivorCompensationTests(unittest.TestCase):
    def test_cohorts_accumulate_and_survival_is_required(self):
        base = dict(route_key="survivor_pension_cohort_delta", years=3,
                    explicit_inputs=dict(new_survivors=10, initial_annual_pension_delta=1000,
                        survival_by_cohort=[[1, .9, .8], [1, .9], [1]],
                        pension_index_factors=1, price_index_factors=1))
        self.assertEqual(estimate_routed_item(base).annual_amounts_thousand, (10, 19, 27))
        invalid = {**base["explicit_inputs"], "survival_by_cohort": [[1, .9, .95], [1, .9], [1]]}
        with self.assertRaises(ValueError):
            estimate_routed_item({**base, "explicit_inputs": invalid})
        missing = {k:v for k,v in base["explicit_inputs"].items() if k != "survival_by_cohort"}
        with self.assertRaisesRegex(ValueError, "survival_by_cohort"):
            estimate_routed_item({**base, "explicit_inputs": missing})

    def test_death_grant_does_not_accumulate(self):
        result = estimate_routed_item(dict(route_key="death_grant_delta", years=3,
            explicit_inputs=dict(new_survivors=10, monthly_income_delta=1000,
                                 grant_months=2, price_index_factors=1)))
        self.assertEqual(result.annual_amounts_thousand, (20,20,20))

    def test_reviewed_first_year_replay_from_db(self):
        rows = survivor_compensation_rows()
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder)/"variables.sqlite3"
            save_variable_rows(rows, db)
            self.assertTrue(all(r["source_bill_no"] != "2201105" for r in
                find_variable_candidates(target_bill_no="2201105", cutoff_date="2024-08-22", db_path=db)))
            total = 0
            for group in ("ordinary", "dangerous"):
                for route in ("survivor_pension_cohort_delta", "death_grant_delta"):
                    keys = [r["evidence_key"] for r in rows if r["survivor_group"] == group
                            and route in r["allowed_routes"] and r["source_bill_no"] == "2201105"]
                    explicit = {"price_index_factors":1}
                    if route == "survivor_pension_cohort_delta":
                        explicit.update(survival_by_cohort=[[1]], pension_index_factors=1)
                    result = estimate_routed_item(dict(route_key=route, years=1, start_year=2026,
                        bill_no="2201105", cutoff_date="2024-08-22", evidence_mode="development_review",
                        compensation_population_scope="all_civil_servants", survivor_group=group,
                        variable_db_path=db, selected_evidence_keys=keys,
                        evidence_selection_reasons={k:"동일 대상 정답 확인 후 재현; 2024년 불변가격" for k in keys},
                        explicit_inputs=explicit))
                    total += result.annual_amounts_thousand[0]
            self.assertEqual(total, 95137)

    def test_population_scope_gate_and_police_firefighters_replay(self):
        rows = survivor_compensation_rows()
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder)/"variables.sqlite3"
            save_variable_rows(rows, db)
            candidates = find_variable_candidates(target_bill_no="new_bill", cutoff_date="2026-10-02",
                db_path=db, compensation_population_scope="police_firefighters")
            counts = [r for r in candidates if r["variable_key"] == "new_survivors"]
            self.assertEqual(sorted(r["value"] for r in counts), [5,14])
            total = 0
            for group in ("ordinary", "dangerous"):
                for route in ("survivor_pension_cohort_delta", "death_grant_delta"):
                    keys = [r["evidence_key"] for r in candidates if r["survivor_group"] == group
                            and route in r["allowed_routes"]]
                    explicit = {"price_index_factors":1}
                    if route == "survivor_pension_cohort_delta":
                        explicit.update(survival_by_cohort=[[1]], pension_index_factors=1)
                    base = dict(route_key=route, years=1, start_year=2026, bill_no="2201700",
                        cutoff_date="2026-10-02", evidence_mode="development_review",
                        compensation_population_scope="police_firefighters", survivor_group=group,
                        variable_db_path=db, selected_evidence_keys=keys,
                        evidence_selection_reasons={k:"경찰·소방 특별승진 순직 조건 일치; 기존 연금 단가는 동일 2026년/2024 불변가격" for k in keys},
                        explicit_inputs=explicit)
                    result = estimate_routed_item(base)
                    total += result.annual_amounts_thousand[0]
                    wrong = [r["evidence_key"] for r in rows if r["source_bill_no"] == "2201105"
                             and r["variable_key"] == "new_survivors" and r["survivor_group"] == group][0]
                    bad_keys = [wrong if k.endswith("new_survivors:2024") else k for k in keys]
                    with self.assertRaisesRegex(ValueError, "population_scope mismatch"):
                        estimate_routed_item({**base, "selected_evidence_keys":bad_keys,
                            "evidence_selection_reasons":{**base["evidence_selection_reasons"], wrong:"법률 주제가 비슷하다는 이유만으로 선택하면 거절되어야 함"}})
            self.assertEqual(total,62165)
