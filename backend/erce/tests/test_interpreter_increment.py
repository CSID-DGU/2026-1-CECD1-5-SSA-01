import tempfile
import unittest
from pathlib import Path
from backend.erce.hospital_interpreter_increment import interpreter_increment_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_interpreter_increment import interpreter_payload, run_regression
from backend.erce.web_bridge import calculate_erce_web_item


class InterpreterIncrementTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "test.sqlite3"
        save_variable_rows(interpreter_increment_rows(), self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"] == "2205811"], self.db)

    def web(self, route="personnel_average", **updates):
        p = {**interpreter_payload(route), "bill_no": "NEW_NATIONAL_HOSPITAL", "evidence_mode": "holdout", **updates}
        return calculate_erce_web_item(p, variable_db_path=self.db)

    def test_gold_display_and_first_year_asset(self):
        r = run_regression(self.db)
        self.assertEqual(r["annual_display_matches"], 5)
        self.assertLess(r["error_percent"], .02)
        self.assertEqual(list(r["components"]["personnel_asset"]["annual_amounts_thousand"][1:]), [0]*4)

    def test_reuse_and_explicit_count_priority(self):
        r = self.web()
        self.assertEqual(r["derivationTrace"][0]["additional_headcount"], 18)
        p = self.web(explicit_inputs={"national_university_hospital_count": dict(value=20, unit="hospital", source_ref="확인된 새 모집단")})
        self.assertEqual(p["derivationTrace"][0]["additional_headcount"], 20)
        self.assertEqual(self.web("personnel_asset")["annualAmountsThousand"][1:], [0]*4)

    def test_increment_requires_confirmation_and_no_overlap_subtraction(self):
        for updates in ({"interpreter_increment_confirmed": False}, {"existing_interpreters_subtracted": True}, {"interpreter_increment_note": ""}):
            self.assertIn("interpreter_increment_confirmation", self.web(**updates)["missingDerivationVariables"])

    def test_missing_price_not_invented_and_own_web_source_excluded(self):
        p = interpreter_payload()
        p["selected_evidence_keys"] = [k for k in p["selected_evidence_keys"] if "salary_2024" not in k]
        r = calculate_erce_web_item({**p, "bill_no": "NEW_HOSPITAL"}, variable_db_path=self.db)
        self.assertIn("interpreter_salary_2024", r["missingDerivationVariables"])
        with self.assertRaises(ValueError):
            calculate_erce_web_item(interpreter_payload(), variable_db_path=self.db)
