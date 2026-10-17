import tempfile
import unittest
from pathlib import Path

from backend.erce.engine import estimate_routed_item
from backend.erce.loan_financing_evidence import (
    ROUTE, loan_financing_rows, reviewed_loan_interest_payload,
    incremental_penalty_loss, borrowing_rates_for_years,
    official_loan_projection_rows, reviewed_loan_projection_payload, project_overdue_balances,
)
from backend.erce.variable_evidence_store import save_variable_rows, find_variable_candidates
from backend.erce.web_bridge import route_options, calculate_erce_web_item


class LoanFinancingTests(unittest.TestCase):
    def test_full_projection_from_history_and_official_forecast(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"evidence.sqlite3"
            save_variable_rows(loan_financing_rows()+official_loan_projection_rows(),db)
            p=reviewed_loan_projection_payload(db)
            result=estimate_routed_item(p)
            self.assertEqual(result.annual_amounts_thousand,(15663,4609,6359,12000,4432))
            # All printed gold annual amounts match at its million-won precision.
            self.assertEqual([round(v/1000) for v in result.annual_amounts_thousand],[16,5,6,12,4])
            self.assertNotIn("2204385:new_borrowing_2025_2029",p["selected_evidence_keys"])
            self.assertEqual(result.resolved_variables["new_borrowing_amount"].source_class,"calculated_estimate")
            self.assertLess(abs(sum(result.annual_amounts_thousand)-43000)/43000,.002)
            with self.assertRaisesRegex(ValueError,"confirmed applicability"):
                estimate_routed_item({**p,"loan_projection_confirmation_note":""})
            with self.assertRaisesRegex(ValueError,"target answer"):
                estimate_routed_item({**p,"evidence_mode":"holdout"})
            bad={**p,"selected_evidence_keys":[k for k in p["selected_evidence_keys"] if "treasury3y" not in k]}
            with self.assertRaisesRegex(ValueError,"sovereign_interest_forecast"):
                estimate_routed_item(bad)

    def test_history_projection_requires_real_baseline_supply(self):
        rows={r["variable_key"]:r for r in loan_financing_rows()+official_loan_projection_rows()}
        supply=rows["icl_supply_by_year"]["value"]
        overdue=rows["overdue_repayment_by_year"]["value"]
        balances,growth=project_overdue_balances(supply,overdue,start_year=2025,years=5,lag=6)
        self.assertAlmostEqual(balances[0]/1e8,941.065345773)
        self.assertAlmostEqual(growth,.017353271762924317)
        without_baseline={k:v for k,v in supply.items() if k!="2018"}
        with self.assertRaisesRegex(ValueError,"2018"):
            project_overdue_balances(without_baseline,overdue,start_year=2025,years=5,lag=6)
        for lag in (True,6.5,0):
            with self.assertRaises(ValueError):
                project_overdue_balances(supply,overdue,start_year=2025,years=5,lag=lag)

    def test_official_forecast_has_2029_and_is_not_latest_or_inverted(self):
        rows=official_loan_projection_rows()
        forecast=rows[0]
        self.assertEqual(forecast["value"]["2029"],.025)
        self.assertEqual(forecast["published_at"],"2024-10-11")
        self.assertEqual(forecast["source_class"],"official_standard")
        self.assertEqual(rows[1]["value"]["2018"],837900000000)

    def inputs(self):
        return {
            "new_borrowing_amount": dict(value=[1000000,2000000], unit="KRW/year", source_ref="synthetic"),
            "borrowing_interest_rate": dict(value=[.03,.04], unit="ratio", source_ref="synthetic"),
            "average_balance_factor": dict(value=.5, unit="ratio", source_ref="synthetic"),
            "government_interest_support_share": dict(value=.8, unit="ratio", source_ref="synthetic"),
        }

    def test_fixed_formula_and_web_connection(self):
        p = dict(route_key=ROUTE, years=2, explicit_inputs=self.inputs())
        self.assertEqual(estimate_routed_item(p).annual_amounts_thousand, (12,32))
        self.assertIn(ROUTE, [r["routeKey"] for r in route_options()])
        self.assertEqual(calculate_erce_web_item(p)["status"], "computed_review")
        missing = self.inputs()
        del missing["borrowing_interest_rate"]
        self.assertEqual(calculate_erce_web_item({**p,"explicit_inputs":missing})["missingVariables"],
                         ["borrowing_interest_rate"])

    def test_invalid_units_and_double_adjustment_rejected(self):
        for key,value in (("borrowing_interest_rate",3.57),("average_balance_factor",float("nan")),
                          ("government_interest_support_share",True),("new_borrowing_amount",[-1,1])):
            data = self.inputs()
            data[key] = {**data[key],"value":value}
            with self.assertRaises(ValueError):
                estimate_routed_item(dict(route_key=ROUTE,years=2,explicit_inputs=data))
        data=self.inputs()
        data["new_borrowing_amount"]["unit"]="백만원/년"
        with self.assertRaisesRegex(ValueError,"unit"):
            estimate_routed_item(dict(route_key=ROUTE,years=2,explicit_inputs=data))
        for key in ("growth_rate","first_year_fraction","duration","growth_rates_by_year","base_year"):
            with self.assertRaises(ValueError):
                estimate_routed_item(dict(route_key=ROUTE,years=2,
                    explicit_inputs={**self.inputs(),key:{"value":1,"unit":"ratio"}}))

    def test_increment_not_whole_stock_and_missing_forecast(self):
        values = incremental_penalty_loss([100000000,120000000],80000000,.0836,.0454,1)
        self.assertAlmostEqual(values[0],764000)
        self.assertAlmostEqual(values[1],764000)
        with self.assertRaisesRegex(ValueError,"previous_year_balance"):
            incremental_penalty_loss([100000000],None,.0836,.0454,1)
        with self.assertRaisesRegex(ValueError,"separate financing"):
            incremental_penalty_loss([70000000],80000000,.0836,.0454,1)
        self.assertEqual(borrowing_rates_for_years([2025,2026],{2025:.0357},{2026:.03},.0017),[.0357,.0317])
        with self.assertRaisesRegex(ValueError,"2026"):
            borrowing_rates_for_years([2025,2026],{2025:.0357},{},.0017)

    def test_reference_replay_and_evidence_gates(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"evidence.sqlite3"
            save_variable_rows(loan_financing_rows(),db)
            p=reviewed_loan_interest_payload(db)
            self.assertEqual(estimate_routed_item(p).annual_amounts_thousand,(15672,))
            with self.assertRaisesRegex(ValueError,"target answer"):
                estimate_routed_item({**p,"evidence_mode":"holdout"})
            with self.assertRaisesRegex(ValueError,"public_financing_scope mismatch"):
                estimate_routed_item({**p,"public_financing_scope":"central_revenue_loss"})
            with self.assertRaisesRegex(ValueError,"year mismatch"):
                estimate_routed_item({**p,"start_year":2026})
            with self.assertRaisesRegex(ValueError,"future"):
                estimate_routed_item({**p,"cutoff_date":"2024-10-29"})
            with self.assertRaisesRegex(ValueError,"borrowing_interest_rate"):
                estimate_routed_item(reviewed_loan_interest_payload(db,years=5))
            candidates=find_variable_candidates(target_bill_no="new",cutoff_date="2026-10-03",db_path=db)
            self.assertFalse(any(row["variable_key"]=="new_borrowing_amount" for row in candidates))
            # Reuse conditional funding/rate references, not the target's amount.
            new={**p,"bill_no":"new","evidence_mode":"holdout",
                "selected_evidence_keys":[key for key in p["selected_evidence_keys"] if "new_borrowing_2025" not in key],
                "explicit_inputs":{"new_borrowing_amount":{"value":100000000,"unit":"KRW/year","source_ref":"synthetic new issuance"}}}
            with self.assertRaisesRegex(ValueError,"applicability reason"):
                estimate_routed_item(new)
            new["evidence_selection_reasons"]={key:"같은 정부 이자지원·신규분 범위 및2025년 금리의 조건부 시나리오" for key in new["selected_evidence_keys"]}
            self.assertEqual(estimate_routed_item(new).annual_amounts_thousand,(2081,))
