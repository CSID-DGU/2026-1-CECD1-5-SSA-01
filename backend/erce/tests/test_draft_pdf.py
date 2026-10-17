import json
from pathlib import Path
import unittest

import fitz

from backend.erce.draft_pdf import generate_draft_pdf, render_draft_html, short_sources
from backend.erce.draft_report import generate_draft


class DraftPdfTests(unittest.TestCase):
    def child_payload(self):
        root = Path(__file__).resolve().parents[3]
        record = json.loads((root / "docs/erce/first_runs/ERCE_FIRST_RUN_2200703.json").read_text())
        return {"bill_name": record["ai_draft"]["bill_name"], "bill_no": "2200703", "start_year": 2026,
                "items": [{**record["payload"], "name": "양육비 선지급", "trigger_ref": "안 제21조의6",
                           "change_summary": "미지급 양육비 채권자에 대한 양육비 선지급 제도 도입"}]}

    def test_child_pdf_has_official_style_sections_and_detail_tables(self):
        data = generate_draft_pdf(self.child_payload())
        self.assertTrue(data.startswith(b"%PDF-"))
        with fitz.open(stream=data, filetype="pdf") as pdf:
            text = "\n".join(page.get_text() for page in pdf)
            self.assertIn("비용추계서 초안", pdf[0].get_text())
            for heading in ("Ⅰ. 비용추계 결과", "Ⅱ. 재정수반요인", "Ⅲ. 비용추계의 전제와 상세내역", "Ⅳ. 부대의견", "Ⅴ. 작성 정보"):
                self.assertIn(heading, text)
            for value in ("63,333", "63,881", "64,382", "64,836", "65,249", "321,681", "64,336"):
                self.assertIn(value, text)
            self.assertIn("27,056", text)
            self.assertIn("양육비 선지급 건수 산출 내역", text)
            self.assertNotIn("[22516347", text)
            self.assertNotIn("24C1988", text)
            for page in pdf:
                self.assertAlmostEqual(page.rect.width, fitz.paper_rect("a4").width, places=1)

    def test_pending_values_block_download(self):
        with self.assertRaises(ValueError):
            generate_draft_pdf({"start_year": 2026, "items": [{"route_key": "quantity_unit"}]})

    def test_child_narrative_explains_actual_assumptions_not_engine_instructions(self):
        payload = self.child_payload()
        report = generate_draft(payload)
        for method in report["items"][0]["selectedMethods"]:
            method["confirmed_assumptions"]["internal"] = "DB 전망연도를 그대로 사업 시작연도로 사용하지 않는다. 중복 지출 제거로만 검토"
        _, html = render_draft_html(report, payload)
        self.assertNotIn("DB 전망연도", html)
        self.assertNotIn("중복 지출 제거로만 검토", html)
        self.assertIn("1,601,000,000원", html)
        self.assertIn("해당 예산을 차감하여", html)
        self.assertIn("제5조제2항", html)
        self.assertIn("2026년에 사업을 개시하는 것으로 가정", html)
        self.assertIn("실제 신청률 및 선정률", report["markdown"])

    def test_server_recalculates_not_client_total(self):
        payload = self.child_payload()
        payload["items"][0]["annualAmountsThousand"] = [999] * 5
        report = generate_draft(payload)
        self.assertEqual(report["totalAmountThousand"], 321680600)

    def test_html_escapes_user_content(self):
        payload = self.child_payload()
        payload["bill_name"] = '<script>alert("x")</script>'
        cover, _ = render_draft_html(generate_draft(payload), payload)
        self.assertNotIn('<script>', cover)
        self.assertIn('&lt;script&gt;', cover)

    def test_sources_show_only_bill_numbers(self):
        self.assertEqual(short_sources(["2201707 비용추계서24C1988 PDF4~7쪽", "2201707 비용추계서"]), "의안 2201707")


if __name__ == "__main__":
    unittest.main()
