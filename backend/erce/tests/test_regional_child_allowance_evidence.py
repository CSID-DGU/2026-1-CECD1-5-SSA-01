import tempfile
import unittest
from pathlib import Path

from backend.erce.regional_child_allowance_evidence import regional_child_allowance_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.web_bridge import calculate_erce_web_item


class RegionalChildAllowanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "evidence.sqlite3"
        self.rows = regional_child_allowance_rows()
        save_variable_rows(self.rows, self.db)

    def payload(self, age=0):
        row = self.rows[0 if age == 0 else 1]
        return dict(bill_no="SYNTHETIC_REGIONAL_REUSE", route_key="transfer_recipient",
            cutoff_date="2026-10-04", start_year=2026, years=5,
            child_population_geography=row["child_population_geography"],
            population_age_min=row["population_age_min"], population_age_max=row["population_age_max"],
            recipient_population_basis=row["recipient_population_basis"],
            selected_evidence_keys=[row["evidence_key"]],
            evidence_selection_reasons={row["evidence_key"]:"동일한 지역지정·연령·기간의 선례 시나리오"},
            explicit_inputs={"benefit_per_recipient":dict(value=100000 if age == 0 else 50000,
                unit="KRW/person/month", source_ref="합성 사례 명시금액"),
                "payments_per_year":dict(value=12, unit="month/year", source_ref="합성 사례 연중지급")})

    def test_web_reuse_calculates_both_age_groups(self):
        amounts = []
        for age in (0, 8):
            r = calculate_erce_web_item(self.payload(age), variable_db_path=self.db)
            self.assertEqual(r["status"], "computed_review")
            self.assertEqual(r.get("missingVariables", []), [])
            amounts.append(sum(r["annualAmountsThousand"]))
        self.assertAlmostEqual(sum(amounts)/1e9, 1.624214052, places=8)

    def test_rejects_wrong_region_age_basis_and_year(self):
        for change in ({"child_population_geography":"전국"}, {"population_age_min":1},
                       {"population_age_max":17}, {"recipient_population_basis":"unverified"},
                       {"start_year":2027}, {"cutoff_date":"2025-06-17"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                calculate_erce_web_item({**self.payload(), **change}, variable_db_path=self.db)

    def test_web_rejects_own_answer_even_with_development_mode(self):
        with self.assertRaises(ValueError):
            calculate_erce_web_item({**self.payload(), "bill_no":"2210913",
                "evidence_mode":"development_review"}, variable_db_path=self.db)

    def test_rejects_double_execution_adjustment(self):
        p = self.payload()
        p["explicit_inputs"]["participation_rate"] = dict(value=.996, unit="ratio", source_ref="중복 집행계수")
        with self.assertRaises(ValueError):
            calculate_erce_web_item(p, variable_db_path=self.db)
