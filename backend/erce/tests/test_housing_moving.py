import copy
import tempfile
import unittest
from pathlib import Path
from backend.erce.housing_moving_evidence import housing_updated_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.scripts.check_housing_moving import moving_payload,updated_payload
from backend.erce.web_bridge import calculate_erce_web_item


class HousingMovingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"test.sqlite3"
        save_variable_rows(housing_updated_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2209844"],self.db)

    def payload(self):
        return {**moving_payload(),"bill_no":"NEW_MOVING_SUPPORT","evidence_mode":"holdout"}

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_two_year_history_baseline_and_single_package(self):
        r=self.calculate(self.payload());t=r["derivationTrace"]
        self.assertEqual(r["status"],"computed_review")
        self.assertEqual([x["gross_moving_households"] for x in t],[28649,28319,27980,28205,28405])
        self.assertEqual([x["incremental_households"] for x in t],[13649,13319,12980,13205,13405])
        self.assertEqual(t[2]["prior_two_years_supported"],56968)
        self.assertEqual(t[0]["unit_price"],416160)
        self.assertAlmostEqual(sum(r["annualAmountsThousand"])/100000,288.24086)

    def test_missing_history_or_price_is_requested(self):
        p=self.payload();p.pop("prior_moving_supported_households")
        self.assertIn("prior_moving_supported_households",self.calculate(p)["missingDerivationVariables"])
        p=self.payload();p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if "moving_bundle_unit" not in k]
        r=self.calculate(p)
        self.assertEqual(r["status"],"needs_input");self.assertIn("moving_bundle_unit",r["missingDerivationVariables"])

    def test_actual_history_and_baseline_override(self):
        p=self.payload();p["prior_moving_supported_households"]=[100,200]
        r=self.calculate(p);self.assertEqual(r["derivationTrace"][0]["prior_two_years_supported"],300)
        p=self.payload();p["explicit_inputs"]={"baseline_supported_households":dict(value=10000,unit="household/year",source_ref="확인된기지원1만가구")}
        self.assertEqual(self.calculate(p)["derivationTrace"][0]["incremental_households"],18649)
        p=self.payload();p["explicit_inputs"]={"baseline_supported_households":dict(value=100000,unit="household/year",source_ref="기존사업이전수요를포함")}
        self.assertEqual(self.calculate(p)["annualAmountsThousand"],[0]*5)

    def test_wrong_bundle_duplicate_months_and_self_answer_blocked(self):
        for change in ({"moving_cost_bundle_confirmed":False},{"moving_repeat_exclusion_years":1},
                       {"moving_scope_note":""},{"moving_price_base_year":2024},{"bill_no":"2209844"}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.calculate({**self.payload(),**change})
        p=self.payload();p["explicit_inputs"]={"payments_per_year":dict(value=12,unit="event/year",source_ref="매월이사중복")}
        with self.assertRaises(ValueError):self.calculate(p)

    def test_management_year_vintages_and_fixed_first_year_price(self):
        p={**updated_payload("all_tenants_flat"),"bill_no":"NEW_MOVING_SUPPORT","evidence_mode":"holdout"}
        r=self.calculate(p)
        self.assertEqual(r["derivationTrace"][0]["monthly_public_payment"],30000)
        self.assertEqual(r["derivationTrace"][0]["base_price_year"],2027)
        self.assertAlmostEqual(sum(r["annualAmountsThousand"])/100000,27270.625)
        p={**updated_payload("arrears_shared"),"bill_no":"NEW_MOVING_SUPPORT","evidence_mode":"holdout"}
        t=self.calculate(p)["derivationTrace"]
        self.assertEqual(t[0]["recipient_share"],.102)
        self.assertEqual(t[0]["base_price_year"],2024)
        self.assertEqual(t[0]["base_monthly_common_fee"],68000)
