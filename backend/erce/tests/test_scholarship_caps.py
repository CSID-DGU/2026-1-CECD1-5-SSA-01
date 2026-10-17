import tempfile
import unittest
from pathlib import Path

from backend.erce.engine import estimate_routed_item
from backend.erce.scholarship_cap_evidence import (
    scholarship_cap_rows, reviewed_scholarship_bounds, reviewed_scholarship_point_estimate,
    reviewed_scholarship_cap_payload, COUNTS, BANDS, NATIONAL_MIX_2024,
)
from backend.erce.variable_evidence_store import save_variable_rows


class ScholarshipCapTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db = Path(self.folder.name) / "variables.sqlite3"
        save_variable_rows(scholarship_cap_rows(), self.db)

    def payload(self):
        return dict(route_key="transfer_recipient_delta", bill_no="2209533",
            start_year=2026, years=5, cutoff_date="2026-10-03", evidence_mode="development_review",
            variable_db_path=self.db, scholarship_calculation="tuition_capped_delta",
            scholarship_income_band="9", scholarship_cohort="existing_multichild_second",
            scholarship_program="multichild_first_second", scholarship_policy_reference_year=2025,
            university_kind="public_junior", scholarship_new_support_mode="capped",
            scholarship_support_confirmation_note="정답 확인 후 기존가구9구간 둘째 200만원 한도 시나리오 검증",
            scholarship_policy_projection="freeze_reference_policy",
            scholarship_policy_confirmation_note="2025년2학기 연간환산 상한을 추계기간 동결한 선례 가정; 미래 공식값 아님",
            selected_evidence_keys=["2209533:count:existing_multichild_second:9:2026-2030",
                "2209533:tuition:public_junior:2026-2030",
                "official:scholarship:2025:multichild_first_second:9",
                "official:scholarship:2025:third_plus:9"])

    def test_existing_band9_post_answer_regression(self):
        result = estimate_routed_item(self.payload())
        self.assertEqual(result.annual_amounts_thousand, (6540300,6466200,6392750,6320600,6248450))
        self.assertEqual([round(v/1000) for v in result.annual_amounts_thousand], [6540,6466,6393,6321,6248])
        # Individual printed answer rows use a different count/rounding precision;
        # compare the total without fabricating recipients to match rounded cells.
        self.assertAlmostEqual(sum(result.annual_amounts_thousand)/1000, 31968.3)

    def test_caps_do_not_exceed_actual_tuition(self):
        p = self.payload()
        p.update(scholarship_income_band="1-3", scholarship_new_support_mode="full_tuition",
            selected_evidence_keys=["2209533:tuition:public_junior:2026-2030",
                "official:scholarship:2025:multichild_first_second:1-3"],
            explicit_inputs={"recipient_count":{"value":100,"unit":"person","source_ref":"synthetic count"}})
        self.assertEqual(estimate_routed_item(p).annual_amounts_thousand, (0,)*5)

    def test_scope_year_self_confirmation_guards(self):
        p = self.payload()
        for changes, message in (({"evidence_mode":"holdout"},"target answer"),
            ({"scholarship_cohort":"new_two_child_second"},"scholarship_cohort mismatch"),
            ({"university_kind":"private_general"},"university_kind mismatch"),
            ({"scholarship_policy_projection":""},"year mismatch"),
            ({"scholarship_support_confirmation_note":""},"constraint"),
            ({"scholarship_new_support_mode":"unknown"},"support mode")):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError,message):
                estimate_routed_item({**p, **changes})
        with self.assertRaisesRegex(ValueError,"program mismatch"):
            # Use no DB rows to verify the computation gate itself, rather
            # than relying solely on row metadata matching.
            estimate_routed_item({**p,"selected_evidence_keys":[],"scholarship_program":"type1"})

    def test_no_missing_or_duplicate_units_filled(self):
        p=self.payload()
        p["selected_evidence_keys"] = [k for k in p["selected_evidence_keys"] if ":tuition:" not in k]
        with self.assertRaisesRegex(ValueError,"missing ERCE"):
            estimate_routed_item(p)
        for key, value, unit in (("payments_per_year",2,"payment/year"),
                                 ("annual_tuition",2000000,"KRW/person/semester")):
            bad=self.payload()
            bad["explicit_inputs"]={key:dict(value=value,unit=unit,source_ref="synthetic bad")}
            with self.subTest(key=key), self.assertRaises(ValueError):
                estimate_routed_item(bad)

    def test_unknown_university_mix_is_bounds_not_fitted_average(self):
        report = reviewed_scholarship_bounds(self.db)
        for low, gold, high in zip(report["lower_bound_thousand"], report["gold_annual_million"],
                                   report["upper_bound_thousand"]):
            self.assertLessEqual(low, gold*1000)
            self.assertGreaterEqual(high, gold*1000)
        self.assertEqual(sum(report["existing_band9_thousand"]),31968300)

    def test_complete_reference_scenario_with_declared_mix(self):
        report = reviewed_scholarship_point_estimate(self.db,policy_scenario="answer_table_reference")
        self.assertEqual(report["annual_amounts_thousand"],
                         [1539849176,1544763108,1549827752,1554530036,1559039712])
        self.assertEqual(report["missing_calculation_inputs"], [])
        self.assertEqual(len(report["components"]),32)
        self.assertAlmostEqual(sum(report["university_shares"].values()),1)
        for cohort, groups in COUNTS.items():
            for band, expected in zip(BANDS, groups):
                parts=[c for c in report["components"] if c["cohort"]==cohort and c["income_band"]==band]
                for i,count in enumerate(expected):
                    self.assertAlmostEqual(sum(c["allocated_recipients"][i] for c in parts),count)
        self.assertAlmostEqual(report["total_absolute_error_percent"],2.753421990981635)

    def test_policy_uncertainty_is_separate_scenarios_not_best_fit(self):
        full=reviewed_scholarship_point_estimate(self.db,policy_scenario="all_second_full_tuition")
        cap=reviewed_scholarship_point_estimate(self.db,policy_scenario="third_child_schedule_extension")
        self.assertEqual(full["total_thousand"],7987588060)
        self.assertEqual(cap["total_thousand"],5227644041)
        with self.assertRaisesRegex(ValueError,"selected explicitly"):
            reviewed_scholarship_point_estimate(self.db,policy_scenario="closest_to_gold")

    def test_mix_requires_confirmation_and_cannot_be_allocated_twice(self):
        p=reviewed_scholarship_cap_payload(self.db,"existing_multichild_second","9","private_general")
        key="official:nabo:university_mix:2024:general_junior"
        p["selected_evidence_keys"].append(key)
        p.update(scholarship_population_allocation="national_mix_proxy",
                 scholarship_recipient_count_scope="cohort_total",
                 evidence_selection_reasons={key:"synthetic comparable mix confirmation"})
        with self.assertRaisesRegex(ValueError,"mix needs applicability confirmation"):
            estimate_routed_item(p)
        p["scholarship_mix_confirmation_note"]="synthetic explicit confirmation"
        self.assertTrue(all(v>=0 for v in estimate_routed_item(p).annual_amounts_thousand))
        with self.assertRaisesRegex(ValueError,"unsplit cohort"):
            estimate_routed_item({**p,"scholarship_recipient_count_scope":"university_type_allocated"})
        bad={**p,"explicit_inputs":{"scholarship_university_mix":dict(
            value={**NATIONAL_MIX_2024,"private_junior":-1},unit="person",source_ref="synthetic invalid")}}
        with self.assertRaisesRegex(ValueError,"invalid scholarship university"):
            estimate_routed_item(bad)
