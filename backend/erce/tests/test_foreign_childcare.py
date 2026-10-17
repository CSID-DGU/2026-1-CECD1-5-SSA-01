import tempfile
import unittest
from pathlib import Path
from backend.erce.foreign_childcare_evidence import foreign_childcare_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows, validate_non_estimation_review
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_foreign_childcare import fee_payload, non_estimation_payload
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


class ForeignChildcareTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "test.sqlite3"
        save_variable_rows(foreign_childcare_rows(), self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"] == "2201907"], self.db)

    def generic(self):
        return {**fee_payload("stock_share"), "bill_no": "NEW_FOREIGN_CHILDCARE", "evidence_mode": "holdout"}

    def calculate(self, payload):
        return calculate_erce_web_item(payload, variable_db_path=self.db)

    def test_reusable_pipeline_requests_real_individual_age_base(self):
        r = self.calculate(self.generic())
        self.assertEqual(r["status"], "needs_input")
        self.assertEqual(r["missingDerivationVariables"], ["foreign_base_counts_by_age"])
        p = self.generic()
        p["explicit_inputs"] = {"foreign_base_counts_by_age": dict(value=dict.fromkeys(map(str, range(4)), 100),
            unit="age_to_person", source_ref="합성 각세 기준실적 검증자료, 실제 통계 아님")}
        r = self.calculate(p)
        self.assertEqual(r["status"], "computed_review")
        t = r["derivationTrace"][0]
        self.assertAlmostEqual(t["national_won"] + t["local_won"], t["expenditure_won"])
        self.assertEqual(t["count_basis"], "stock_share")

    def test_target_forecast_not_reusable_or_allowed_by_web(self):
        p = {**fee_payload(), "variable_db_path": str(self.db)}
        r = estimate_routed_item(p)
        self.assertAlmostEqual(sum(r.annual_amounts_thousand) / 100000, 3827.7868)
        with self.assertRaises(ValueError):
            self.calculate(fee_payload())
        with self.assertRaises(ValueError):
            self.calculate({**fee_payload(), "bill_no": "NEW_FOREIGN_CHILDCARE"})

    def test_wrong_age_band_and_missing_confirmation_rejected(self):
        p = self.generic()
        p["explicit_inputs"] = {"foreign_base_counts_by_age": dict(value={"0~4": 32400},
            unit="age_to_person", source_ref="공식5세묶음을 각세로 임의분해하지 않는 검증")}
        with self.assertRaises(ValueError):
            self.calculate(p)
        r = self.calculate({**self.generic(), "foreign_scope_confirmed": False})
        self.assertIn("foreign_parent_fee_confirmation", r["missingDerivationVariables"])

    def test_non_estimation_is_reasoned_and_not_zero(self):
        p = {**non_estimation_payload("home"), "bill_no": "NEW_FOREIGN_CHILDCARE", "evidence_mode": "holdout"}
        r = validate_non_estimation_review(p, db_path=self.db)
        self.assertEqual(r["decision"], "not_estimated")
        self.assertIsNone(r["amount"])
        p["decision_facts"]["institution_nonuse_basis_available"] = True
        with self.assertRaises(ValueError):
            validate_non_estimation_review(p, db_path=self.db)
