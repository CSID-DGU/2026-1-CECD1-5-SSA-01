import tempfile
import unittest
from pathlib import Path
from backend.erce.elderly_public_activity_evidence import elderly_public_activity_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_elderly_public_activity import activity_payload
from backend.erce.web_bridge import calculate_erce_web_item


class ElderlyPublicActivityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "test.sqlite3"
        save_variable_rows(elderly_public_activity_rows(), self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"] == "2203550"], self.db)

    def payload(self):
        return {**activity_payload(), "bill_no": "NEW_PUBLIC_ACTIVITY_REFERENCE", "evidence_mode": "holdout"}

    def calculate(self, p):
        return calculate_erce_web_item(p, variable_db_path=self.db)

    def test_histories_first_year_and_ancillary_cancellation(self):
        r = self.calculate(self.payload())
        self.assertEqual([t["public_activity_participants"] for t in r["derivationTrace"]], [685129, 717739, 751902, 787691, 825183])
        self.assertEqual([t["payment_months"] for t in r["derivationTrace"]], [2, 11, 11, 11, 11])
        self.assertEqual([round(x / 100000) for x in r["annualAmountsThousand"]], [79, 861, 1787, 2834, 4012])
        p = self.payload()
        p["explicit_inputs"] = {"ancillary_annual_cost": dict(value=0, unit="KRW/person/year", source_ref="양쪽 동일 부대경비 상쇄 검증")}
        self.assertEqual(self.calculate(p)["annualAmountsThousand"], r["annualAmountsThousand"])

    def test_version_and_job_type_guards(self):
        for change in [{"use_unmatched_source_as_reference": False}, {"elderly_job_type": "private_job"}, {"bill_no": "2203550"}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.calculate({**self.payload(), **change})

    def test_missing_history_not_imputed(self):
        p = self.payload()
        p["selected_evidence_keys"] = [k for k in p["selected_evidence_keys"] if "participant_history" not in k]
        self.assertIn("public_activity_participant_history", self.calculate(p)["missingDerivationVariables"])
