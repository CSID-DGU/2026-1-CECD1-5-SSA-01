import copy
import tempfile
import unittest
from pathlib import Path
from backend.erce.regional_advocacy_committee import regional_advocacy_committee_rows
from backend.erce.scripts.check_regional_advocacy_committee import committee_payload
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.web_bridge import calculate_erce_web_item


class RegionalAdvocacyCommitteeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"evidence.sqlite3";save_variable_rows(regional_advocacy_committee_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["method_key"]=="2202038:regional_advocacy_case_scaled_committee"],self.db)
        self.p={**committee_payload(),"bill_no":"SYNTHETIC_REGIONAL_ADVOCACY","evidence_mode":"holdout"}
    def calc(self,p):return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_regional_rounding_cap_and_unrounded_cost_reproduce(self):
        r=self.calc(self.p);trace=r["derivationTrace"];n={t["region"]:t["paid_members"] for t in trace}
        self.assertEqual(n,{"서울":23,"부산":20,"대구":17,"인천":13,"광주":8,"대전":11,"울산":17,
            "세종":7,"경기":28,"강원":14,"충북":21,"충남":15,"전북":10,"전남":14,"경북":16,"경남":16,"제주":9})
        self.assertEqual(sum(n.values()),259);self.assertEqual(r["annualAmountsThousand"],[103600]*5)
        self.assertTrue(next(x for x in trace if x["region"]=="경기")["cap_applied"])

    def test_wrong_workload_rounding_paid_officials_and_own_answer_blocked(self):
        for change in ({"committee_workload_proxy":"central_committee"},{"committee_rounding":"floor"},
                       {"public_officials_paid":True},{"bill_no":"2202038"},{"cutoff_date":"2024-07-19"}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.calc({**self.p,**change})

    def test_zero_reference_cases_rejected_and_missing_allowance_stays_missing(self):
        p=copy.deepcopy(self.p);p["explicit_inputs"]={"reference_suspected_cases":dict(value=0,unit="case",source_ref="합성잘못된분모")}
        with self.assertRaises(ValueError):self.calc(p)
        p=copy.deepcopy(self.p);p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if "meeting_allowance" not in k]
        r=self.calc(p);self.assertEqual(r["status"],"needs_input");self.assertIn("meeting_allowance",r["missingDerivationVariables"])
