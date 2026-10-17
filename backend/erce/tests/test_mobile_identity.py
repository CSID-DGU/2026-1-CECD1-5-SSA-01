import tempfile
import unittest
from pathlib import Path
from backend.erce.mobile_identity_evidence import mobile_identity_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_mobile_identity import mobile_payload
from backend.erce.web_bridge import calculate_erce_web_item


class MobileIdentityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "test.sqlite3"
        save_variable_rows(mobile_identity_rows(), self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"] == "2205097"], self.db)

    def payload(self):
        return {**mobile_payload(), "bill_no": "NEW_MOBILE_ID", "evidence_mode": "holdout"}

    def calculate(self, p):
        return calculate_erce_web_item(p, variable_db_path=self.db)

    def test_lifecycle_warranty_and_component_display(self):
        r = self.calculate(self.payload()); t = r["derivationTrace"]
        self.assertEqual(r["annualAmountsThousand"], [6778000, 893460, 1165021, 1188321, 1212088])
        self.assertEqual(t[0]["operation_won"], 0)
        self.assertGreater(t[1]["operation_won"], 0)
        self.assertEqual(t[1]["maintenance_won"], 0)
        self.assertGreater(t[2]["maintenance_won"], 0)
        displayed = [sum(round(row[k] / 1000000) for k in ("build_won", "operation_won", "maintenance_won")) for row in t]
        self.assertEqual(displayed, [6778, 893, 1165, 1189, 1212])

    def test_scope_missing_price_and_own_source(self):
        r = self.calculate({**self.payload(), "mobile_plan_scope_confirmed": False})
        self.assertIn("mobile_identity_scope_confirmation", r["missingDerivationVariables"])
        p = self.payload(); p["selected_evidence_keys"] = [k for k in p["selected_evidence_keys"] if "maintenance_base" not in k]
        self.assertIn("mobile_maintenance_base", self.calculate(p)["missingDerivationVariables"])
        with self.assertRaises(ValueError):
            self.calculate({**self.payload(), "bill_no": "2205097"})

    def test_confirmed_component_override_and_no_duplicate_rate(self):
        p = self.payload()
        p["explicit_inputs"] = {"mobile_build_components": dict(value={"new_quote": 100000000}, unit="component_to_KRW", source_ref="확정된 동일과업 신규구축견적")}
        r = self.calculate(p)
        self.assertEqual(r["annualAmountsThousand"][0], 100000)
        p["explicit_inputs"]["system_maintenance_rate"] = dict(value=.15, unit="ratio/year", source_ref="중복유지관리율 검증")
        with self.assertRaises(ValueError):
            self.calculate(p)
