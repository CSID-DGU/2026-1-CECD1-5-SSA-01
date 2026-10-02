import unittest

from backend.erce.draft_report import generate_draft


class DraftReportTests(unittest.TestCase):
    def payload(self):
        return {"bill_name": "합성 시험 법안", "start_year": 2026, "years": 2,
                "items": [{"name": "장비", "trigger_ref": "제1조", "route_key": "quantity_unit",
                           "explicit_inputs": {
                               "quantity": {"value": 3, "unit": "item", "source_ref": "법안 제1조"},
                               "unit_cost": {"value": 1000000, "unit": "KRW/item", "source_ref": "사용자 입력 가정"}},
                           "annualAmountsThousand": [999999999, 999999999]}]}

    def test_recalculates_and_renders_sources_not_client_totals(self):
        report = generate_draft(self.payload())
        self.assertEqual(report["status"], "draft_ready")
        self.assertEqual(report["annualAmountsThousand"], [3000, 3000])
        self.assertEqual(report["totalAmountThousand"], 6000)
        for text in ("Ⅰ. 비용추계 결과", "Ⅱ. 재정수반요인", "Ⅲ. 추계의 전제", "Ⅳ. 부대의견",
                     "사용자 입력 가정", "단위: 천원", "2026", "2027"):
            self.assertIn(text, report["markdown"])

    def test_missing_item_blocks_report(self):
        payload = self.payload()
        payload["items"].append({"name": "미입력 항목", "route_key": "quantity_unit"})
        report = generate_draft(payload)
        self.assertEqual(report["status"], "needs_input")
        self.assertNotIn("markdown", report)
        self.assertEqual(report["pendingItems"][0]["missingVariables"], ["quantity", "unit_cost"])

    def test_exclusions_not_presented_as_whole_bill_cost(self):
        report = generate_draft({**self.payload(), "exclusions": ["제2조 교육비: 규모 미정"]})
        self.assertIn("법안 전체 비용은 아닙니다", report["summary"])
        self.assertIn("제2조 교육비: 규모 미정", report["markdown"])

    def test_period_and_alternative_scenarios_checked(self):
        for change in ({"start_year": None}, {"years": 0}, {"years": True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                generate_draft({**self.payload(), **change})
        payload = self.payload()
        payload["items"][0]["start_year"] = 2027
        with self.assertRaisesRegex(ValueError, "시작연도"):
            generate_draft(payload)
        payload["items"] = [{"route_key": "infertility_leave_civil_proxy"},
                            {"route_key": "infertility_leave_budget_proxy"}]
        with self.assertRaisesRegex(ValueError, "대안 시나리오"):
            generate_draft(payload)
