import unittest
from backend.erce.evaluation_scope_status import scope_status
from backend.erce.scripts.check_activity_accounting_scope import run_review


class EvaluationScopeTests(unittest.TestCase):
    def test_zero_subtotal_error_never_implies_whole_completion(self):
        items=[dict(key="survey",status="estimated",source_ref="확인된계약"),
               dict(key="admin",status="needs_review",source_ref="원문행정조항")]
        r=scope_status(items,covered_amount_thousand=180000,covered_error_percent=0)
        self.assertFalse(r["whole_numeric_complete"])
        self.assertEqual(r["overall_status"],"partial_pending_review")
        self.assertIsNone(r["whole_bill_error_percent"]);self.assertIsNone(r["whole_bill_amount_thousand"])

    def test_all_decisions_known_but_non_estimated_amount_stays_unknown(self):
        r=scope_status([dict(key="pay",status="grounded_non_estimation",source_ref="조건확인근거")],
                       covered_amount_thousand=0,covered_error_percent=0)
        self.assertTrue(r["scope_review_complete"]);self.assertFalse(r["whole_numeric_complete"])
        self.assertEqual(r["overall_status"],"scope_review_complete_partial_estimate")
        r=scope_status([dict(key="cost",status="estimated",source_ref="확인된견적")])
        self.assertFalse(r["whole_numeric_complete"])

    def test_citation_fixed_without_mutating_first_run_and_pending_costs_visible(self):
        r=run_review()
        self.assertEqual(r["original_quote_verified"],[True,True,False])
        self.assertEqual(r["corrected_quote_verified"],[True,True,True])
        self.assertEqual(r["completion"]["pending_scope_keys"],
            ["accounting_system_implementation","supervision_administration","penalty_revenue"])
        self.assertEqual(r["completion"]["covered_error_percent"],0)
        self.assertIsNone(r["completion"]["whole_bill_amount_thousand"])
