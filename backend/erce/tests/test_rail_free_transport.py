import tempfile
import unittest
from pathlib import Path
from backend.erce.rail_free_transport_evidence import rail_free_transport_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_rail_free_transport import rail_payload
from backend.erce.web_bridge import calculate_erce_web_item


class RailFreeTransportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "test.sqlite3"
        save_variable_rows(rail_free_transport_rows(), self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"] == "2204465"], self.db)

    def payload(self):
        return {**rail_payload(), "bill_no": "NEW_DISABLED_URBAN_RAIL", "evidence_mode": "holdout"}

    def calculate(self, p):
        return calculate_erce_web_item(p, variable_db_path=self.db)

    def test_historical_only_trends_units_and_display(self):
        r = self.calculate(self.payload())
        self.assertEqual([round(v / 100000) for v in r["annualAmountsThousand"]], [2950, 3328, 3693, 4048, 4399])
        self.assertEqual([t["displayed_trip_thousand"] for t in r["derivationTrace"]], [76656, 80754, 84852, 88950, 93048])
        self.assertEqual([t["displayed_fare_won"] for t in r["derivationTrace"]], [3849, 4121, 4352, 4551, 4727])
        self.assertAlmostEqual(sum(r["annualAmountsThousand"]) / 100000, 18418.04041)

    def test_reference_share_yields_to_confirmed_support_ratio(self):
        p = self.payload(); baseline = self.calculate(p)
        p["explicit_inputs"] = {"rail_compensation_share": dict(value=.5, unit="ratio", source_ref="확인된50%지원 시나리오")}
        r = self.calculate(p)
        for a, b in zip(baseline["derivationTrace"], r["derivationTrace"]):
            self.assertAlmostEqual(a["annual_won"] / 2, b["annual_won"])

    def test_scope_approval_and_missing_history(self):
        for change in [{"bill_no": "2204465"}, {"rail_operator_scope": "including_korail"},
                       {"rail_beneficiary_scope": "all_elderly"}, {"rail_fare_trend": "cagr"}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.calculate({**self.payload(), **change})
        r = self.calculate({**self.payload(), "rail_compensation_scenario_confirmed": False})
        self.assertIn("rail_compensation_confirmation", r["missingDerivationVariables"])
        p = self.payload(); p["selected_evidence_keys"] = [k for k in p["selected_evidence_keys"] if "trip_history" not in k]
        self.assertIn("rail_free_trip_history", self.calculate(p)["missingDerivationVariables"])
