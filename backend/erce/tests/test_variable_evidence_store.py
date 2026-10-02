from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.erce.engine import estimate_routed_item
from backend.erce.reviewed_variable_rows import reviewed_variable_rows, burial_comparable_rows
from backend.erce.interagency_meeting_evidence import interagency_meeting_rows, unification_council_annual_rows
from backend.erce.legislative_committee_evidence import legislative_committee_rows, policy_review_committee_rows, POLICY_REVIEW_STAFF_GRADES
from backend.erce.transfer_payment_evidence import transfer_payment_rows, veteran_allowance_rows
from backend.erce.insurance_premium_evidence import insurance_premium_rows
from backend.erce.spouse_leave_evidence import spouse_leave_rows
from backend.erce.village_enterprise_evidence import village_enterprise_rows
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

    def test_spouse_leave_pre_cutoff_sources_require_explicit_cap_scenario(self):
        save_variable_rows(spouse_leave_rows(), self.path)
        keys = ["official:kostat:medium_births:2025-2029",
                "official:nabo:spouse_leave_recipients:2022",
                "official:kostat:births:2022",
                "official:moel:spouse_leave_cap_5days:2024"]
        base = dict(bill_no="2200258", cutoff_date="2024-06-10", start_year=2025,
                    years=5, evidence_mode="holdout", variable_db_path=str(self.path),
                    route_path=["이전지출", "개인지원", "배우자출산휴가급여기간확대"],
                    selected_evidence_keys=keys,
                    explicit_inputs={"funded_days_before":5, "funded_days_after":20,
                                     "reference_days":5})
        with self.assertRaisesRegex(ValueError, "constraint is not an automatic payment"):
            estimate_routed_item(base)
        scenario = {**base, "use_upper_limit_as_scenario":True,
                    "upper_limit_scenario_note":"2024년 5일 상한액을 2025~2029년에도 동일하게 적용하는 최대지급 시나리오"}
        result = estimate_routed_item(scenario)
        self.assertEqual(result.formula_key, "TRANSFER_SPOUSE_LEAVE_EXTENSION_V1")
        self.assertEqual(result.annual_amounts_thousand,
                         (17054509, 17915058, 18697375, 19401460, 20105545))
        self.assertEqual(round(sum(result.annual_amounts_thousand)/100000), 932)
        with self.assertRaisesRegex(ValueError, "future"):
            estimate_routed_item({**scenario, "cutoff_date":"2023-12-01"})

    def test_village_enterprise_partial_estimate_is_answer_only(self):
        save_variable_rows(village_enterprise_rows(), self.path)
        base = dict(bill_no="2200039", cutoff_date="2024-07-02",
                    start_year=2026, years=5, evidence_mode="development_review",
                    variable_db_path=str(self.path))
        plan_keys = ["2200039:mois_plan_research_unit_cost:2021-2023",
                     "2200039:plan_cpi_rates:2024-2030",
                     "2200039:plan_base_year:2023"]
        plan = estimate_routed_item({**base,
            "route_path":["물건비", "연구용역", "기본계획"],
            "selected_evidence_keys":plan_keys,
            "explicit_inputs":{"recurrence_interval_years":5}})
        committee = estimate_routed_item({**base,
            "route_path":["물건비", "위원회", "구성요소입력"],
            "selected_evidence_keys":["2200039:central_committee_components:2026-2030"]})
        self.assertEqual(plan.annual_amounts_thousand, (217543, 0, 0, 0, 0))
        self.assertEqual(committee.annual_amounts_thousand, (14000,) * 5)
        self.assertEqual(round((sum(plan.annual_amounts_thousand)
                                + sum(committee.annual_amounts_thousand)) / 1000), 288)
        with self.assertRaisesRegex(ValueError, "future"):
            estimate_routed_item({**base, "cutoff_date":"2024-05-30",
                "route_key":"research_plan", "selected_evidence_keys":plan_keys,
                "explicit_inputs":{"recurrence_interval_years":5}})
        with self.assertRaisesRegex(ValueError, "target answer"):
            estimate_routed_item({**base, "evidence_mode":"holdout",
                "route_key":"committee_components",
                "selected_evidence_keys":["2200039:central_committee_components:2026-2030"]})
        future = {**base, "bill_no":"NEW_MOIS_PLAN", "cutoff_date":"2024-08-01",
                  "evidence_mode":"holdout", "route_key":"research_plan",
                  "selected_evidence_keys":plan_keys[:1],
                  "explicit_inputs":{"recurrence_interval_years":5}}
        with self.assertRaisesRegex(ValueError, "applicability reason"):
            estimate_routed_item(future)
        later = estimate_routed_item({**future, "evidence_selection_reasons":{
            plan_keys[0]:"같은 행정안전부의 5년 종합계획 연구용역이며 과업범위·규모를 검토함"}})
        self.assertEqual(later.annual_amounts_thousand, (203000, 0, 0, 0, 0))

    def test_transfer_adjusted_population_preserves_first_run_and_answer_cutoff(self):
        save_variable_rows(transfer_payment_rows(), self.path)
        answer_keys = ["2200563:excluded_recipients:2024",
                       "2200563:additional_recipients:2024"]
        self.assertEqual(find_variable_candidates(
            cutoff_date="2024-06-18", variable_key="excluded_recipients",
            target_bill_no="2200563", evidence_mode="development_review",
            db_path=self.path, start_year=2024, years=1), [])
        base = dict(bill_no="2200563", start_year=2024, years=1,
                    cutoff_date="2024-06-18", variable_db_path=str(self.path),
                    route_path=["이전지출", "개인지원", "일반급여"],
                    selected_evidence_keys=["mois:registered_population:2024-05"],
                    explicit_inputs={"benefit_per_recipient":250000, "payments_per_year":1})
        self.assertEqual(estimate_routed_item(base).annual_amounts_thousand, (12819336750,))
        adjusted = {**base, "cutoff_date":"2024-07-11", "evidence_mode":"development_review",
                    "route_path":["이전지출", "개인지원", "대상인구가감급여"],
                    "selected_evidence_keys":["mois:base_population:2024-05", *answer_keys]}
        result = estimate_routed_item(adjusted)
        self.assertEqual(result.annual_amounts_thousand, (13322742750,))
        for changes, reason in (
            ({"cutoff_date":"2024-06-18"}, "future"),
            ({"evidence_mode":"holdout"}, "target answer"),
            ({"bill_no":"NEW"}, "different target"),
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, reason):
                estimate_routed_item({**adjusted, **changes})

        synthetic = dict(route_key="transfer_recipient_adjusted", start_year=2024, years=1,
                         explicit_inputs={"base_population":100, "excluded_recipients":10,
                                          "additional_recipients":5, "benefit_per_recipient":1000})
        self.assertEqual(estimate_routed_item(synthetic).annual_amounts_thousand, (95,))
        with self.assertRaisesRegex(ValueError, "excluded_recipients"):
            estimate_routed_item({**synthetic, "explicit_inputs":{
                **synthetic["explicit_inputs"], "excluded_recipients":101}})
        with self.assertRaisesRegex(ValueError, "missing ERCE formula variables"):
            estimate_routed_item({**synthetic, "explicit_inputs":{
                "base_population":100, "benefit_per_recipient":1000}})

    def test_farmer_allowance_post_answer_reconstruction_is_not_holdout(self):
        save_variable_rows(transfer_payment_rows(), self.path)
        keys = ["2200431:recipient_count:2026-2030",
                "2200431:benefit_per_recipient:2026-2030",
                "2200431:subsidy_rate:2026-2030"]
        payload = dict(bill_no="2200431", route_path=["이전지출", "수급자기반국비분담"],
                       start_year=2026, years=5, cutoff_date="2024-07-05",
                       evidence_mode="development_review", variable_db_path=str(self.path),
                       selected_evidence_keys=keys)
        result = estimate_routed_item(payload)
        self.assertEqual(result.formula_key, "TRANSFER_RECIPIENT_SUBSIDY_V1")
        self.assertEqual(sum(result.annual_amounts_thousand), 32525195178)
        gross = estimate_routed_item({**payload,
            "route_path":["이전지출", "개인지원", "일반급여"],
            "selected_evidence_keys":keys[:2]})
        self.assertEqual(sum(gross.annual_amounts_thousand), 65050390356)
        for changes, reason in (({"cutoff_date":"2024-06-13"}, "future"),
                                ({"evidence_mode":"holdout"}, "target answer"),
                                ({"bill_no":"NEW"}, "different target")):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, reason):
                estimate_routed_item({**payload, **changes})
        lower_bound = estimate_routed_item(dict(
            route_path=["이전지출", "수급자기반국비분담"], years=1,
            explicit_inputs={"recipient_count":100, "benefit_per_recipient":1000,
                             "subsidy_rate":0.4}))
        self.assertEqual(lower_bound.annual_amounts_thousand, (40,))
        for bad_inputs, variable in (({"subsidy_rate":1.1}, "subsidy_rate"),
                                     ({"recipient_count":[100, 200]}, "recipient_count")):
            with self.subTest(bad_inputs=bad_inputs), self.assertRaisesRegex(ValueError, variable):
                estimate_routed_item({"route_key":"transfer_recipient_subsidy", "years":1,
                    "explicit_inputs":{"recipient_count":100, "benefit_per_recipient":1000,
                                       "subsidy_rate":0.4, **bad_inputs}})

    def test_veteran_allowance_split_and_post_answer_gates(self):
        save_variable_rows(veteran_allowance_rows(), self.path)
        base = dict(bill_no="2200169", start_year=2025, years=5,
                    cutoff_date="2024-08-09", evidence_mode="development_review",
                    variable_db_path=str(self.path))
        def run(route, suffixes, **extra):
            return estimate_routed_item({**base, "route_key":route,
                "selected_evidence_keys":[f"2200169:{suffix}:2025-2029" for suffix in suffixes],
                **extra})
        components = {}
        for level in (32, 60):
            benefit = f"new_monthly_benefit_{level}pct"
            shared = dict(benefit_scenario=f"{level}pct",
                          explicit_inputs={"payments_per_year":12})
            components[level] = [
                run("transfer_recipient", ["concurrent_new_recipients", benefit], **shared),
                run("transfer_recipient_delta", ["existing_recipients", benefit,
                                                 "existing_monthly_benefit"], **shared),
                run("transfer_recipient", ["surviving_spouses", benefit], **shared),
            ]
        self.assertEqual(components[32][1].formula_key, "TRANSFER_RECIPIENT_DELTA_V1")
        medical = [run("transfer_service_use",
                       [f"{channel}_{part}" for part in ("recipients", "visits", "cost_per_visit")],
                       care_channel=channel)
                   for channel in ("veterans_hospital", "contract_hospital")]
        transport = estimate_routed_item({**base, "route_key":"transfer_recipient",
            "selected_evidence_keys":["2200169:transport_recipients:2025-2029",
                                      "2200169:transport_unit_cost:2023"]})
        for level, gold_eok in ((32, 74886), (60, 160000)):
            predicted_thousand = sum(sum(r.annual_amounts_thousand)
                                     for r in [*components[level], *medical, transport])
            self.assertLess(abs(predicted_thousand - gold_eok * 100000), 25 * 100000)
        blocked = {**base, "route_key":"transfer_recipient_delta",
                   "selected_evidence_keys":["2200169:existing_recipients:2025-2029",
                                             "2200169:new_monthly_benefit_32pct:2025-2029",
                                             "2200169:existing_monthly_benefit:2025-2029"],
                   "benefit_scenario":"32pct", "explicit_inputs":{"payments_per_year":12}}
        for changes, reason in (({"cutoff_date":"2024-06-05"}, "future"),
                                ({"evidence_mode":"holdout"}, "target answer"),
                                ({"benefit_scenario":"60pct"}, "scenario")):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, reason):
                estimate_routed_item({**blocked, **changes})
        with self.assertRaisesRegex(ValueError, "care_channel"):
            run("transfer_service_use", ["veterans_hospital_recipients",
                "contract_hospital_visits", "veterans_hospital_cost_per_visit"],
                care_channel="veterans_hospital")
        with self.assertRaisesRegex(ValueError, "missing ERCE formula variables"):
            estimate_routed_item({"bill_no":"2200169", "route_key":"transfer_recipient_delta",
                                  "start_year":2025, "years":5, "cutoff_date":"2024-06-05"})
        comparable = dict(bill_no="NEW", route_key="transfer_recipient", start_year=2025,
                          years=1, cutoff_date="2024-08-09", variable_db_path=str(self.path),
                          selected_evidence_keys=["2200169:transport_unit_cost:2023"],
                          explicit_inputs={"recipient_count":1})
        with self.assertRaisesRegex(ValueError, "applicability reason"):
            estimate_routed_item(comparable)
        accepted = estimate_routed_item({**comparable, "evidence_selection_reasons":{
            "2200169:transport_unit_cost:2023":"같은 국가보훈부 수송할인 범위와 2023년 단가 연도 확인"}})
        self.assertEqual(accepted.annual_amounts_thousand, (90,))

    def test_insurance_premium_subsidy_delta_keeps_national_and_local_signs(self):
        save_variable_rows(insurance_premium_rows(), self.path)
        base = dict(bill_no="2200116", route_path=["이전지출", "보험료지원", "기준선차감"],
                    cutoff_date="2024-06-14", start_year=2025, years=5,
                    evidence_mode="development_review", variable_db_path=str(self.path))
        totals = [0] * 5
        for line in ("crop", "livestock", "aquaculture"):
            for payer in ("national", "local"):
                keys = [f"2200116:{line}:premium_base:2024",
                        f"2200116:{line}:{payer}:existing_support_amount:2024",
                        f"2200116:{payer}:new_support_rate:2025-2029"]
                if line == "crop":
                    keys += ["2200116:crop:growth_rates_by_year:2025-2029",
                             "2200116:crop:base_year:2024"]
                payload = {**base, "insurance_line":line, "payer":payer,
                           "selected_evidence_keys":keys}
                result = estimate_routed_item(payload)
                self.assertEqual(result.formula_key, "TRANSFER_PREMIUM_SUBSIDY_DELTA_V1")
                if payer == "local" and line != "livestock":
                    self.assertTrue(all(value < 0 for value in result.annual_amounts_thousand))
                totals = [a+b for a,b in zip(totals, result.annual_amounts_thousand)]
                if line == "crop" and payer == "national":
                    for changes, reason in (({"cutoff_date":"2024-06-04"}, "future"),
                                            ({"evidence_mode":"holdout"}, "target answer"),
                                            ({"payer":"local"}, "payer"),
                                            ({"insurance_line":"livestock"}, "insurance_line")):
                        with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, reason):
                            estimate_routed_item({**payload, **changes})
        self.assertEqual([round(value/1000) for value in totals],
                         [98195, 101039, 104150, 107554, 111278])
        self.assertLess(abs(sum(totals) - 522216000), 2_000)
        with self.assertRaisesRegex(ValueError, "missing ERCE formula variables"):
            estimate_routed_item({"bill_no":"2200116", "route_key":"transfer_premium_subsidy_delta",
                                  "cutoff_date":"2024-06-04", "start_year":2025, "years":5,
                                  "explicit_inputs":{"new_support_rate":.7}})

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
