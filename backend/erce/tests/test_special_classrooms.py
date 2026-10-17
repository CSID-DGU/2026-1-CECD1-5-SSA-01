import tempfile
import unittest
from pathlib import Path
from backend.erce.special_classroom_evidence import special_classroom_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows,validate_non_estimation_review
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_special_classrooms import classroom_payload,teacher_review,run_regression
from backend.erce.web_bridge import calculate_erce_web_item


class SpecialClassroomTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.db=Path(temp.name)/"test.sqlite3"
        save_variable_rows(special_classroom_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2205721"],self.db)

    def web(self,**updates):
        return calculate_erce_web_item({**classroom_payload(),"bill_no":"NEW_SPECIAL_CLASSROOMS","evidence_mode":"holdout",**updates},variable_db_path=self.db)

    def test_class_counts_prices_and_high_school_zero(self):
        r=run_regression(self.db)
        self.assertEqual(r["annual_display_matches"],5)
        self.assertLess(r["error_percent"],.001)
        trace=r["web_result"]["derivationTrace"]
        self.assertEqual([t["new_classes"] for t in trace],[2356,726,768,810,859])
        self.assertTrue(all(g["new_classes"]==0 for t in trace for g in t["groups"] if g["stage"]=="high"))
        self.assertEqual(r["web_result"]["estimatePurpose"],"reference_scenario")

    def test_unapproved_inferred_precision_and_index_bridge_blocked(self):
        for update,missing in ((dict(price_index_bridge_confirmed=False),"price_index_vintage_confirmation"),
                               (dict(class_precision_assumption_confirmed=False),"class_rounding_confirmation")):
            self.assertIn(missing,self.web(**update)["missingDerivationVariables"])
        with self.assertRaises(ValueError):
            self.web(estimate_purpose="official_estimate")

    def test_annual_installations_do_not_repeat_first_year_gap(self):
        trace=self.web()["derivationTrace"]
        for before,after in zip(trace,trace[1:]):
            for g in after["groups"]:
                prev=next(x for x in before["groups"] if (x["stage"],x["school_group"])==(g["stage"],g["school_group"]))
                self.assertEqual(g["installed_before"],prev["installed_after"])
        p=classroom_payload("consistent_2024_vintage","strict_ceiling")
        r=calculate_erce_web_item({**p,"bill_no":"STRICT_NEW_CLASSROOMS"},variable_db_path=self.db)
        self.assertEqual([t["new_classes"] for t in r["derivationTrace"]],[2356,726,768,811,858])

    def test_missing_history_and_law_explicit_caps_priority(self):
        keys=[k for k in classroom_payload()["selected_evidence_keys"] if "student_history" not in k]
        self.assertIn("special_student_history",self.web(selected_evidence_keys=keys)["missingDerivationVariables"])
        r=self.web(explicit_inputs={"special_new_class_caps":dict(value=dict(elementary=3,high=6),unit="stage_to_person/class",source_ref="합성 새의안초등3명기준")})
        self.assertGreater(r["derivationTrace"][0]["new_classes"],2356)

    def test_teacher_uncertainty_not_zero_and_self_source_excluded(self):
        p={**teacher_review(),"bill_no":"NEW_SPECIAL_CLASSROOMS","evidence_mode":"holdout"}
        r=validate_non_estimation_review(p,db_path=self.db)
        self.assertEqual(r["decision"],"not_estimated");self.assertIsNone(r["amount"])
        p["decision_facts"]["teacher_increment_confirmed"]=True
        with self.assertRaises(ValueError):
            validate_non_estimation_review(p,db_path=self.db)
        with self.assertRaises(ValueError):
            calculate_erce_web_item(classroom_payload(),variable_db_path=self.db)
