import tempfile
import unittest
from pathlib import Path
from backend.erce.enterprise_assistant_evidence import enterprise_assistant_rows, PROFILE
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_enterprise_assistant import assistant_payload, run_regression
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.route_tree import route_for_path


class EnterpriseAssistantTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.db=Path(temp.name)/"test.sqlite3"
        save_variable_rows(enterprise_assistant_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2207221"],self.db)

    def web(self,**updates):
        return calculate_erce_web_item({**assistant_payload(False),"bill_no":"NEW_ENTERPRISE_ASSISTANT","evidence_mode":"holdout",**updates},variable_db_path=self.db)

    def test_gold_display_reproduced_from_independent_budget_operands(self):
        r=run_regression(self.db)
        self.assertAlmostEqual(r["replay_total_eok"],16120.20141,places=4)
        self.assertLess(r["error_percent"],.002)
        self.assertGreater(r["error_percent"],0)
        self.assertEqual(r["annual_display_matches"],5)
        self.assertTrue(r["displayed_total_matches"])
        self.assertTrue(r["engine_and_web_same"])

    def test_annual_unit_and_normal_price_year(self):
        r=self.web();t=r["derivationTrace"][0]
        growth=(9142/4494)**.25-1
        price=14843*125*12*.98406
        self.assertAlmostEqual(t["annual_price_won"],price*(15092/14843)**2)
        self.assertAlmostEqual(t["recipients"],9142*(1+growth)**4*.5)
        self.assertEqual(t["price_base_year"],2024)
        self.assertEqual(route_for_path(["이전지출","인력서비스지원","1인중증장애인기업연간업무지원"]),PROFILE)
        with self.assertRaises(ValueError):
            self.web(explicit_inputs={"payments_per_year":dict(value=12,unit="month/year",source_ref="연단가에중복개월")})

    def test_explicit_take_up_and_confirmed_baseline_priority(self):
        half=self.web()["annualAmountsThousand"]
        r=self.web(explicit_inputs={"assistant_take_up":dict(value=.25,unit="ratio",source_ref="새사업계획지원율25%")})
        self.assertAlmostEqual(r["annualAmountsThousand"][0],half[0]/2,delta=1)
        r=self.web(explicit_inputs={"existing_public_support":dict(value=200000000,unit="KRW/year",source_ref="시험용 확인된 추계기간 연간 기존지원액")})
        self.assertEqual(r["annualAmountsThousand"],[a-200000 for a in half])

    def test_missing_history_and_confirmation_and_price_replay_leak(self):
        keys=[k for k in assistant_payload(False)["selected_evidence_keys"] if "history" not in k]
        self.assertIn("solo_enterprise_history",self.web(selected_evidence_keys=keys)["missingDerivationVariables"])
        self.assertIn("assistant_continuation_confirmation",self.web(assistant_continuation_confirmed=False)["missingDerivationVariables"])
        with self.assertRaises(ValueError):
            self.web(reviewed_assistant_price_year_offset=1)
        with self.assertRaises(ValueError):
            calculate_erce_web_item(assistant_payload(False),variable_db_path=self.db)
