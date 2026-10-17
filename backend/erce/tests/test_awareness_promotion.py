import tempfile
import unittest
from pathlib import Path
from backend.erce.awareness_promotion_evidence import awareness_promotion_rows
from backend.erce.scripts.check_awareness_promotion import package_payload
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows,find_method_candidates
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.engine import estimate_routed_item


class AwarenessPromotionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"evidence.sqlite3"
        save_variable_rows(awareness_promotion_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["method_key"]=="2200879:annual_awareness_campaign_and_video"],self.db)
    def p(self,package):return {**package_payload(package),"bill_no":"SYNTHETIC_AWARENESS","evidence_mode":"holdout"}

    def test_two_packages_compute_same_annual_total(self):
        annual=[]
        for name in ("public_awareness_campaign","awareness_video_production_distribution"):
            r=calculate_erce_web_item(self.p(name),variable_db_path=self.db)
            self.assertEqual(r["status"],"computed_review");annual.append(r["annualAmountsThousand"])
        self.assertEqual([sum(x[i] for x in annual) for i in range(5)],[350000]*5)
        candidates=find_method_candidates(query="장애인보조견인식개선공익광고홍보",cutoff_date="2026-10-06",target_bill_no="SYNTHETIC_AWARENESS",db_path=self.db)
        self.assertTrue(any(r["method_key"]=="2200879:annual_awareness_campaign_and_video" for r in candidates))

    def test_wrong_task_scale_price_version_self_and_future_blocked(self):
        p=self.p("awareness_video_production_distribution")
        for change in ({"service_cost_basis":"public_awareness_campaign"},{"awareness_scale_profile":"small_local_poster"},
            {"awareness_price_projection":"latest_official"},{"bill_no":"2200879","evidence_mode":"development_review"},
            {"cutoff_date":"2024-06-24"}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                calculate_erce_web_item({**p,**change},variable_db_path=self.db)

    def test_explicit_quantity_wins_over_precedent_annual_frequency(self):
        p={**self.p("public_awareness_campaign"),"variable_db_path":str(self.db),
            "explicit_inputs":{"quantity":dict(value=2,unit="package/year",source_ref="합성법안명시패키지수")}}
        r=estimate_routed_item(p)
        self.assertEqual(r.annual_amounts_thousand,(400000,)*5)
