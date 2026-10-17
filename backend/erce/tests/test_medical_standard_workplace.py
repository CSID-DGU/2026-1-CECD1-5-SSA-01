import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from backend.erce.medical_standard_workplace import medical_workplace_rows
from backend.erce.standard_workplace_evidence import standard_workplace_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows,validate_non_estimation_review
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_medical_workplace import medical_payload,formal_review
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


class MedicalStandardWorkplaceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.db=Path(temp.name)/"test.sqlite3"
        save_variable_rows(medical_workplace_rows()+standard_workplace_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2204655"],self.db)

    def generic(self):
        return {**medical_payload(False),"bill_no":"NEW_MEDICAL_STANDARD_WORKPLACE","evidence_mode":"holdout"}

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_source_cumulative_replay_and_new_case_guard(self):
        r=estimate_routed_item({**medical_payload(),"variable_db_path":str(self.db)})
        self.assertEqual([round(v/1000) for v in r.annual_amounts_thousand],[612,1248,1910,2598,3312])
        with self.assertRaises(ValueError):self.calculate({**self.generic(),"medical_support_mode":"cumulative_support_reference"})
        r=self.calculate(self.generic())
        self.assertEqual(r["estimatePurpose"],"reference_scenario")
        self.assertTrue(all(t["supported_workplaces"]==2 for t in r["derivationTrace"]))

    def test_previous_shared_price_is_not_blocked_by_investor_tag(self):
        p=self.generic()
        p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if "standard_grant_unit" not in k]+["2200200:standard_grant_unit:reviewed"]
        p["evidence_selection_reasons"]["2200200:standard_grant_unit:reviewed"]="동일설립지원평균단가의2024버전준용, 설립주체와가격과업구분"
        p["standard_grant_price_year"]=2024
        self.assertEqual(self.calculate(p)["status"],"computed_review")

    def test_formal_non_estimation_not_replaced_by_reference_number(self):
        p={**formal_review(),"bill_no":"NEW_MEDICAL_STANDARD_WORKPLACE","evidence_mode":"holdout"}
        r=validate_non_estimation_review(p,db_path=self.db)
        self.assertEqual(r["decision"],"not_estimated")
        self.assertEqual(r["source_decision_label"],"미첨부3호")
        self.assertIsNone(r["amount"])
        p["decision_facts"]["actual_new_application_volume_confirmed"]=True
        with self.assertRaises(ValueError):validate_non_estimation_review(p,db_path=self.db)

    def test_budget_and_reference_approval_required(self):
        for change,key in [({"budget_expansion_assumed":False},"medical_budget_retention_confirmation"),
                           ({"medical_reference_confirmed":False},"medical_workplace_reference_confirmation")]:
            r=self.calculate({**self.generic(),**change})
            self.assertIn(key,r["missingDerivationVariables"])

    def test_draft_keeps_reference_scenario_label(self):
        from backend.erce.draft_report import generate_draft
        p=self.generic();r=self.calculate(p)
        with patch("backend.erce.draft_report.calculate_erce_web_item",return_value=r):
            draft=generate_draft(dict(start_year=2026,years=5,bill_name="의료법인 참고검증",items=[p]))
        self.assertIn("참고 시나리오",draft["summary"])
        self.assertIn("공식미첨부 판단과 별도",draft["markdown"])
        self.assertEqual(draft["items"][0]["estimatePurpose"],"reference_scenario")
