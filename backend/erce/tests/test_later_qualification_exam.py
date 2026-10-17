import tempfile
import unittest
from pathlib import Path
from backend.erce.qualification_exam_evidence import qualification_exam_rows, later_qualification_exam_projection_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows, validate_non_estimation_review, find_method_candidates
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_later_qualification_exam import later_exam_payload, association_payload, run_regression
from backend.erce.web_bridge import calculate_erce_web_item


class LaterQualificationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name)/"test.sqlite3"
        save_variable_rows(qualification_exam_rows()+later_qualification_exam_projection_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2210347"],self.db)

    def test_exam_and_positive_existing_association_review(self):
        r = run_regression(self.db)
        self.assertEqual(r["annual_display_matches"],5)
        self.assertEqual(r["association_review"]["decision"],"no_incremental_cost")
        self.assertIsNone(r["association_review"]["amount"])
        self.assertFalse(r["independent_evaluation"])
        self.assertIn("service_provider_forecast",r["new_bill_missing_projection_result"]["missingDerivationVariables"])

    def test_target_projection_not_transferable(self):
        p = {**later_exam_payload(),"bill_no":"NEW_EXAM"}
        with self.assertRaises(ValueError):
            calculate_erce_web_item(p,variable_db_path=self.db)

    def test_expanded_association_not_automatically_excluded(self):
        p = association_payload()
        p["decision_facts"] = {**p["decision_facts"],"new_scope_or_public_funding_confirmed":True}
        with self.assertRaises(ValueError):
            validate_non_estimation_review(p,db_path=self.db)

    def test_router_candidate_for_three_year_transition(self):
        rows = find_method_candidates(query="발달재활사 국가시험 자격증 특례시험 3년 경과조치",
            cutoff_date="2026-10-12",target_bill_no="NEW_EXAM",db_path=self.db)
        self.assertTrue(any(r["method_key"]=="2210347:qualification_exam_stock_flow" for r in rows))
