import tempfile
import unittest
from pathlib import Path
from backend.erce.grandparent_care_evidence import grandparent_parallel_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows, validate_non_estimation_review
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_grandparent_parallel import parallel_payload, recovery_review
from backend.erce.web_bridge import calculate_erce_web_item


class GrandparentParallelTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "test.sqlite3"
        save_variable_rows(grandparent_parallel_rows(), self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"] == "2200629"], self.db)

    def payload(self):
        return {**parallel_payload(), "bill_no": "NEW_PARALLEL_CARE", "evidence_mode": "holdout"}

    def calculate(self, p):
        return calculate_erce_web_item(p, variable_db_path=self.db)

    def test_population_counts_prices_and_display_precision(self):
        r = self.calculate(self.payload())
        self.assertEqual(r["status"], "computed_review")
        self.assertEqual([round(v / 100000) for v in r["annualAmountsThousand"]], [2157, 2060, 2012, 1992, 2002])
        self.assertAlmostEqual(sum(r["annualAmountsThousand"]) / 100000, 10222.2432)
        t = r["derivationTrace"][0]
        self.assertEqual(t["age_child_counts"], {"0": 18030, "1": 8902, "2": 9249, "3": 12644, "4": 11461, "5": 14622})
        self.assertEqual(t["gross_monthly_support"], 240000)
        self.assertTrue(all(v == 240000 for v in t["net_monthly_by_age"].values()))

    def test_confirmation_required_and_missing_values_not_generated(self):
        r = self.calculate({**self.payload(), "care_proxy_confirmed": False})
        self.assertEqual(r["status"], "needs_input")
        self.assertIn("care_parallel_proxy_confirmation", r["missingDerivationVariables"])
        p = self.payload()
        p["selected_evidence_keys"] = [key for key in p["selected_evidence_keys"] if "grandparent_care_shares" not in key]
        self.assertIn("grandparent_care_shares", self.calculate(p)["missingDerivationVariables"])
        with self.assertRaises(ValueError):
            self.calculate({**self.payload(), "bill_no": "2200629"})

    def test_allowance_parallel_cannot_deduct_existing_allowance(self):
        p = self.payload()
        p["explicit_inputs"] = {"foregone_allowance_by_age": dict(value=dict.fromkeys(map(str, range(6)), 100000),
             unit="age_to_KRW/month", source_ref="잘못된 수당차감 입력 검증")}
        with self.assertRaises(ValueError):
            self.calculate(p)
        with self.assertRaises(ValueError):
            self.calculate({**self.payload(), "grandparent_allowance_mode": "replacement_net"})

    def test_recovery_non_estimation_requires_forecast_review(self):
        p = {**recovery_review(), "bill_no": "NEW_PARALLEL_CARE", "evidence_mode": "holdout"}
        r = validate_non_estimation_review(p, db_path=self.db)
        self.assertEqual(r["decision"], "not_estimated")
        self.assertIsNone(r["amount"])
        with self.assertRaises(ValueError):
            validate_non_estimation_review({**p, "reliable_estimation_basis_available": True}, db_path=self.db)
        p["decision_facts"]["new_program_implemented"] = True
        with self.assertRaises(ValueError):
            validate_non_estimation_review(p, db_path=self.db)
