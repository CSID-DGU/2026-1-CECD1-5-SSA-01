import tempfile
import unittest
from pathlib import Path
from backend.erce.engine import estimate_routed_item
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.school_meal_research_evidence import (
    school_meal_research_rows,reviewed_school_meal_research_payloads,linked_research_cycle_candidates,
)


class SchoolMealResearchTests(unittest.TestCase):
    def test_answer_reference_replay_with_version_confirmation(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"variables.sqlite3"
            save_variable_rows(school_meal_research_rows(),db)
            plan,survey=reviewed_school_meal_research_payloads(db)
            self.assertEqual(estimate_routed_item(plan).annual_amounts_thousand,(42000,0,0,44000,0))
            self.assertEqual(estimate_routed_item(survey).annual_amounts_thousand,(22000,0,0,24000,0))
            for change,message in (({"evidence_mode":"holdout"},"target answer"),
                ({"use_unmatched_source_as_reference":False},"unmatched-source"),
                ({"research_service_kind":"other_research"},"research_service_kind mismatch"),
                ({"cutoff_date":"2025-07-08"},"future"),
                ({"start_year":2027},"year mismatch")):
                with self.subTest(change=change),self.assertRaisesRegex(ValueError,message):
                    estimate_routed_item({**survey,**change})

    def test_linked_review_does_not_silently_inherit_annual_cycle(self):
        p=dict(route_key="research_survey",agency="교육부",bill_no="synthetic",
            cutoff_date="2026-10-03",start_year=2027,years=5,
            explicit_inputs={"survey_unit_cost":22000000})
        self.assertEqual(sum(estimate_routed_item(p).annual_amounts_thousand),110000)
        with self.assertRaisesRegex(ValueError,"recurrence_interval_years"):
            estimate_routed_item({**p,"linked_plan_recurrence_years":3})
        confirmed={**p,"linked_plan_recurrence_years":3,
            "calculated_inputs":{"recurrence_interval_years":dict(value=3,unit="year",
                source_ref="사용자 확인:3년 기본계획과 함께 기준 검토",is_assumption=True)}}
        r=estimate_routed_item(confirmed)
        self.assertEqual(r.annual_amounts_thousand,(22000,0,0,22000,0))
        self.assertTrue(r.resolved_variables["recurrence_interval_years"].is_assumption)
        explicit={**confirmed,"explicit_inputs":{**p["explicit_inputs"],"recurrence_interval_years":1}}
        self.assertEqual(sum(estimate_routed_item(explicit).annual_amounts_thousand),110000)

    def test_sparse_scheduled_prices_require_occurrence_years_and_no_double_index(self):
        p=dict(route_key="research_plan",years=5,start_year=2025,cutoff_date="2026-10-03",
            explicit_inputs={"plan_unit_cost":{"value":{"2025":42000000,"2028":44000000},
                                              "unit":"KRW/occurrence/year"},
                             "recurrence_interval_years":3})
        self.assertEqual(estimate_routed_item(p).annual_amounts_thousand,(42000,0,0,44000,0))
        for change in ({"start_year":None},
                       {"explicit_inputs":{**p["explicit_inputs"],"recurrence_interval_years":1}},
                       {"explicit_inputs":{**p["explicit_inputs"],"growth_rate":.02}},
                       {"explicit_inputs":{**p["explicit_inputs"],"plan_unit_cost":{"value":{"2025":-1,"2028":44000000}}}}):
            with self.assertRaises(ValueError):
                estimate_routed_item({**p,**change})

    def test_cycle_candidate_preserves_explicit_cycle_and_hearing_scope(self):
        items=[dict(routeKey="research_plan",itemIndex=0,explicitInputs={
            "recurrence_interval_years":dict(value=3,source_ref="원문3년 계획")}),
            dict(routeKey="research_survey",itemIndex=1,explicitInputs={},calculation={}),
            dict(routeKey="goods_service_activity",itemIndex=2,explicitInputs={},calculation={})]
        articles=[dict(text="기본계획"),dict(text="기준 마련 및 조정 연구 조사"),dict(text="공청회 개최")]
        linked_research_cycle_candidates(items,articles)
        self.assertEqual(items[1]["recurrenceCandidates"][0]["value"],3)
        self.assertTrue(items[1]["recurrenceCandidates"][0]["requiresConfirmation"])
        self.assertEqual(items[1]["explicitInputs"],{})
        self.assertEqual(len(items[2]["scopeChecks"]),2)
        explicit=dict(items[1],explicitInputs={"recurrence_interval_years":{"value":1}})
        explicit.pop("recurrenceCandidates")
        linked_research_cycle_candidates([items[0],explicit],articles)
        self.assertNotIn("recurrenceCandidates",explicit)
