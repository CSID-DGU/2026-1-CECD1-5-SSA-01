import tempfile
import unittest
from pathlib import Path
from backend.erce.disabled_worker_wage_evidence import direct_worker_wage_rows, disabled_worker_wage_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_direct_worker_wage import direct_worker_payload,run_regression
from backend.erce.web_bridge import calculate_erce_web_item


class DirectWorkerWageTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.db=Path(temp.name)/"test.sqlite3"
        save_variable_rows(direct_worker_wage_rows()+disabled_worker_wage_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"] in {"2207871","2200664"}],self.db)

    def web(self,**updates):
        return calculate_erce_web_item({**direct_worker_payload(),"bill_no":"NEW_DIRECT_WORKER_GAP","evidence_mode":"holdout",**updates},variable_db_path=self.db)

    def test_three_scenarios_display_and_no_linked_bill_dependency(self):
        r=run_regression(self.db)
        self.assertEqual([p["annual_display_matches"] for p in r["parts"]],[5,5,5])
        self.assertTrue(all(p["error_percent"]<.03 for p in r["parts"]))
        self.assertEqual([round(p["total_eok"]) for p in r["parts"]],[990,1650,3299])
        trace=self.web()["derivationTrace"]
        self.assertTrue(all(t["monthly_hours"]==113.4 for t in trace))
        self.assertEqual([t["excluded_worker_count"] for t in trace],[9838,10180,10534,10899,11278])

    def test_model_mix_and_missing_history_blocked(self):
        with self.assertRaises(ValueError):
            self.web(worker_support_model="linked_minimum_wage_reform")
        keys=[k for k in direct_worker_payload()["selected_evidence_keys"] if "exempt_worker_history" not in k]
        self.assertIn("exempt_worker_history",self.web(selected_evidence_keys=keys)["missingDerivationVariables"])

    def test_forecast_vintage_explanation_and_year_coverage_required(self):
        self.assertIn("worker_forecast_vintage_confirmation",self.web(worker_forecast_vintage_note="")["missingDerivationVariables"])
        self.assertIn("minimum_wage_forecast_year_coverage",self.web(start_year=2031)["missingDerivationVariables"])

    def test_self_source_excluded_and_negative_gap_clamped(self):
        with self.assertRaises(ValueError):
            calculate_erce_web_item(direct_worker_payload(),variable_db_path=self.db)
        r=self.web(explicit_inputs={"facility_hourly_wage_history":dict(value=dict.fromkeys(map(str,range(2020,2025)),30000),unit="year_to_KRW/hour",source_ref="합성 최저시급이상 임금")})
        self.assertEqual(r["annualAmountsThousand"],[0]*5)
