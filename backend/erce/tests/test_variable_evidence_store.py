from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.erce.engine import estimate_routed_item
from backend.erce.reviewed_variable_rows import reviewed_variable_rows, burial_comparable_rows
from backend.erce.interagency_meeting_evidence import interagency_meeting_rows, unification_council_annual_rows
from backend.erce.legislative_committee_evidence import legislative_committee_rows, policy_review_committee_rows, POLICY_REVIEW_STAFF_GRADES
from backend.erce.variable_evidence_store import save_variable_rows, find_variable_candidates


class VariableEvidenceStoreTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "evidence.sqlite3"
        self.rows = (reviewed_variable_rows() + burial_comparable_rows()
                     + interagency_meeting_rows() + unification_council_annual_rows()
                     + legislative_committee_rows() + policy_review_committee_rows())
        save_variable_rows(self.rows, self.path)

    def payload(self, bill, route, start, keys, **extra):
        return dict(bill_no=bill, route_key=route, start_year=start, years=5,
            cutoff_date="2026-09-27", evidence_mode="development_review",
            variable_db_path=str(self.path), selected_evidence_keys=keys, **extra)

    def test_missing_four_cases_calculate_from_saved_ids_not_inline_gold_values(self):
        cases = [
            ("2212780", "legal_notification", 2027,
             ["2212780:annual_case_count:2027-2031", "2212780:action_rate:2025", "2212780:notices_per_case:2025", "2212780:notice_unit_price:2025"], {}, 1742190),
            ("2203298", "diagnostic_test_subsidy", 2026,
             ["2203298:annual_recipients:2026-2030", "2203298:existing_annual_cost:2026-2030", "2203298:test_unit_cost:2024"], {}, 18014200),
            ("2200093", "information_system_project_plan", 2025,
             ["2200093:annual_project_budget:2025-2029"], {"budget_start_year":2025}, 19111000),
            ("2215482", "non_tax_fee_channel_shift", 2027,
             [f"2215482:{key}:2026" for key in ("historical_annual_fee_revenues", "other_channel_base_revenue", "other_channel_base_year", "other_channel_growth_rate", "channel_shift_rate")],
             {"explicit_inputs":{"exemption_rate":1}}, 383112139),
        ]
        for bill, route, start, keys, extra, total in cases:
            with self.subTest(bill=bill):
                payload = self.payload(bill, route, start, keys, **extra)
                result = estimate_routed_item(payload)
                self.assertEqual(sum(result.annual_amounts_thousand), total)
                self.assertEqual(result.evidence_mode, "development_review")
                self.assertEqual(result.evidence_key, ",".join(keys))
                with self.assertRaisesRegex(ValueError, "target answer"):
                    estimate_routed_item({**payload, "evidence_mode":"holdout"})
        plan = estimate_routed_item(self.payload("2203298", "research_plan", 2026,
            ["borderline_intelligence_plan_2024_10_22:plan_unit_cost"],
            explicit_inputs={"recurrence_interval_years":5}))
        survey = estimate_routed_item(self.payload("2203298", "research_survey", 2026,
            ["borderline_intelligence_survey_2024_10_22:survey_unit_cost",
             "2203298:first_occurrence_offset_years:2026"],
            explicit_inputs={"recurrence_interval_years":3}))
        self.assertEqual(survey.annual_amounts_thousand,(0,300000,0,0,300000))
        self.assertEqual(sum(plan.annual_amounts_thousand)+sum(survey.annual_amounts_thousand)+18014200,18684200)

    def test_target_quantities_and_project_budgets_never_become_other_target_unit_prices(self):
        for key in ("2200093:annual_project_budget:2025-2029", "2212780:annual_case_count:2027-2031"):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "different target"):
                estimate_routed_item(self.payload("NEW", "quantity_unit", 2025, [key]))
        candidates = find_variable_candidates(cutoff_date="2026-09-27", variable_key="annual_project_budget",
            target_bill_no="NEW", evidence_mode="development_review", db_path=self.path)
        self.assertEqual(candidates, [])

    def test_future_year_and_unknown_id_guards(self):
        base = self.payload("2211932", "burial_supplies", 2026,
            ["2212347:new_death_burial_quantity:2026-2030", "2212347:burial_supplies_unit_cost:2026-2030"])
        self.assertNotIn(None, estimate_routed_item(base).annual_amounts_thousand)
        for changed, reason in (({"cutoff_date":"2025-09-03"}, "future"),
                                ({"start_year":2027}, "year mismatch"),
                                ({"selected_evidence_keys":["unknown"]}, "unknown")):
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, reason):
                estimate_routed_item({**base, **changed})

    def test_caps_are_constraints_not_automatic_amounts(self):
        with self.assertRaisesRegex(ValueError, "not an automatic payment"):
            estimate_routed_item(self.payload("NEW", "quantity_unit", 2026,
                ["central_government_meeting_allowance_limit_2026"]))

    def test_explicit_values_override_selected_assumptions(self):
        payload = self.payload("NEW", "burial_supplies", 2026,
            ["2212347:new_death_burial_quantity:2026-2030", "2212347:burial_supplies_unit_cost:2026-2030"],
            explicit_inputs={"quantity":1,"unit_cost":1000})
        result = estimate_routed_item(payload)
        self.assertEqual(result.annual_amounts_thousand, (1,)*5)

    def test_idempotent_save_does_not_duplicate_rows(self):
        save_variable_rows(self.rows, self.path)
        candidates = find_variable_candidates(cutoff_date="2026-09-27", agency="국가보훈부",
            policy_domain="국립묘지", target_bill_no="2211932", start_year=2026, db_path=self.path)
        self.assertEqual(len(candidates),4)

    def test_cross_domain_comparables_require_ai_applicability_note(self):
        payload = self.payload("NEW", "quantity_unit", 2026,
            ["2212347:new_death_burial_quantity:2026-2030", "2212347:burial_supplies_unit_cost:2026-2030"],
            policy_domain="다른대상")
        with self.assertRaisesRegex(ValueError, "scope mismatch"):
            estimate_routed_item(payload)
        result = estimate_routed_item({**payload, "evidence_selection_reasons":{
            key:"테스트용: 같은 안장업무·동일 규모의 대상 집단" for key in payload["selected_evidence_keys"]}})
        self.assertNotIn(None,result.annual_amounts_thousand)

    def test_backlog_requires_law_applicability_not_comparable_similarity(self):
        payload = self.payload("NEW", "burial_supplies", 2026,
            ["2212347:burial_quantity:2026-2030", "2212347:burial_supplies_unit_cost:2026-2030"])
        with self.assertRaisesRegex(ValueError, "retroactive application"):
            estimate_routed_item(payload)
        result = estimate_routed_item({**payload, "retroactive_application":{
            "enabled":True, "source_ref":"합성 법안: 부칙 소급적용 조항 확인"}})
        self.assertNotIn(None,result.annual_amounts_thousand)

    def test_corrected_burial_uses_other_bill_new_death_counts_without_target_gold(self):
        amounts = []
        for route, price in (("burial_supplies","burial_supplies_unit_cost"),
                             ("burial_plot_construction","burial_plot_unit_cost")):
            payload = self.payload("2211932",route,2026,
                ["2212347:new_death_burial_quantity:2026-2030", f"2212347:{price}:2026-2030"])
            result = estimate_routed_item({**payload,"evidence_mode":"holdout"})
            self.assertEqual(result.evidence_mode,"holdout")
            amounts.append(sum(result.annual_amounts_thousand))
        self.assertEqual(sum(amounts),213466)

    def test_array_formula_rejects_bad_lengths_negative_and_nan(self):
        for quantity in ([1], [-1]*5, [float("nan")]*5, [True]*5):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                estimate_routed_item(dict(route_key="quantity_unit", years=5,
                    explicit_inputs={"quantity":quantity,"unit_cost":1000}))

    def test_same_unit_but_different_service_rate_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"service/formula mismatch"):
            estimate_routed_item(self.payload("2211932","burial_supplies",2026,
                ["2212347:new_death_burial_quantity:2026-2030", "2212347:burial_plot_unit_cost:2026-2030"]))

    def test_interagency_meeting_first_result_stays_separate_from_annual_budget_fix(self):
        event_keys=["2214485:interagency_meeting_unit_cost:2024", "2214485:interagency_meeting_frequency:2026"]
        first=estimate_routed_item(self.payload("2200936","interagency_meeting_operation",2025,event_keys,
            explicit_inputs={"service_quantity":1}))
        self.assertEqual(first.annual_amounts_thousand,(48000,)*5)
        annual_keys=["2200936:unification_council_annual_budget:2024",
                     "2200936:unification_council_base_year:2024",
                     "2200936:consumer_price_forecast:2024-06-28"]
        payload=self.payload("2200936","interagency_annual_operation",2025,annual_keys)
        corrected=estimate_routed_item(payload)
        self.assertEqual(corrected.annual_amounts_thousand,(11038,11280,11517,11759,12006))
        self.assertEqual(corrected.evidence_mode,"development_review")
        with self.assertRaisesRegex(ValueError,"target answer"):
            estimate_routed_item({**payload,"evidence_mode":"holdout"})

    def test_annual_budget_not_treated_as_per_meeting_unit_rate(self):
        with self.assertRaisesRegex(ValueError,"service/formula mismatch"):
            estimate_routed_item(self.payload("2200936","interagency_meeting_operation",2025,
                ["2200936:unification_council_annual_budget:2024"]))
        with self.assertRaisesRegex(ValueError,"service/formula mismatch"):
            estimate_routed_item(self.payload("NEW","interagency_annual_operation",2025,
                ["2214485:interagency_meeting_unit_cost:2024"]))

    def test_annual_operation_forecast_and_priority_without_gold(self):
        result=estimate_routed_item(dict(route_key="interagency_annual_operation",start_year=2025,years=2,
            explicit_inputs={"annual_operating_amount":1000000},
            actual_inputs={"annual_operating_amount":9999999},
            official_inputs={"base_year":2024,"growth_rates_by_year":{"value":{"2025":.1,"2026":.2}}}))
        self.assertEqual(result.annual_amounts_thousand,(1100,1320))

    def test_committee_staff_model_checks_workload_not_just_word_committee(self):
        payload=self.payload("NEW","personnel_average",2026,
            ["2214994:legislative_support_headcount:2026","2212534:legislative_salary_per_person:2026-2030"],
            workload_features={"budget_settlement_pre_review":False})
        with self.assertRaisesRegex(ValueError,"workload mismatch"):
            estimate_routed_item(payload)
        accepted=estimate_routed_item({**payload,"workload_features":{"budget_settlement_pre_review":True}})
        self.assertEqual(sum(accepted.annual_amounts_thousand),4875454)

    def test_committee_salary_grade_profile_is_not_transferable_to_all_six_person_groups(self):
        base=self.payload("NEW","personnel_average",2027,
            ["2215199:policy_review_staff_model:2026","2215199:policy_review_salary_per_person:2027-2031"],
            workload_features={"budget_settlement_pre_review":False})
        with self.assertRaisesRegex(ValueError,"staff-grade composition mismatch"):
            estimate_routed_item(base)
        result=estimate_routed_item({**base,"staff_grade_profile":{k:v for k,v in POLICY_REVIEW_STAFF_GRADES.items() if v}})
        self.assertEqual(sum(result.annual_amounts_thousand),3330000)
        with self.assertRaisesRegex(ValueError,"staff-grade composition mismatch"):
            estimate_routed_item({**base,"staff_grade_profile":{"9급":6}})

    def test_policy_review_case_full_db_workflow_keeps_benchmark_operating_budget(self):
        base=dict(bill_no="2215199",start_year=2027,years=5,cutoff_date="2026-09-27",
            evidence_mode="development_review",variable_db_path=str(self.path),
            workload_features={"budget_settlement_pre_review":False},staff_grade_profile=POLICY_REVIEW_STAFF_GRADES)
        pay=estimate_routed_item({**base,"route_key":"personnel_average","selected_evidence_keys":[
            "2215199:policy_review_staff_model:2026","2215199:policy_review_salary_per_person:2027-2031"]})
        calculated={"annual_salary_amount":{"value":[v*1000 for v in pay.annual_amounts_thousand],
            "unit":"KRW/year","source_ref":"앞 단계 ERCE 보수 계산","is_assumption":True}}
        results=[pay]
        for route,key,extra in (
            ("personnel_employer_contribution","2215199:legislative_employer_rate:2027-2031",{"calculated_inputs":calculated}),
            ("personnel_basic_expense","2214994:legislative_basic_expense_ratio:2026",{"calculated_inputs":calculated}),
            ("personnel_asset","2215199:legislative_asset_per_person:2027",{"explicit_inputs":{"duration":1}}),
            ("legislative_committee_operation","2214994:legislative_annual_operating_budget:2026",{}),
        ):
            keys=[key]
            if route=="personnel_asset": keys.insert(0,"2215199:policy_review_staff_model:2026")
            if route=="legislative_committee_operation": keys.append("2214994:legislative_operating_growth:2026")
            results.append(estimate_routed_item({**base,"route_key":route,"selected_evidence_keys":keys,**extra}))
        self.assertEqual(sum(sum(r.annual_amounts_thousand) for r in results),4888206)
        self.assertEqual(results[1].resolved_variables["annual_salary_amount"].source_class,"calculated_estimate")
        self.assertTrue(results[1].resolved_variables["annual_salary_amount"].is_assumption)
        with self.assertRaisesRegex(ValueError,"target answer"):
            estimate_routed_item({**base,"route_key":"personnel_average","evidence_mode":"holdout",
                "selected_evidence_keys":["2215199:policy_review_staff_model:2026"]})

    def test_personnel_yearly_operands_reject_invalid_arrays_and_do_not_override_officials(self):
        for salaries in ([1000],[-1]*5,[float("nan")]*5):
            with self.subTest(salaries=salaries),self.assertRaises(ValueError):
                estimate_routed_item(dict(route_key="personnel_average",years=5,
                    explicit_inputs={"headcount":1,"salary_per_person":salaries}))
        result=estimate_routed_item(dict(route_key="personnel_employer_contribution",years=2,
            official_inputs={"annual_salary_amount":1000000,"employer_contribution_rate":.1},
            calculated_inputs={"annual_salary_amount":{"value":[999000,999000],"is_assumption":True}}))
        self.assertEqual(result.annual_amounts_thousand,(100,100))
        self.assertEqual(result.resolved_variables["annual_salary_amount"].source_class,"official_standard")


if __name__ == "__main__":
    unittest.main()
