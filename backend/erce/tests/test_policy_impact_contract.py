import tempfile
import unittest
from pathlib import Path
from backend.erce.policy_impact_research_evidence import policy_impact_research_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_policy_impact_contract import impact_payload
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.route_tree import route_for_path


class PolicyImpactContractTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "test.sqlite3"
        save_variable_rows(policy_impact_research_rows(), self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"] == "2201364"], self.db)

    def payload(self):
        return {**impact_payload(), "bill_no": "NEW_ANNUAL_POLICY_IMPACT", "evidence_mode": "holdout"}

    def calculate(self, p):
        return calculate_erce_web_item(p, variable_db_path=self.db)

    def test_leaf_and_annual_package_amount(self):
        self.assertEqual(route_for_path(["물건비", "평가사업", "정책영향평가", "연간연구용역패키지"]), "policy_impact_annual_contract")
        r = self.calculate(self.payload())
        self.assertEqual(r["annualAmountsThousand"], [200000] * 5)
        p = self.payload()
        p["explicit_inputs"] = {"service_unit_cost": dict(value=300000000, unit="KRW/contract", source_ref="확정 신규계약 견적")}
        self.assertEqual(self.calculate(p)["annualAmountsThousand"], [300000] * 5)

    def test_wrong_task_self_and_missing_confirmation_rejected(self):
        for change in [{"bill_no": "2201364"}, {"research_service_function": "social_worker_rights_violence_survey"},
                       {"route_key": "quantity_unit"}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.calculate({**self.payload(), **change})
        p = self.payload()
        p["method_confirmations"] = {"2201364:annual_policy_impact_contract": {}}
        with self.assertRaises(ValueError):
            self.calculate(p)

    def test_missing_budget_not_imputed(self):
        p = self.payload()
        p["selected_evidence_keys"] = [k for k in p["selected_evidence_keys"] if "service_unit_cost" not in k]
        r = self.calculate(p)
        self.assertEqual(r["status"], "needs_input")
        self.assertIn("service_unit_cost", r["missingVariables"])
