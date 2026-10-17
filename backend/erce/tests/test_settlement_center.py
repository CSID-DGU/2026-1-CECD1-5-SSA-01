import tempfile
import unittest
from pathlib import Path

from backend.erce.engine import estimate_routed_item
from backend.erce.scripts.check_settlement_center import reviewed_payload
from backend.erce.support_method_operands import support_operand_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.web_bridge import calculate_erce_web_item


class SettlementCenterTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"refs.sqlite3"
        save_variable_rows(support_operand_rows(),self.db)

    def payload(self,kind="agriculture",scope="combined"):
        return {**reviewed_payload(kind,scope),"variable_db_path":str(self.db)}

    def test_accumulation_and_national_local_split(self):
        combined=[]
        for kind,unit in (("agriculture",500000),("fisheries",600000)):
            e=estimate_routed_item(self.payload(kind))
            self.assertEqual(e.resolved_variables["quantity"].value,[1,2,3,4,5])
            self.assertEqual(e.annual_amounts_thousand,tuple(unit*n for n in range(1,6)))
            national=estimate_routed_item(self.payload(kind,"national"))
            local=estimate_routed_item(self.payload(kind,"local"))
            self.assertEqual(tuple(a+b for a,b in zip(national.annual_amounts_thousand,local.annual_amounts_thousand)),e.annual_amounts_thousand)
            combined.append(sum(e.annual_amounts_thousand))
        self.assertEqual(sum(combined),16500000)

    def test_new_bill_schedule_reuses_price_without_target_stock(self):
        p=self.payload()
        p["bill_no"]="NEW_AGRICULTURE_CENTER"
        p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if ":initial_supported_centers:" not in k]
        p["explicit_inputs"]={
            "initial_supported_centers":dict(value=2,unit="center",source_ref="신규 지원대상이 된 기존기관 수. 기존 지원예산과 중복 없음"),
            "annual_new_centers":dict(value=[1,0,2,0,0],unit="center/year",source_ref="신규 사업계획")}
        r=calculate_erce_web_item(p,variable_db_path=self.db)
        self.assertEqual(r["annualAmountsThousand"],[1500000,1500000,2500000,2500000,2500000])
        del p["explicit_inputs"]["initial_supported_centers"]
        r=calculate_erce_web_item(p,variable_db_path=self.db)
        self.assertEqual(r["status"],"needs_input")
        self.assertIn("initial_supported_centers",r["missingDerivationVariables"])

    def test_scope_self_publication_and_confirmation_guards(self):
        for changes,message in [({"center_kind":"fisheries"},"center_kind mismatch"),
            ({"support_fiscal_scope":"national"},"support_fiscal_scope mismatch"),
            ({"evidence_mode":"holdout"},"target answer"),
            ({"cutoff_date":"2024-07-01"},"future"),
            ({"center_operation_scope_note":""},"continued operation"),
            ({"estimation_start_note":""},"separate basis"),
            ({"start_year":None},"start_year")]:
            with self.subTest(changes=changes),self.assertRaisesRegex(ValueError,message):
                estimate_routed_item({**self.payload(),**changes})

    def test_no_fractional_centers_or_duplicate_adjustment(self):
        p=self.payload()
        p["explicit_inputs"]={"annual_new_centers":dict(value=.5,unit="center/year",source_ref="test")}
        with self.assertRaisesRegex(ValueError,"integers"):
            estimate_routed_item(p)
        p["explicit_inputs"]={"growth_rate":dict(value=.02,unit="ratio",source_ref="test")}
        with self.assertRaisesRegex(ValueError,"duplicate adjustment"):
            estimate_routed_item(p)
