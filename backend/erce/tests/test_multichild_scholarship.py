import tempfile
import unittest
from pathlib import Path
from backend.erce.engine import estimate_routed_item
from backend.erce.multichild_scholarship_evidence import (
    GROUP, multichild_scholarship_rows, reviewed_multichild_payloads,
)
from backend.erce.variable_evidence_store import save_variable_rows, find_variable_candidates


class MultichildScholarshipTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.db=Path(self.folder.name)/"variables.sqlite3"
        save_variable_rows(multichild_scholarship_rows(),self.db)

    def test_eight_bands_annual_delta_regression(self):
        results=[estimate_routed_item(p) for p in reviewed_multichild_payloads(self.db)]
        totals=[sum(r.annual_amounts_thousand[i] for r in results) for i in range(5)]
        self.assertEqual(totals,[163754073,160642159,157587709,154596304,151660775])
        self.assertLess(abs(sum(totals)/100000-7884)/7884,.001)
        self.assertTrue(all(r.formula_key=="TRANSFER_RECIPIENT_DELTA_V1" for r in results))
        self.assertTrue(all(r.resolved_variables["recipient_count"].source_class=="calculated_estimate" for r in results))

    def test_population_band_policy_self_and_confirmation_gates(self):
        p=reviewed_multichild_payloads(self.db)[0]
        for changes,message in (({"evidence_mode":"holdout"},"target answer"),
            ({"scholarship_income_band":2},"scholarship_income_band mismatch"),
            ({"scholarship_population_group":"third_child"},"scholarship_population_group mismatch"),
            ({"scholarship_policy_reference_year":2026},"scholarship_policy_reference_year mismatch"),
            ({"cutoff_date":"2024-08-23"},"future"),
            ({"scholarship_projection_confirmation_note":""},"confirmation")):
            with self.subTest(changes=changes),self.assertRaisesRegex(ValueError,message):
                estimate_routed_item({**p,**changes})
        bad={**p,"selected_evidence_keys":[k for k in p["selected_evidence_keys"] if "student_growth" not in k]}
        with self.assertRaisesRegex(ValueError,"annual_population_growth_rate"):
            estimate_routed_item(bad)

    def test_new_similar_population_reuse_requires_recorded_reason(self):
        p=reviewed_multichild_payloads(self.db)[0]
        candidates=find_variable_candidates(target_bill_no="new",cutoff_date="2026-10-03",db_path=self.db)
        self.assertTrue(any(row["variable_key"]=="base_recipient_count" for row in candidates))
        new={**p,"bill_no":"new","evidence_mode":"holdout"}
        with self.assertRaisesRegex(ValueError,"applicability reason"):
            estimate_routed_item(new)
        new["evidence_selection_reasons"]={key:"같은2024년1학기1소득구간 첫째·둘째 대상 및 기존 정책의 조건부 비교 시나리오" for key in new["selected_evidence_keys"]}
        self.assertEqual(estimate_routed_item(new).annual_amounts_thousand,
                         estimate_routed_item(p).annual_amounts_thousand)
        explicit={**new,"explicit_inputs":{"recipient_count":{"value":100,"unit":"person","source_ref":"synthetic new target"}}}
        self.assertEqual(estimate_routed_item(explicit).annual_amounts_thousand,(121000,)*5)

    def test_annual_units_no_duplicate_growth_or_semesters(self):
        p=reviewed_multichild_payloads(self.db)[0]
        for key,value,unit,message in (
            ("benefit_per_recipient",6269000,"KRW/person/semester","annual mean"),
            ("payments_per_year",2,"payment/year","semesters"),
            ("growth_rate",-.019,"ratio","reapplied"),
            ("annual_population_growth_rate",-1,"ratio/year","range")):
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,message):
                estimate_routed_item({**p,"explicit_inputs":{key:{"value":value,"unit":unit,"source_ref":"synthetic invalid"}}})
        scope=[r for r in multichild_scholarship_rows() if r["variable_key"]=="scholarship_scope_rule"][0]
        self.assertEqual(scope["value"]["unestimated_income_bands"],[9,10])
        self.assertEqual(scope["value"]["estimated_birth_orders"],[1,2])
