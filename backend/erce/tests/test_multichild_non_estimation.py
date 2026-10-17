import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

from backend.erce.ai_pdf_analysis import analyze_erce_pdf
from backend.erce.draft_report import generate_draft
from backend.erce.method_evidence_store import find_method_candidates,save_method_rows,validate_non_estimation_review
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.variable_evidence_store import save_variable_rows

KEY="2208749:multichild_delegated_allowance_not_estimated"


def confirmed_review():
    return dict(decision_evidence_key=KEY,reliable_estimation_basis_available=False,
        decision_confirmations={"household_child_scope":"합성검증: 미성년자녀2명이상가구의아동,첫째도가능",
            "population_basis_review":"합성검증: 가구별아동통계·적용가능한준용근거부족 확인;단순DB빈값이아님",
            "delegated_payment_review":"합성검증: 자녀수별월액이위임되고상한만명시,확정시행령·확인받은시나리오없음"},
        decision_facts={"multiple_minor_children_household":True,"reliable_household_child_basis_available":False,
            "payment_delegated":True,"payment_amount_confirmed":False})


class MultichildNonEstimationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/"refs.sqlite3";save_variable_rows([],self.db)
        row=next(r for r in reviewed_method_rows() if r["method_key"]==KEY)
        save_method_rows([row],self.db)

    def payload(self):
        return {**confirmed_review(),"bill_no":"NEW_MULTICHILD","cutoff_date":"2026-10-04"}

    def test_both_source_reasons_and_unknown_amount(self):
        r=validate_non_estimation_review(self.payload(),db_path=self.db)
        self.assertEqual(r["decision"],"not_estimated");self.assertIsNone(r["amount"])
        self.assertIn("대통령령",r["additional_source_quote"])
        self.assertIn("대상아동",r["reason"]);self.assertTrue(r["reestimate_when"])

    def test_scope_price_or_population_resolved_blocks_this_reason(self):
        for key,value in (("multiple_minor_children_household",False),
                          ("reliable_household_child_basis_available",True),
                          ("payment_delegated",False),("payment_amount_confirmed",True)):
            p=self.payload();p["decision_facts"][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,"fact mismatch"):
                validate_non_estimation_review(p,db_path=self.db)
        p=self.payload();p.pop("decision_facts")
        with self.assertRaises(ValueError):validate_non_estimation_review(p,db_path=self.db)

    def test_source_cutoff_self_family_and_exclusion(self):
        for changes in ({"bill_no":"2208749"},{"cutoff_date":"2025-04-27"},
                        {"target_family_key":"multichild_household_delegated_allowance"},
                        {"excluded_bill_nos":["2208749"]}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                validate_non_estimation_review({**self.payload(),**changes},db_path=self.db)

    def test_search_not_ordinary_birth_order_payment(self):
        self.assertEqual(len(find_method_candidates(query="아동수당2명이상추가지급대통령령",cutoff_date="2026-10-04",db_path=self.db)),1)
        self.assertEqual(find_method_candidates(query="아동수당둘째15만원셋째20만원",cutoff_date="2026-10-04",db_path=self.db),[])

    def analyze(self,review):
        pdf=fitz.open();pdf.new_page().insert_text((40,40),"2026-10-04\nchild allowance: additional payment for two children, delegated.")
        encoded=base64.b64encode(pdf.tobytes()).decode();pdf.close()
        article=dict(article_ref="Section 1",change_summary="child allowance two children additional delegated",
            source_quote="child allowance: additional payment for two children, delegated.",source_page=1,
            cost_trigger=True,estimation_decision="defer",decision_reason="Await review",route_key="transfer_recipient",variables=[])
        if review is not None:article["non_estimation_review"]=review
        from backend.erce import method_evidence_store as store
        search=store.find_method_candidates;validate=store.validate_non_estimation_review
        with patch.object(store,"find_method_candidates",side_effect=lambda **kw:search(**kw,db_path=self.db)),\
             patch.object(store,"validate_non_estimation_review",side_effect=lambda p:validate(p,db_path=self.db)):
            return analyze_erce_pdf("synthetic.pdf",encoded,ai_draft=dict(bill_no="NEW_MULTICHILD",propose_date="2026-10-04",articles=[article]))

    def test_analysis_candidate_is_not_auto_decision_but_confirmed_review_is(self):
        unconfirmed=self.analyze(None)
        self.assertEqual(unconfirmed["articles"][0]["estimation_decision"],"defer")
        self.assertTrue(unconfirmed["articles"][0]["non_estimation_candidates"])
        confirmed=self.analyze(confirmed_review())
        self.assertEqual(confirmed["articles"][0]["estimation_decision"],"not_estimated")
        self.assertIsNone(confirmed["articles"][0]["non_estimation_review"]["amount"])

    def test_draft_only_non_estimated_never_zero(self):
        from backend.erce import method_evidence_store as store
        validate=store.validate_non_estimation_review
        with patch.object(store,"validate_non_estimation_review",side_effect=lambda p:validate(p,db_path=self.db)):
            r=generate_draft(dict(bill_no="NEW_MULTICHILD",cutoff_date="2026-10-04",start_year=2026,years=5,
                items=[],non_estimation_items=[{**confirmed_review(),"name":"추가급여"}]))
        self.assertEqual(r["status"],"not_estimated");self.assertIsNone(r["totalThousand"])
        self.assertIn("25C1367",r["markdown"]);self.assertIn("재추계",r["markdown"])
