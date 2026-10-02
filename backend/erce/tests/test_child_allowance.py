import tempfile
import unittest
from pathlib import Path

from backend.erce.child_allowance_evidence import child_allowance_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.variable_evidence_store import save_variable_rows, find_variable_candidates


class ChildAllowanceTests(unittest.TestCase):
    def test_population_replay_and_gates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "variables.sqlite3"
            rows = child_allowance_rows()
            save_variable_rows(rows, path)
            self.assertEqual(find_variable_candidates(cutoff_date="2024-06-12", db_path=path), [])
            self.assertEqual(find_variable_candidates(cutoff_date="2024-06-13", target_bill_no="2200147", db_path=path), [])
            self.assertEqual(find_variable_candidates(cutoff_date="2024-06-13", start_year=2026, years=5, variable_key="recipient_count", db_path=path), [])
            base = dict(bill_no="2200147", cutoff_date="2024-06-13", start_year=2025,
                        years=5, evidence_mode="development_review", variable_db_path=path)
            explicit = {"benefit_per_recipient": {"value": 200000, "unit": "KRW/person/month", "source_ref": "원문 제4조"},
                        "payments_per_year": {"value": 12, "unit": "month/year", "source_ref": "원문 매월"}}
            old_payload = {**base, "route_key": "transfer_recipient_delta",
                           "explicit_inputs": {**explicit, "existing_benefit_per_recipient": {"value":100000, "source_ref":"현행 제4조"}},
                           "selected_evidence_keys": [rows[1]["evidence_key"],rows[3]["evidence_key"]]}
            old = estimate_routed_item(old_payload)
            new = estimate_routed_item({**base, "route_key": "transfer_recipient", "explicit_inputs": explicit,
                                       "selected_evidence_keys": [rows[2]["evidence_key"],rows[3]["evidence_key"]]})
            combined = tuple(a+b for a,b in zip(old.annual_amounts_thousand, new.annual_amounts_thousand))
            expected = tuple(round((a*200000-b*100000)*12*.972/1000)
                             for a,b in zip(rows[0]["value"], rows[1]["value"]))
            self.assertEqual(combined, expected)
            self.assertEqual(old.resolved_variables["participation_rate"].value, .972)
            with self.assertRaisesRegex(ValueError, "target answer"):
                estimate_routed_item({**old_payload, "evidence_mode":"holdout"})
            with self.assertRaisesRegex(ValueError, "applicability"):
                estimate_routed_item({**old_payload, "bill_no":"other"})
            with self.assertRaises(ValueError):
                estimate_routed_item({**old_payload, "explicit_inputs": {**old_payload["explicit_inputs"], "participation_rate":{"value":1.1}}})

    def test_actual_recipients_default_to_full_payment(self):
        result = estimate_routed_item({"route_key":"transfer_recipient_delta", "years":1,
                                      "explicit_inputs":{"recipient_count":{"value":100},
                                          "benefit_per_recipient":{"value":200000},
                                          "existing_benefit_per_recipient":{"value":100000},
                                          "payments_per_year":{"value":12}}})
        self.assertEqual(result.annual_amounts_thousand, (120000,))
