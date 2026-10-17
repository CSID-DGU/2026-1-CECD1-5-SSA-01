import base64
import json
from pathlib import Path
import unittest

from backend.erce.ai_pdf_analysis import analyze_erce_pdf
from backend.erce.draft_report import generate_draft
from backend.erce.web_evidence_selection import advance_clause_candidates, evidence_catalog, selected_web_context
from backend.erce.user_messages import user_error

ROOT = Path(__file__).resolve().parents[3]


class WebEvidenceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.catalog = evidence_catalog("양육비 선지급 신청 기존 지원 폐지", "2200703")
        self.method = next(m for m in self.catalog["methods"]
                           if m.get("support_derivation") == "child_support_advance_expense")
        self.selection = {
            "method_key": self.method["method_key"],
            "evidence_keys": self.method["variable_evidence_keys"],
            "applicability_note": "미지급 양육비 선지급 대상 필터가 같은 선례. 전원 신청·월 20만원·12개월·기존 예산 차감·2026~2030은 확인할 참고 가정.",
        }

    def test_pdf_selection_reaches_calculation_and_draft(self):
        # Development AI role, not a paid/model-quality evaluation. The server
        # reads the bill only, never the target cost-estimate PDF.
        recorded = json.loads((ROOT / "docs/erce/first_runs/ERCE_FIRST_RUN_2200703.json").read_text())
        draft = recorded["ai_draft"]
        draft["articles"][0]["evidence_selection"] = self.selection
        content = base64.b64encode((ROOT / "backend/generated/assembly_22_pdfs/by_bill/2200703/bill_text.pdf").read_bytes()).decode()
        result = analyze_erce_pdf("bill_text.pdf", content, ai_draft=draft)
        item = result["erce"]["items"][0]
        self.assertEqual(item["routeKey"], "direct_annual_amount")
        self.assertTrue(item["assumptionConfirmationRequired"])
        self.assertEqual(item["calculation"]["status"], "computed_review")
        self.assertEqual(len(item["calculation"]["evidenceVariables"]), 9)
        report = generate_draft({"bill_name": result["billName"], "start_year": item["startYear"],
            "items": [{**item["engineContext"], "route_key": item["routeKey"], "name": item["name"],
                       "bill_no": "2200703", "trigger_ref": item["triggerRef"]}]})
        self.assertEqual(report["status"], "draft_ready")
        self.assertEqual(report["totalAmountThousand"], 321680600)
        self.assertEqual(len(report["items"][0]["derivationTrace"]), 5)
        self.assertEqual(len(report["items"][0]["evidenceVariables"]), 9)

    def test_historical_cutoff_does_not_leak_later_evidence(self):
        past = evidence_catalog("양육비 선지급 신청", "2200703", "2024-06-20")
        self.assertNotIn(self.method["method_key"], {m["method_key"] for m in past["methods"]})

    def test_self_answer_excluded(self):
        self.assertTrue(all(v["source_bill_no"] != "2200703" for v in self.catalog["variables"]))

    def test_forged_id_rejected(self):
        with self.assertRaises(ValueError):
            selected_web_context({**self.selection, "evidence_keys": ["invented"]}, self.catalog,
                                 "양육비 선지급 신청", "direct_annual_amount")

    def test_abolition_is_not_new_benefit(self):
        with self.assertRaises(ValueError):
            selected_web_context(self.selection, self.catalog, "제14조를 삭제한다", "direct_annual_amount")

    def test_korean_errors(self):
        self.assertIn("적용 연도", user_error("selected DB evidence year mismatch: private-id"))
        self.assertNotIn("private-id", user_error("unknown selected evidence key: private-id"))

    def test_pdf_line_break_does_not_reject_advance_amount(self):
        context = selected_web_context(self.selection, self.catalog,
            '양육비선지\n급금액은 가이드라인을 고려하여 책정한다.', 'direct_annual_amount')
        self.assertEqual(context['support_derivation'], 'child_support_advance_expense')

    def test_wrong_abolition_quote_offers_verified_recovery_without_auto_accept(self):
        import fitz
        record = json.loads((ROOT / 'docs/erce/first_runs/ERCE_FIRST_RUN_2200703.json').read_text())
        draft = record['ai_draft']
        row = draft['articles'][0]
        row.update(source_page=6, source_quote='제14조및제14조의2부터제14조의4까지를각각삭제한다.',
                   evidence_selection=self.selection)
        path = ROOT / 'backend/generated/assembly_22_pdfs/by_bill/2200703/bill_text.pdf'
        result = analyze_erce_pdf('bill_text.pdf', base64.b64encode(path.read_bytes()).decode(), ai_draft=draft)
        item = result['erce']['items'][0]
        self.assertEqual(item['calculation']['status'], 'needs_review')
        candidates = item['citationRecoveryCandidates']
        self.assertTrue(candidates)
        candidate = candidates[0]
        self.assertEqual(candidate['articleRef'], '제21조의6')
        self.assertEqual(candidate['sourcePage'], 8)
        with fitz.open(path) as pdf:
            self.assertIn(candidate['sourceQuote'], pdf[candidate['sourcePage']-1].get_text())
        self.assertEqual(candidate['calculation']['status'], 'computed_review')
        self.assertEqual(sum(candidate['calculation']['annualAmountsThousand']), 321680600)

    def test_existing_advance_reference_is_not_a_new_application_clause(self):
        self.assertEqual(advance_clause_candidates(['제21조의6(양육비선지급신청등) 먼저지급 신청할수있다. 1. 조건']), [])


if __name__ == "__main__":
    unittest.main()
