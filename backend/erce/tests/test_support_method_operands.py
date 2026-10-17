import tempfile
import unittest
from pathlib import Path

from backend.erce.engine import estimate_routed_item
from backend.erce.scripts.check_support_method_operands import payload_for
from backend.erce.support_method_operands import prepare_support_operands, support_operand_rows
from backend.erce.variable_evidence_store import save_variable_rows, find_variable_candidates
from backend.erce.web_bridge import calculate_erce_web_item


class SupportOperandsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name)/"reference.sqlite3"
        save_variable_rows(support_operand_rows(),self.db)

    def payload(self,bill,profile,**kwargs):
        return {**payload_for(bill,profile,**kwargs),"variable_db_path":str(self.db)}

    def test_three_cases_run_and_split_does_not_double_total(self):
        for bill,profile in [("2209405","student_tuition_interest"),
                ("2215813","graduate_fee_compensation"),("2214218","association_operating_support")]:
            p = self.payload(bill,profile,group="public" if bill=="2215813" else None)
            self.assertEqual(len(estimate_routed_item(p).annual_amounts_thousand),5)
        p = self.payload("2214218","association_operating_support")
        self.assertEqual(estimate_routed_item(p).annual_amounts_thousand,(754000,)*5)
        p = self.payload("2214218","association_operating_support",fiscal_scope="national")
        self.assertEqual(estimate_routed_item(p).annual_amounts_thousand,(377000,)*5)

    def test_self_answer_still_blocked(self):
        p = self.payload("2209405","student_tuition_interest")
        with self.assertRaisesRegex(ValueError,"target answer"):
            estimate_routed_item({**p,"evidence_mode":"holdout"})

    def test_wrong_type_rate_and_projection_rejected(self):
        p = self.payload("2215813","graduate_fee_compensation",group="private_graduate")
        with self.assertRaisesRegex(ValueError,"university_kind mismatch"):
            estimate_routed_item({**p,"university_kind":"public"})
        p = self.payload("2209405","student_tuition_interest")
        with self.assertRaisesRegex(ValueError,"year mismatch"):
            estimate_routed_item({**p,"start_year":2027})
        p = {"route_key":"transfer_recipient","support_derivation":"student_tuition_interest",
             "support_derivation_note":"confirmed","years":5,"explicit_inputs":{
             "student_loan_rate":dict(value=2,unit="ratio",source_ref="test")}}
        with self.assertRaisesRegex(ValueError,"invalid support operand"):
            prepare_support_operands(p)

    def test_explicit_top_slot_wins(self):
        p = self.payload("2214218","association_operating_support")
        p["explicit_inputs"]={"project_cost":dict(value=1000000,unit="KRW/year",source_ref="법안명시")}
        self.assertEqual(estimate_routed_item(p).annual_amounts_thousand,(1000,)*5)

    def test_missing_stays_missing_and_no_confirmation_no_derive(self):
        p = dict(route_key="transfer_subsidy_rate",years=5,support_derivation="association_operating_support",
                 support_derivation_note="confirmed")
        self.assertEqual(prepare_support_operands(p)["support_missing_operands"],
            ["association_count","association_annual_unit","government_share"])
        with self.assertRaisesRegex(ValueError,"applicability note"):
            prepare_support_operands({**p,"support_derivation_note":""})

    def test_web_reuse_with_new_explicit_quantity(self):
        p = self.payload("2214218","association_operating_support")
        p["bill_no"]="NEW_ASSOCIATION"
        p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if ":association_count:" not in k]
        p["explicit_inputs"]={"association_count":dict(value=10,unit="organization",source_ref="신규 법안")}
        r = calculate_erce_web_item(p,variable_db_path=self.db)
        self.assertEqual(r["annualAmountsThousand"],[260000]*5)
        self.assertTrue(r["derivationTrace"])
        del p["explicit_inputs"]["association_count"]
        r = calculate_erce_web_item(p,variable_db_path=self.db)
        self.assertEqual(r["status"],"needs_input")
        self.assertIn("association_count",r["missingDerivationVariables"])

    def test_target_quantities_not_reusable(self):
        candidates=find_variable_candidates(cutoff_date="2026-10-03",target_bill_no="NEW",
            variable_key="fee_paying_entrants",db_path=self.db)
        self.assertEqual(candidates,[])

    def test_no_unnecessary_questions_when_top_value_already_known(self):
        p = dict(route_key="transfer_recipient",support_derivation="student_tuition_interest",
            support_derivation_note="confirmed",explicit_inputs={
                "recipient_count":dict(value=10,unit="person",source_ref="법안"),
                "benefit_per_recipient":dict(value=1000,unit="KRW/person/year",source_ref="법안")})
        self.assertEqual(prepare_support_operands(p)["support_missing_operands"],[])
