import copy
import tempfile
import unittest
from pathlib import Path
from backend.erce.commemorative_event_evidence import commemorative_event_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows,validate_non_estimation_review,find_method_candidates
from backend.erce.scripts.check_commemorative_event import event_payload,non_estimation_payload
from backend.erce.web_bridge import calculate_erce_web_item


class CommemorativeEventTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"evidence.sqlite3";save_variable_rows(commemorative_event_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2201850"],self.db)

    def test_national_event_is_not_campaign_or_seven_day_event_count(self):
        p={**event_payload(),"bill_no":"SYNTHETIC_EVENT","evidence_mode":"holdout"}
        r=calculate_erce_web_item(p,variable_db_path=self.db)
        self.assertEqual(r["annualAmountsThousand"],[100000]*5)
        for change in ({"service_cost_basis":"public_awareness_campaign"},{"commemorative_event_scale":"local_multiple_events"},
                       {"event_price_projection":"latest_official"},{"bill_no":"2201850"}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                calculate_erce_web_item({**p,**change},variable_db_path=self.db)

    def test_sourced_non_estimation_has_no_zero_amount(self):
        p={**non_estimation_payload(),"bill_no":"SYNTHETIC_ADVOCACY","evidence_mode":"holdout"}
        r=validate_non_estimation_review(p,db_path=self.db)
        self.assertEqual(r["decision"],"not_estimated");self.assertIsNone(r["amount"])
        self.assertIn("PDF3쪽",r["source_ref"]);self.assertTrue(r["reestimate_when"])
        candidates=find_method_candidates(query="장애인권익옹호기관인구면적1개소설치",cutoff_date="2026-10-06",target_bill_no="SYNTHETIC_ADVOCACY",db_path=self.db)
        self.assertTrue(any(r["method_key"]=="2201850:regional_advocacy_expansion_not_estimated" for r in candidates))

    def test_new_plan_or_uncovered_region_prevents_reusing_reason(self):
        p={**non_estimation_payload(),"bill_no":"SYNTHETIC_ADVOCACY","evidence_mode":"holdout"}
        for fact,value in (("existing_all_regions_covered",False),("reliable_incremental_installation_basis_available",True),
                           ("quantified_expansion_standard_available",True)):
            q=copy.deepcopy(p);q["decision_facts"][fact]=value
            with self.subTest(fact=fact),self.assertRaises(ValueError):validate_non_estimation_review(q,db_path=self.db)
        for change in ({"bill_no":"2201850"},{"cutoff_date":"2024-07-17"},{"excluded_bill_nos":["2201850"]}):
            with self.subTest(change=change),self.assertRaises(ValueError):validate_non_estimation_review({**p,**change},db_path=self.db)
