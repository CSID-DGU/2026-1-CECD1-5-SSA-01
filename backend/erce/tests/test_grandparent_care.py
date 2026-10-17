import tempfile
import unittest
from pathlib import Path
from backend.erce.grandparent_care_evidence import grandparent_care_rows
from backend.erce.common_population_evidence import single_age_population_matrix,population_series
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.scripts.check_grandparent_care import care_payload
from backend.erce.web_bridge import calculate_erce_web_item


class GrandparentCareTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"test.sqlite3"
        save_variable_rows(grandparent_care_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2211034"],self.db)

    def payload(self):
        return {**care_payload(),"bill_no":"NEW_GRANDPARENT_SUPPORT","evidence_mode":"holdout"}

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_existing_population_and_age_by_age_counts(self):
        matrix=single_age_population_matrix(0,5,2027,5)
        self.assertEqual(matrix["0"],population_series("age0_population",2027,5))
        expected={"0":[11392,11900,12364,12770,13110],"1":[9955,10448,10912,11337,11708],
            "2":[8663,8658,9086,9489,9857],"3":[9588,9098,9094,9542,9965],
            "4":[9484,8896,8442,8439,8855],"5":[11582,10926,10249,9727,9723]}
        r=self.calculate(self.payload())
        for age,values in expected.items():
            self.assertEqual([t["age_child_counts"][age] for t in r["derivationTrace"]],values)
        self.assertEqual([round(v/100000) for v in r["annualAmountsThousand"]],[839,843,857,878,905])
        self.assertAlmostEqual(sum(r["annualAmountsThousand"])/100000,4321.2384)

    def test_child_net_amounts_and_registration_are_explicit(self):
        p=self.payload();r=self.calculate(p);t=r["derivationTrace"][0]
        self.assertEqual(t["gross_monthly_support"],180000)
        self.assertEqual(t["net_monthly_by_age"],{"0":180000,"1":180000,"2":80000,"3":80000,"4":80000,"5":80000})
        p["explicit_inputs"]={"registration_take_up":dict(value=.5,unit="ratio",source_ref="확인된참여률후보50%")}
        self.assertAlmostEqual(sum(self.calculate(p)["annualAmountsThousand"])/100000,4321.2384/2)

    def test_missing_share_or_population_requests_information(self):
        p=self.payload();p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if "grandparent_care_shares" not in k]
        r=self.calculate(p)
        self.assertEqual(r["status"],"needs_input")
        self.assertIn("grandparent_care_shares",r["missingDerivationVariables"])
        p=self.payload();p.pop("start_year")
        self.assertIn("start_year",self.calculate(p)["missingVariables"])

    def test_scope_vintage_duplicate_index_and_own_answer_guard(self):
        for change in ({"grandparent_count_basis":"elderly_population"},{"population_geography":"서울"},
                {"population_vintage":"2025-12"},{"care_price_projection":"cpi_2_percent"},
                {"registration_scope_note":""},{"start_year":2026},{"bill_no":"2211034"}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.calculate({**self.payload(),**change})
        p=self.payload();p["explicit_inputs"]={"growth_rate":dict(value=.02,unit="ratio/year",source_ref="잘못된일괄물가")}
        with self.assertRaises(ValueError):self.calculate(p)
