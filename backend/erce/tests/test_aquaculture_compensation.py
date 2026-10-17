import tempfile
import unittest
from pathlib import Path
from backend.erce.aquaculture_compensation_evidence import aquaculture_compensation_rows, COMMITTEE_ID
from backend.erce.variable_evidence_store import save_variable_rows,find_variable_candidates
from backend.erce.engine import estimate_routed_item


class AquacultureCompensationTests(unittest.TestCase):
    def test_db_replay_and_scope_guards(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"variables.sqlite3"
            rows=aquaculture_compensation_rows()
            save_variable_rows(rows,db)
            payload=dict(route_key="committee_member_increase",bill_no="2207048",start_year=2026,
                years=5,cutoff_date="2026-10-03",evidence_mode="development_review",
                committee_identity=COMMITTEE_ID,variable_db_path=db,
                selected_evidence_keys=[r["evidence_key"] for r in rows])
            self.assertEqual(estimate_routed_item(payload).annual_amounts_thousand,(2400,)*5)
            with self.assertRaisesRegex(ValueError,"target answer"):
                estimate_routed_item({**payload,"evidence_mode":"holdout"})
            with self.assertRaisesRegex(ValueError,"committee_identity mismatch"):
                estimate_routed_item({**payload,"committee_identity":"other"})
            self.assertEqual(find_variable_candidates(cutoff_date="2024-12-27",db_path=db),[])
            candidates=find_variable_candidates(cutoff_date="2026-10-03",target_bill_no="new",db_path=db)
            self.assertEqual({r["variable_key"] for r in candidates},{"annual_meetings","meeting_unit_price"})
            p={**payload,"bill_no":"new","evidence_mode":"holdout",
               "selected_evidence_keys":[r["evidence_key"] for r in candidates],
               "evidence_selection_reasons":{r["evidence_key"]:"동일 위원회; 과거 운영 실적 유지 및 선례 참석비 가정" for r in candidates},
               "explicit_inputs":{"additional_paid_members":{"value":1,"source_ref":"별도 의안의 유급 순증위원1명 확인"}}}
            self.assertEqual(estimate_routed_item(p).annual_amounts_thousand,(1200,)*5)

    def test_incremental_members_not_entire_committee(self):
        result=estimate_routed_item(dict(route_key="committee_member_increase",years=1,
            explicit_inputs=dict(additional_paid_members=2,annual_meetings=4,meeting_unit_price=300000)))
        self.assertEqual(result.annual_amounts_thousand,(2400,))
        with self.assertRaises(ValueError):
            estimate_routed_item(dict(route_key="committee_member_increase",years=1,
                explicit_inputs=dict(additional_paid_members=-1,annual_meetings=4,meeting_unit_price=300000)))
