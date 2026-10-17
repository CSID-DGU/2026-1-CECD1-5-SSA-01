import copy
import tempfile
import unittest
from pathlib import Path
from backend.erce.median_pension_evidence import median_pension_rows,prepare_median_pension
from backend.erce.scripts.check_median_pension import payload,non_estimation_payload
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows,validate_non_estimation_review
from backend.erce.web_bridge import calculate_erce_web_item


class MedianPensionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"evidence.sqlite3"
        save_variable_rows(median_pension_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["method_key"]=="2204828:occupational_pension_not_estimated"],self.db)
        self.p={**payload(),"bill_no":"SYNTHETIC_MEDIAN_PENSION","evidence_mode":"holdout"}

    def calc(self,p):return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_source_replay_counts_and_money(self):
        r=self.calc(self.p)
        self.assertEqual(r["status"],"computed_review")
        total=sum(r["annualAmountsThousand"])/1e9
        self.assertAlmostEqual(total,100.23277715,places=7)
        self.assertEqual(len(r["derivationTrace"]),4)
        self.assertAlmostEqual(r["derivationTrace"][0]["count_growth"],(3235552/2880696)**.25-1)

    def test_future_self_version_period_and_double_growth_block(self):
        for change in ({"bill_no":"2204828"},{"cutoff_date":"2024-10-22"},
            {"use_unmatched_source_as_reference":False},{"start_year":2026},
            {"median_pension_conflict_note":""},{"pension_baseline_version":"latest"}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.calc({**self.p,**change})
        p=copy.deepcopy(self.p);p["explicit_inputs"]["growth_rate"]=dict(value=.05,unit="ratio",source_ref="중복")
        with self.assertRaises(ValueError):self.calc(p)

    def test_alternative_reading_requires_household_scope_review(self):
        with self.assertRaises(ValueError):self.calc({**self.p,"median_pension_reading":"income_gap_32pct_review"})

    def test_non_estimation_has_sources_and_no_zero_amount(self):
        p={**non_estimation_payload(),"bill_no":"SYNTHETIC_OCCUPATIONAL","evidence_mode":"holdout"}
        r=validate_non_estimation_review(p,db_path=self.db)
        self.assertEqual(r["decision"],"not_estimated");self.assertIsNone(r["amount"])
        for fact in ("reliable_income_distribution_available","payment_amount_confirmed"):
            q=copy.deepcopy(p);q["decision_facts"][fact]=True
            with self.assertRaises(ValueError):validate_non_estimation_review(q,db_path=self.db)
