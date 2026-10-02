import tempfile
import unittest
from pathlib import Path

from backend.erce.parent_benefit_evidence import parent_benefit_rows
from backend.erce.variable_evidence_store import save_variable_rows, find_variable_candidates
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item, route_options
from backend.erce.draft_report import generate_draft


class ParentBenefitTests(unittest.TestCase):
    def test_official_data_and_negative_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "variables.sqlite3"
            rows = parent_benefit_rows()
            save_variable_rows(rows, path)
            self.assertEqual(find_variable_candidates(cutoff_date="2024-06-14", db_path=path), [])
            results = []
            for age in (0,1):
                keys = [r["evidence_key"] for r in rows[:4] if r["population_age_min"] == age]
                base = dict(route_key="transfer_benefit_abolition", bill_no="2200509",
                            cutoff_date="2026-10-02", start_year=2025, years=5,
                            variable_db_path=path, selected_evidence_keys=keys,
                            evidence_selection_reasons={k:"동일 부모급여 및 연령; 2024년 단가 동결·전원 12개월 지급 시나리오" for k in keys},
                            explicit_inputs={"payments_per_year":{"value":12, "unit":"month/year", "source_ref":"검토 가정: 연 12개월"}})
                result = estimate_routed_item(base)
                self.assertTrue(all(v < 0 for v in result.annual_amounts_thousand))
                results.append(result)
                with self.assertRaisesRegex(ValueError, "future"):
                    estimate_routed_item({**base, "cutoff_date":"2024-06-14"})
                with self.assertRaises(ValueError):
                    estimate_routed_item({**base, "explicit_inputs":{"payments_per_year":{"value":13}}})
            reduction = sum(sum(r.annual_amounts_thousand) for r in results)*1000
            self.assertEqual(reduction, -(1147413*1000000 + 1125561*500000)*12)

    def test_web_catalog_and_draft_subtract_decrease(self):
        self.assertTrue(any(r["routeKey"] == "transfer_benefit_abolition" for r in route_options()))
        v = lambda x,u: {"value":x,"unit":u,"source_ref":"합성 검증 입력"}
        decrease = {"name":"급여 폐지", "route_key":"transfer_benefit_abolition",
                    "explicit_inputs":{"recipient_count":v(10,"person"),
                                       "existing_benefit_per_recipient":v(1000,"KRW/person/month"),
                                       "payments_per_year":v(12,"month/year")}}
        increase = {"name":"급여 신설", "route_key":"transfer_recipient",
                    "explicit_inputs":{"recipient_count":v(10,"person"),
                                       "benefit_per_recipient":v(2000,"KRW/person/month"),
                                       "payments_per_year":v(12,"month/year")}}
        draft = generate_draft({"start_year":2025,"years":1,"items":[increase,decrease]})
        self.assertEqual(draft["annualAmountsThousand"], [120])
        self.assertEqual(calculate_erce_web_item({**decrease,"years":1})["annualAmountsThousand"],[-120])
        with self.assertRaises(ValueError):
            calculate_erce_web_item({**decrease,"explicit_inputs":{**decrease["explicit_inputs"],
                                     "existing_benefit_per_recipient":v(1000,"KRW/person/year")}})
