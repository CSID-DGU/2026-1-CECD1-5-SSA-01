import tempfile
import unittest
from pathlib import Path
from backend.erce.owner_energy_repair_evidence import energy_repair_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.scripts.check_owner_energy_repair import repair_payload
from backend.erce.web_bridge import calculate_erce_web_item


class OwnerEnergyRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"test.sqlite3"
        save_variable_rows(energy_repair_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2211430"],self.db)

    def payload(self):
        return {**repair_payload(),"bill_no":"NEW_OWNER_ENERGY","evidence_mode":"holdout"}

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_three_groups_and_increment_only_match_table(self):
        r=self.calculate(self.payload());t=r["derivationTrace"]
        self.assertEqual(t[0]["eligible_households"],dict(light=7701,medium=3177,heavy=1981))
        self.assertEqual(t[0]["base_increment_won"],dict(light=600000,medium=1800000,heavy=3000000))
        self.assertAlmostEqual(t[0]["cpi_factor"],1.019*1.02)
        self.assertAlmostEqual(sum(r["annualAmountsThousand"])/100000,880.70017)
        self.assertEqual([round(x/1000) for x in r["annualAmountsThousand"]],[16923,17262,17607,17959,18318])

    def test_missing_reference_prompts_instead_of_school_price(self):
        p=self.payload();p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if "repair_increment_base" not in k]
        r=self.calculate(p)
        self.assertEqual(r["status"],"needs_input")
        self.assertIn("repair_increment_base",r["missingDerivationVariables"])
        p=self.payload();p.pop("start_year")
        self.assertIn("start_year",self.calculate(p)["missingVariables"])

    def test_scope_cycles_income_and_self_answer_are_guarded(self):
        for change in ({"repair_recipient_scope":"tenant_households"},{"repair_payment_scenario":"actual_income_unknown"},
                {"annual_flow_note":""},{"repair_increment_base_year":2024},{"bill_no":"2211430"}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.calculate({**self.payload(),**change})
        p=self.payload();p["explicit_inputs"]={"repair_cycle":dict(value=3,unit="year",source_ref="중복분할")}
        with self.assertRaises(ValueError):self.calculate(p)

    def test_actual_group_counts_priority_and_invalid_map(self):
        p=self.payload();p["explicit_inputs"]={"repair_household_history":dict(
            value=dict(light=[100]*3,medium=[200]*3,heavy=[300]*3),unit="class_to_households",source_ref="확인된다른연간실적")}
        self.assertEqual(self.calculate(p)["derivationTrace"][0]["eligible_households"],dict(light=65,medium=131,heavy=196))
        p=self.payload();p["explicit_inputs"]={"repair_increment_base":dict(
            value=dict(light=600000,medium=1800000),unit="class_to_KRW/household",source_ref="그룹누락")}
        with self.assertRaises(ValueError):self.calculate(p)
