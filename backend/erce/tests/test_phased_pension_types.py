import tempfile
import unittest
from pathlib import Path
from backend.erce.phased_pension_types import phased_pension_type_rows
from backend.erce.scripts.check_phased_pension_types import payload
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.web_bridge import calculate_erce_web_item


class PensionTypeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"evidence.sqlite3";save_variable_rows(phased_pension_type_rows(),self.db)
        self.p={**payload(),"bill_no":"SYNTHETIC_TYPES","evidence_mode":"holdout"}
    def calc(self,p):return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_real_group_counts_and_effects_reconcile(self):
        r=self.calc(self.p);trace=r["derivationTrace"]
        self.assertEqual(r["status"],"computed_review")
        for i,total in enumerate([5973059,6238798,6508574,6758487]):
            self.assertEqual(sum(g["historical_counts"][i] for g in trace[:4]),total)
        for i in range(5):
            self.assertAlmostEqual(sum(g["forecast_share"][i] for g in trace[:4]),1)
            self.assertAlmostEqual(trace[-1]["eligibility_expansion_won"][i]+trace[-1]["reduction_recovery_won"][i],trace[-1]["total_increment_won"][i],places=2)
            self.assertAlmostEqual(sum(g["eligibility_expansion_won"][i] for g in trace[:4]),trace[-1]["eligibility_expansion_won"][i],places=2)
        self.assertTrue(all(v==0 for v in trace[0]["reduction_recovery_won"]))
        self.assertTrue(all(v==0 for v in trace[2]["reduction_recovery_won"]))

    def test_actual_counts_and_proxy_prices_are_distinct(self):
        t=self.calc(self.p)["derivationTrace"]
        self.assertEqual([g["historical_counts"][-1] for g in t[:4]],[3368571,2484187,421256,484473])
        self.assertEqual([g["group_price_is_proxy"] for g in t[:4]],[False,False,True,True])

    def test_source_scope_and_missing_proxy_confirmation_guard(self):
        for change in ({"pension_distribution_basis":"all_average"},{"reduced_group_split_note":""},
            {"reduced_couple_recovery":"fit_gold"},{"bill_no":"2211669"},{"cutoff_date":"2025-07-23"}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.calc({**self.p,**change})
