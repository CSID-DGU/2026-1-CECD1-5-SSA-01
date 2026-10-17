import tempfile
import unittest
from pathlib import Path
from backend.erce.child_support_advance_evidence import child_support_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.scripts.check_delegated_child_support import reviewed_payloads


class DelegatedChildSupportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "test.sqlite3"
        save_variable_rows(child_support_rows(), self.db)
        save_method_rows([r for r in reviewed_method_rows()
                         if r["source_bill_no"] in {"2201707", "2200987"}], self.db)

    def calculate(self, payload):
        return calculate_erce_web_item(payload, variable_db_path=self.db)

    def payload(self):
        return {**reviewed_payloads()[0], "bill_no": "SIMILAR_DELEGATED_ADVANCE", "evidence_mode": "holdout"}

    def test_approved_scenario_reuses_existing_formula_and_keeps_notes(self):
        result = self.calculate(self.payload())
        self.assertEqual(result["status"], "computed_review")
        self.assertAlmostEqual(sum(result["annualAmountsThousand"]) / 100000, 3216.806)
        self.assertTrue(result["derivationTrace"][0]["reference_scenario_confirmed"])
        self.assertIn("소득기준", result["derivationTrace"][0]["delegated_eligibility_note"])

    def test_missing_approval_or_explanation_does_not_compute(self):
        for change in [{"reference_scenario_confirmed": False}, {"reference_scenario_confirmed": "true"},
                       {"delegated_eligibility_note": ""}, {"claim_amount_difference_note": ""},
                       {"reference_scenario_source": ""}, {"legacy_transition_note": ""}]:
            with self.subTest(change=change):
                result = self.calculate({**self.payload(), **change})
                self.assertEqual(result["status"], "needs_input")
                self.assertIn("delegated_policy_reference_confirmation", result["missingDerivationVariables"])

    def test_own_source_excluded_and_confirmed_price_has_priority(self):
        with self.assertRaises(ValueError):
            self.calculate({**self.payload(), "bill_no": "2200987"})
        p = self.payload()
        p["explicit_inputs"] = {"advance_monthly_amount": dict(value=300000, unit="KRW/person/month",
                                                              source_ref="확인된 적용 지급액")}
        result = self.calculate(p)
        self.assertEqual(result["derivationTrace"][0]["gross_expense"], 27056 * 300000 * 12)

    def test_existing_system_calculation_unchanged(self):
        result = self.calculate(reviewed_payloads()[1])
        self.assertEqual(result["annualAmountsThousand"], [948000, 0, 142200, 145186, 148090])
