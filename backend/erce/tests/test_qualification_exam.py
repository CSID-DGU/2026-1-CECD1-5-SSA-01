import tempfile
import unittest
from pathlib import Path
from backend.erce.qualification_exam_evidence import qualification_exam_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_qualification_exam import exam_payload,run_regression
from backend.erce.web_bridge import calculate_erce_web_item


class QualificationExamTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.db=Path(temp.name)/"test.sqlite3"
        save_variable_rows(qualification_exam_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2207043"],self.db)

    def supplied(self):
        p={**exam_payload(False),"bill_no":"NEW_TEST_EXAM","evidence_mode":"holdout"}
        p["explicit_inputs"]={**p["explicit_inputs"],"service_provider_forecast":dict(value={
            "2027":36188,"2028":37236,"2029":38161,"2030":38988,"2031":39736},
            unit="year_to_person",source_ref="공급인원입력 인터페이스시험.정답표사용한합성입력")}
        return p

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_self_regression_display_and_stock_flow_retake(self):
        r=run_regression(self.db)
        self.assertEqual(r["annual_display_matches"],5)
        self.assertEqual(r["displayed_total_million"],5893)
        self.assertGreater(r["raw_error_percent"],0)
        self.assertLess(r["raw_error_percent"],.03)
        trace=r["explicit_projection_web_result"]["derivationTrace"]
        self.assertEqual([t["total_candidates"] for t in trace],[18564,1048,925,827,1013])
        self.assertEqual([t["retake_candidates"] for t in trace],[0,0,0,0,265])
        self.assertEqual([t["exam_type"] for t in trace],["special"]*3+["regular"]*2)

    def test_target_projection_does_not_become_comparable_population(self):
        p={**exam_payload(False),"bill_no":"NEW_TEST_EXAM","evidence_mode":"holdout"}
        self.assertIn("service_provider_forecast",self.calculate(p)["missingDerivationVariables"])
        with self.assertRaises(ValueError):
            self.calculate({**exam_payload(),"bill_no":"NEW_TEST_EXAM"})

    def test_real_linked_dependency_and_transition_assumptions_required(self):
        p=self.supplied()
        self.assertIn("exam_linked_bill_confirmation",self.calculate({**p,"exam_linked_bill_assumed_passed":False})["missingDerivationVariables"])
        self.assertIn("exam_special_pass_assumption",self.calculate({**p,"exam_special_all_pass_assumed":False})["missingDerivationVariables"])

    def test_new_policy_shares_override_and_no_three_type_multiplier(self):
        p=self.supplied();normal=self.calculate(p)
        p["explicit_inputs"]["exam_initial_unlicensed_share"]=dict(value=.25,unit="ratio",source_ref="합성신규정책미자격25%")
        r=self.calculate(p)
        self.assertEqual(r["derivationTrace"][0]["total_candidates"],9047)
        self.assertEqual(r["annualAmountsThousand"][1:],normal["annualAmountsThousand"][1:])
        p["explicit_inputs"]["exam_regular_failure_share"]=dict(value=.5,unit="ratio",source_ref="합성정규시험실패50%")
        r=self.calculate(p)
        self.assertEqual(r["derivationTrace"][4]["retake_candidates"],414)
