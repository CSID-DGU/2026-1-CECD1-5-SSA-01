import tempfile
import unittest
from pathlib import Path
from backend.erce.published_pension_replay import published_pension_replay_rows
from backend.erce.scripts.check_published_pension_replay import payload
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


class PublishedPensionReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"evidence.sqlite3";save_variable_rows(published_pension_replay_rows(),self.db)
        self.p={**payload(),"variable_db_path":str(self.db)}

    def test_replay_matches_grand_total_without_adjusting_annual_discrepancy(self):
        r=estimate_routed_item(self.p)
        self.assertEqual(sum(r.annual_amounts_thousand),30100000000)
        self.assertEqual(r.annual_amounts_thousand[2],6600000000)

    def test_same_target_only_and_mode_guards(self):
        for change in ({"bill_no":"OTHER_BILL"},{"evidence_mode":"holdout"},
                       {"replay_purpose":"prediction"},{"cutoff_date":"2025-07-23"},
                       {"explicit_inputs":{"growth_rate":dict(value=.05,unit="ratio",source_ref="잘못된보정")}}):
            with self.subTest(change=change),self.assertRaises(ValueError):estimate_routed_item({**self.p,**change})

    def test_public_bridge_cannot_escape_holdout_with_development_flag(self):
        with self.assertRaises(ValueError):calculate_erce_web_item(payload(),variable_db_path=self.db)
