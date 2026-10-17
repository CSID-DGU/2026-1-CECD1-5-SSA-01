import tempfile
import unittest
from pathlib import Path
from backend.erce.child_support_advance_evidence import ADVANCE,SYSTEM,child_support_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.scripts.check_child_support_advance import advance_payload
from backend.erce.web_bridge import calculate_erce_web_item


class ChildSupportAdvanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"test.sqlite3"
        save_variable_rows(child_support_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2201707"],self.db)

    def payload(self,profile):
        return {**advance_payload(profile),"bill_no":"NEW_CHILD_SUPPORT","evidence_mode":"holdout"}

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_cohort_filters_round_only_final_and_legacy_budget(self):
        r=self.calculate(self.payload(ADVANCE));t=r["derivationTrace"]
        self.assertEqual([x["advance_cases"] for x in t],[27056,27284,27493,27682,27854])
        self.assertEqual(t[0]["gross_expense"],64934400000)
        self.assertEqual(t[0]["legacy_budget"],1601000000)
        self.assertEqual(r["annualAmountsThousand"],[63333400,63880600,64382200,64835800,65248600])
        p=self.payload(ADVANCE);p["explicit_inputs"]={"legacy_support_budget":dict(value=0,unit="KRW/year",source_ref="확인된기존사업없음시나리오")}
        self.assertEqual(self.calculate(p)["annualAmountsThousand"][0],64934400)

    def test_upgrade_warranty_and_future_maintenance_prices(self):
        r=self.calculate(self.payload(SYSTEM))
        self.assertEqual(r["annualAmountsThousand"],[948000,0,142200,145186,148090])
        self.assertEqual(r["derivationTrace"][1]["maintenance_expense"],0)
        self.assertEqual(r["derivationTrace"][2]["first_maintenance_year"],2028)

    def test_missing_data_scope_or_reference_is_not_zero(self):
        p=self.payload(ADVANCE);p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if "claim_holder_share" not in k]
        r=self.calculate(p)
        self.assertEqual(r["status"],"needs_input");self.assertIn("claim_holder_share",r["missingDerivationVariables"])
        for change in ({"fiscal_reporting":"net_recovery_from_expense"},{"child_support_model":SYSTEM},
                {"advance_take_up_scenario":"unknown"},{"bill_no":"2201707"},{"start_year":2025}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.calculate({**self.payload(ADVANCE),**change})
        p=self.payload(SYSTEM);p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if "upgrade_components" not in k]
        self.assertIn("upgrade_components",self.calculate(p)["missingDerivationVariables"])

    def test_receipts_never_net_into_expense_and_existing_plan_priority(self):
        p=self.payload(ADVANCE);p["explicit_inputs"]={"recovery_rate":dict(value=.1536,unit="ratio",source_ref="누적회수율")}
        with self.assertRaises(ValueError):self.calculate(p)
        p=self.payload(SYSTEM)
        p["explicit_inputs"]={"upgrade_components":dict(value={"confirmed_upgrade":100000000},unit="component_to_KRW",source_ref="확인된동일과업견적")}
        r=self.calculate(p)
        self.assertEqual(r["annualAmountsThousand"][:3],[100000,0,15000])
