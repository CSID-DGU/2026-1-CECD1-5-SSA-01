import tempfile
import unittest
from pathlib import Path
from backend.erce.medical_communication_evidence import medical_communication_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_medical_communication import communication_payload
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.engine import estimate_routed_item


class MedicalCommunicationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "test.sqlite3"
        save_variable_rows(medical_communication_rows(), self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"] == "2203688"], self.db)

    def annual_payload(self):
        return {**communication_payload("official_annual_package"), "bill_no": "NEW_HOSPITAL_PACKAGE", "evidence_mode": "holdout"}

    def calculate(self, p):
        return calculate_erce_web_item(p, variable_db_path=self.db)

    def test_annual_unit_not_multiplied_by_twelve_and_overlap_removed(self):
        r = self.calculate(self.annual_payload())
        self.assertEqual(r["annualAmountsThousand"], [6660000] * 5)
        self.assertEqual(r["derivationTrace"][0]["eligible_hospitals"], 37)
        p = self.annual_payload()
        p["explicit_inputs"] = {"tertiary_hospital_count": dict(value=48, unit="hospital", source_ref="확인된신규기관수")}
        self.assertEqual(self.calculate(p)["annualAmountsThousand"], [6840000] * 5)

    def test_disputed_monthly_price_only_own_engine_replay(self):
        p = {**communication_payload(), "variable_db_path": str(self.db)}
        r = estimate_routed_item(p)
        self.assertAlmostEqual(sum(r.annual_amounts_thousand) / 100000, 4488.25075)
        with self.assertRaises(ValueError):
            self.calculate(communication_payload())
        with self.assertRaises(ValueError):
            self.calculate({**communication_payload(), "bill_no": "NEW_HOSPITAL_PACKAGE"})

    def test_scope_subsidy_and_approval_guards(self):
        r = self.calculate({**self.annual_payload(), "communication_scenario_confirmed": False})
        self.assertIn("communication_scenario_confirmation", r["missingDerivationVariables"])
        with self.assertRaises(ValueError):
            self.calculate({**self.annual_payload(), "fiscal_scope": "national_only"})
        p = self.annual_payload()
        p["explicit_inputs"] = {"already_supported_hospital_count": dict(value=50, unit="hospital", source_ref="잘못된겹침검증")}
        with self.assertRaises(ValueError):
            self.calculate(p)
        p = self.annual_payload()
        p["explicit_inputs"] = {"communication_staff_per_hospital": dict(value=4, unit="person/hospital", source_ref="변경배치범위")}
        with self.assertRaises(ValueError):
            self.calculate(p)
