import tempfile
import unittest
from pathlib import Path
from backend.erce.disabled_child_allowance_evidence import disabled_child_allowance_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_disabled_child_allowance import child_allowance_payload
from backend.erce.web_bridge import calculate_erce_web_item


class DisabledChildAllowanceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "test.sqlite3"
        save_variable_rows(disabled_child_allowance_rows(), self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"] == "2205274"], self.db)

    def payload(self):
        return {**child_allowance_payload(), "bill_no": "NEW_CHILD_ALLOWANCE_MANDATORY", "evidence_mode": "holdout"}

    def calculate(self, p):
        return calculate_erce_web_item(p, variable_db_path=self.db)

    def test_group_deltas_and_exact_amount(self):
        r = self.calculate(self.payload())
        self.assertEqual(r["annualAmountsThousand"], [465000] * 5)
        t = r["derivationTrace"][0]
        self.assertEqual(t["new_recipients_by_group"], dict(severe_home=80, severe_facility=10, mild_home=174, mild_facility=37))
        self.assertEqual(t["additional_recipients"], 301)

    def test_confirmed_recipients_priority_and_no_duplicate_payments(self):
        p = self.payload()
        p["explicit_inputs"] = {"child_allowance_current_by_group": dict(value=dict(severe_home=3999, severe_facility=1028, mild_home=4583, mild_facility=1005),
            unit="group_to_person", source_ref="확인된 전원기존수급 시나리오")}
        self.assertEqual(self.calculate(p)["annualAmountsThousand"], [0] * 5)
        p["explicit_inputs"]["child_allowance_current_by_group"]["value"]["severe_home"] = 4000
        with self.assertRaises(ValueError):
            self.calculate(p)

    def test_scope_approval_and_missing_group_data(self):
        for change in [{"bill_no": "2205274"}, {"disability_child_scope": "adult_disability_allowance"}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.calculate({**self.payload(), **change})
        r = self.calculate({**self.payload(), "child_allowance_scenario_confirmed": False})
        self.assertIn("child_allowance_delta_confirmation", r["missingDerivationVariables"])
        p = self.payload(); p["selected_evidence_keys"] = [k for k in p["selected_evidence_keys"] if "current_by_group" not in k]
        self.assertIn("child_allowance_current_by_group", self.calculate(p)["missingDerivationVariables"])
