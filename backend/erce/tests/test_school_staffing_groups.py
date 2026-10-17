import tempfile
import unittest
from pathlib import Path
from backend.erce.school_staffing_groups import (
    split_school_staffing_groups,school_staffing_group_rows,reviewed_school_groups_replay,
)
from backend.erce.teacher_staffing_evidence import teacher_staffing_rows,teacher_staffing_review_candidates
from backend.erce.court_organization_evidence import court_organization_rows
from backend.erce.variable_evidence_store import save_variable_rows,find_variable_candidates,evidence_payload_from_db
from backend.erce.web_bridge import route_options


class SchoolStaffingGroupTests(unittest.TestCase):
    def test_overlap_is_not_counted_twice_or_assumed_zero(self):
        self.assertEqual(split_school_staffing_groups(100,80,30,5),
                         dict(large_public=100,meals_public=50,large_private=5))
        for overlap in (None,81,-1,False):
            with self.assertRaises(ValueError):
                split_school_staffing_groups(100,80,overlap,5)

    def test_replay_nine_components_first_year_assets_and_private_pay(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"variables.sqlite3"
            save_variable_rows(school_staffing_group_rows()+teacher_staffing_rows()+court_organization_rows(),db)
            r=reviewed_school_groups_replay(db)
            self.assertEqual(len(r["components"]),9)
            self.assertEqual(r["effective_headcounts"],dict(large_public=1208,meals_public=813,large_private=91))
            self.assertEqual(r["components"]["large_public:initial_asset"],[6017048,0,0,0,0])
            self.assertEqual(r["components"]["meals_public:initial_asset"],[4049553,0,0,0,0])
            self.assertEqual(r["components"]["large_private:private_pension"][0],
                             round(91*34491000*.03706/1000))
            self.assertEqual(r["total_thousand"],sum(r["annual_amounts_thousand"]))

    def test_quantities_not_reused_self_exclusion_and_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"variables.sqlite3"
            save_variable_rows(school_staffing_group_rows(),db)
            candidates=find_variable_candidates(target_bill_no="new",cutoff_date="2026-10-03",db_path=db)
            self.assertFalse(any(r["variable_key"]=="headcount" for r in candidates))
            self.assertTrue(any(r["variable_key"]=="classroom_threshold" and r["value"]==36 for r in candidates))
            from backend.erce.teacher_staffing_evidence import PAY_PROFILE
            p=dict(bill_no="2207986",start_year=2026,years=5,cutoff_date="2026-10-03",
                evidence_mode="development_review",variable_db_path=db,staff_pay_profile=PAY_PROFILE,
                route_key="personnel_average",school_sector="public",staffing_target_group="large_public",
                selected_evidence_keys=["2207986:large_public:headcount"])
            self.assertEqual(evidence_payload_from_db(p)["selected_variable_inputs"]["headcount"]["value"],1208)
            with self.assertRaisesRegex(ValueError,"staffing_target_group mismatch"):
                evidence_payload_from_db({**p,"staffing_target_group":"meals_public"})
            with self.assertRaisesRegex(ValueError,"target answer"):
                evidence_payload_from_db({**p,"evidence_mode":"holdout"})
            with self.assertRaisesRegex(ValueError,"future"):
                evidence_payload_from_db({**p,"cutoff_date":"2025-02-07"})

    def test_target_split_review_is_wired(self):
        items=[dict(routeKey="personnel_average",itemIndex=0,name="국공립 보수")]
        articles=[dict(text="일정 규모 이상 또는 1일 2회 이상 급식 학교에는 2명 이상의 영양교사를 둔다.",
                       no="제7조",source_page=3)]
        review=teacher_staffing_review_candidates(items,articles,{r["routeKey"]:r for r in route_options()})
        split=[r for r in review if r["componentKey"]=="teacher_target_group_split"]
        self.assertEqual(len(split),1)
        self.assertTrue(split[0]["requiresConfirmation"])
