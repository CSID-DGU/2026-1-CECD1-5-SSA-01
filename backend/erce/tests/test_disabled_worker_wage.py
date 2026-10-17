import tempfile
import unittest
from pathlib import Path
from backend.erce.disabled_worker_wage_evidence import disabled_worker_wage_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_disabled_worker_wage import worker_payload
from backend.erce.web_bridge import calculate_erce_web_item


class DisabledWorkerWageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "test.sqlite3"
        save_variable_rows(disabled_worker_wage_rows(), self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"] == "2200664"], self.db)

    def payload(self, scenario="share100"):
        return {**worker_payload(scenario), "bill_no": "NEW_DISABLED_WORKER", "evidence_mode": "holdout"}

    def calculate(self, p):
        return calculate_erce_web_item(p, variable_db_path=self.db)

    def test_histories_and_three_shares(self):
        full = self.calculate(self.payload())
        self.assertEqual([t["excluded_worker_count"] for t in full["derivationTrace"]], [9960, 10311, 10675, 11052, 11442])
        self.assertTrue(all(t["monthly_hours"] == 116 for t in full["derivationTrace"]))
        for scenario, share in (("share30", .3), ("share50", .5)):
            r = self.calculate(self.payload(scenario))
            for a, b in zip(full["derivationTrace"], r["derivationTrace"]):
                self.assertAlmostEqual(a["annual_won"] * share, b["annual_won"])

    def test_wages_above_minimum_do_not_create_negative_subsidy(self):
        p = self.payload()
        p["explicit_inputs"] = {"facility_hourly_wage_history": dict(value=dict.fromkeys(map(str, range(2019, 2024)), 30000),
            unit="year_to_KRW/hour", source_ref="합성 최저임금이상 시급 검증")}
        self.assertEqual(self.calculate(p)["annualAmountsThousand"], [0] * 5)

    def test_scope_linked_bill_and_missing_history(self):
        for change in [{"bill_no": "2200664"}, {"disabled_worker_scope": "all_disabled_workers"}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.calculate({**self.payload(), **change})
        r = self.calculate({**self.payload(), "linked_minimum_wage_bill_assumed_passed": False})
        self.assertIn("linked_bill_scope_confirmation", r["missingDerivationVariables"])
        p = self.payload(); p["selected_evidence_keys"] = [k for k in p["selected_evidence_keys"] if "hours_history" not in k]
        self.assertIn("facility_monthly_hours_history", self.calculate(p)["missingDerivationVariables"])
