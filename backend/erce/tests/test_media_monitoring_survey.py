import tempfile
import unittest
from pathlib import Path
from backend.erce.media_monitoring_survey_evidence import media_monitoring_survey_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_media_monitoring_survey import monitoring_payload, run_regression
from backend.erce.web_bridge import calculate_erce_web_item


class MediaMonitoringTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name)/"test.sqlite3"
        save_variable_rows(media_monitoring_survey_rows(),self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"]=="2209797"],self.db)

    def calculate(self,p):
        return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_full_result_engine_and_web(self):
        r = run_regression(self.db)
        self.assertEqual(r["total_eok"],1)
        self.assertEqual(r["error_percent"],0)
        self.assertEqual(r["annual_display_matches"],5)
        self.assertFalse(r["independent_evaluation"])

    def test_other_task_rejected(self):
        p = {**monitoring_payload(),"bill_no":"NEW_SURVEY","research_service_function":"household_survey"}
        with self.assertRaises(ValueError):
            self.calculate(p)

    def test_new_law_cycle_overrides_precedent_and_missing_unit(self):
        p = {**monitoring_payload(),"bill_no":"NEW_MONITORING"}
        p["explicit_inputs"] = {"recurrence_interval_years":dict(value=2,unit="year",source_ref="새원문2년주기")}
        self.assertEqual(self.calculate(p)["annualAmountsThousand"],[50000,0,50000,0,50000])
        p["selected_evidence_keys"] = p["selected_evidence_keys"][1:]
        self.assertEqual(self.calculate(p)["status"],"needs_input")
