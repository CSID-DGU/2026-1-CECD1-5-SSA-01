import tempfile
import unittest
from pathlib import Path

from backend.erce.child_asset_evidence import child_asset_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.variable_evidence_store import save_variable_rows, find_variable_candidates


class ChildAssetTests(unittest.TestCase):
    def test_monthly_formula_requires_months_and_monthly_units(self):
        payload = {"route_key": "transfer_child_asset_monthly", "years": 2,
                   "explicit_inputs": {
                       "recipient_count": {"value": [100, 80]},
                       "benefit_per_recipient": {"value": 1000, "unit": "KRW/person/month"},
                       "payments_per_year": {"value": [12, 6]}}}
        self.assertEqual(estimate_routed_item(payload).annual_amounts_thousand, (1200, 480))
        for change in ({"payments_per_year": {"value": 13}},
                       {"benefit_per_recipient": {"value": 1000, "unit": "KRW/person/year"}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                estimate_routed_item({**payload, "explicit_inputs": {**payload["explicit_inputs"], **change}})
        del payload["explicit_inputs"]["payments_per_year"]
        with self.assertRaisesRegex(ValueError, "payments_per_year"):
            estimate_routed_item(payload)

    def test_evidence_replay_and_holdout_gates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "variables.sqlite3"
            rows = child_asset_rows()
            save_variable_rows(rows, path)
            self.assertEqual(find_variable_candidates(cutoff_date="2024-06-14", db_path=path), [])
            self.assertEqual(find_variable_candidates(cutoff_date="2024-06-18", target_bill_no="2200486", db_path=path), [])
            candidates = find_variable_candidates(cutoff_date="2024-06-18", target_bill_no="other", start_year=2026, years=5, db_path=path)
            self.assertEqual(len(candidates), 3)
            payload = {"route_key": "transfer_child_asset_monthly", "bill_no": "2200486",
                       "cutoff_date": "2024-06-18", "start_year": 2026, "years": 5,
                       "evidence_mode": "development_review", "variable_db_path": path,
                       "benefit_scenario": "child_asset_monthly_maximum_100000",
                       "selected_evidence_keys": [row["evidence_key"] for row in rows[:3]]}
            result = estimate_routed_item(payload)
            self.assertEqual(result.annual_amounts_thousand,
                             (7629600000,7363200000,7117200000,6840000000,6583200000))
            with self.assertRaisesRegex(ValueError, "benefit_scenario"):
                estimate_routed_item({**payload, "benefit_scenario": ""})
            with self.assertRaisesRegex(ValueError, "target answer"):
                estimate_routed_item({**payload, "evidence_mode": "holdout"})
            with self.assertRaisesRegex(ValueError, "constraint"):
                estimate_routed_item({**payload, "selected_evidence_keys": [rows[3]["evidence_key"]]})
            with self.assertRaisesRegex(ValueError, "applicability"):
                estimate_routed_item({**payload, "bill_no": "other"})
