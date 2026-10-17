import base64
import json
import tempfile
import unittest
from pathlib import Path

import fitz

from backend.erce.ai_pdf_analysis import analyze_erce_pdf
from backend.erce.engine import estimate_routed_item
from backend.erce.scripts.check_capital_student_interest import reviewed_payload
from backend.erce.support_method_operands import support_operand_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.web_bridge import calculate_erce_web_item


class CapitalStudentInterestTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"references.sqlite3"
        save_variable_rows(support_operand_rows(),self.db)

    def payload(self,band=7):
        return {**reviewed_payload(band),"variable_db_path":str(self.db)}

    def test_scope_period_confirmation_and_self_guards(self):
        for p,message in [({**self.payload(),"loan_income_band":"8"},"loan_income_band mismatch"),
                ({**self.payload(),"student_loan_region":"noncapital"},"student_loan_region mismatch"),
                ({**self.payload(),"start_year":2026},"year mismatch"),
                ({**self.payload(),"evidence_mode":"holdout"},"target answer"),
                ({**self.payload(),"estimation_start_note":""},"start needs a separate basis"),
                ({**self.payload(),"student_interest_scope_note":""},"scope confirmation")]:
            with self.subTest(message=message),self.assertRaisesRegex(ValueError,message):
                estimate_routed_item(p)

    def test_both_bands_reproduce_at_answer_precision(self):
        estimates=[estimate_routed_item(self.payload(b)) for b in (7,8)]
        annual=[sum(e.annual_amounts_thousand[i] for e in estimates) for i in range(5)]
        self.assertLess(abs(sum(annual)-54116000)/54116000,.001)
        self.assertEqual(estimates[0].resolved_variables["benefit_per_recipient"].source_class,"calculated_estimate")

    def test_new_bill_can_reuse_rate_balance_but_not_target_population(self):
        p=self.payload()
        p["bill_no"]="NEW_CAPITAL_BAND7"
        p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if ":eligible_loan_students:" not in k]
        p["explicit_inputs"]={"eligible_loan_students":dict(value=100,unit="person",source_ref="신규 법안 명시")}
        result=calculate_erce_web_item(p,variable_db_path=self.db)
        self.assertEqual(result["status"],"computed_review")
        self.assertEqual(result["annualAmountsThousand"][0],6866)
        self.assertTrue(result["derivationTrace"])
        p["start_year"]=None
        result=calculate_erce_web_item(p,variable_db_path=self.db)
        self.assertEqual(result["status"],"needs_input")
        self.assertIn("start_year",result["missingVariables"])

    def test_effective_year_is_not_automatically_forecast_start(self):
        with fitz.open() as pdf:
            page=pdf.new_page()
            page.insert_text((50,50),"Article 1 effective 2026-11-20")
            encoded=base64.b64encode(pdf.tobytes()).decode()
        # English quote uses the explicit effective_year key; the extraction
        # rule also handles legacy Korean 시행일 start_year drafts.
        draft=dict(bill_no="NEW",bill_name="test",document_type="amendment",articles=[dict(
            article_ref="Article 1",source_quote="Article 1 effective 2026-11-20",source_page=1,
            cost_trigger=True,estimation_decision="estimate_now",decision_reason="new interest",
            route_key="transfer_recipient",route_reason="count times interest",variables=[dict(
                key="effective_year",value_json="2026",unit="year",source_quote="effective 2026-11-20",source_page=1)])])
        result=analyze_erce_pdf("test.pdf",encoded,ai_draft=draft)
        item=result["erce"]["items"][0]
        self.assertEqual(item["effectiveYear"],2026)
        self.assertIsNone(item["startYear"])
        self.assertTrue(item["timingNeedsConfirmation"])
