import tempfile
import unittest
from pathlib import Path
from backend.erce.basic_pension_statistical_proxies import basic_pension_proxy_rows
from backend.erce.basic_pension_staged_evidence import basic_pension_staged_rows
from backend.erce.scripts.check_basic_pension_proxy import proxy_payload
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.web_bridge import calculate_erce_web_item


class PensionProxyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"evidence.sqlite3"
        save_variable_rows(basic_pension_staged_rows()+basic_pension_proxy_rows(),self.db)
        self.p={**proxy_payload("lower30"),"bill_no":"SYNTHETIC_PROXY","evidence_mode":"holdout"}

    def test_proxy_computes_but_requires_opt_in(self):
        r=calculate_erce_web_item(self.p,variable_db_path=self.db)
        self.assertEqual(r["status"],"computed_review")
        for change in ({"use_national_pension_proxy":False},{"pension_proxy_confirmation_note":""},
                       {"pension_rate_basis":"actual_income_band"},{"cutoff_date":"2024-11-12"}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                calculate_erce_web_item({**self.p,**change},variable_db_path=self.db)

    def test_proxy_preserves_actual_input_priority(self):
        p={**self.p,"explicit_inputs":{**self.p["explicit_inputs"],
            "pension_delta_payment_factor":dict(value=.8,unit="ratio",source_ref="합성법안 확인계수")}}
        r=calculate_erce_web_item(p,variable_db_path=self.db)
        expected=basic_pension_staged_rows()[2]["value"][0]*.3*basic_pension_proxy_rows()[0]["value"]*.8
        self.assertAlmostEqual(r["derivationTrace"][0]["values"][0],expected)
