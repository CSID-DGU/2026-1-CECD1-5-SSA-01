import tempfile
import unittest
from pathlib import Path
from backend.erce.engine import estimate_routed_item
from backend.erce.school_meal_evidence import (
    school_meal_rows,reviewed_school_meal_payload,COST_BASIS,FINANCING_SCOPE,
)
from backend.erce.variable_evidence_store import save_variable_rows,find_variable_candidates


class SchoolMealTests(unittest.TestCase):
    def test_annual_cost_financing_and_known_offset(self):
        payload=dict(route_key="school_meal_annual_public_support",years=2,
            explicit_inputs={"recipient_count":10,
                "annual_service_cost_per_person":{"value":10000,"unit":"KRW/person/year"},
                "public_support_share":{"value":.9,"unit":"ratio"},
                "cost_adjustment_factors":[1,1.1]})
        self.assertEqual(estimate_routed_item(payload).annual_amounts_thousand,(90,99))
        net=estimate_routed_item({**payload,"explicit_inputs":{**payload["explicit_inputs"],
                                                              "existing_public_support":1000}})
        self.assertEqual(net.annual_amounts_thousand,(89,98))
        for key,value in (("public_support_share",1.2),("cost_adjustment_factors",[1,0])):
            with self.assertRaises(ValueError):
                estimate_routed_item({**payload,"explicit_inputs":{**payload["explicit_inputs"],key:value}})
        with self.assertRaisesRegex(ValueError,"annual"):
            estimate_routed_item({**payload,"explicit_inputs":{**payload["explicit_inputs"],
                "annual_service_cost_per_person":{"value":10000,"unit":"KRW/person/meal"}}})

    def test_db_scope_year_and_self_exclusion(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"variables.sqlite3"
            save_variable_rows(school_meal_rows(),db)
            p=reviewed_school_meal_payload(db)
            result=estimate_routed_item(p)
            self.assertEqual(result.formula_key,"ANNUAL_PUBLIC_SERVICE_SUPPORT_V1")
            self.assertTrue(all(a<b for a,b in zip(result.annual_amounts_thousand,result.annual_amounts_thousand[1:])))
            with self.assertRaisesRegex(ValueError,"target answer"):
                estimate_routed_item({**p,"evidence_mode":"holdout"})
            with self.assertRaisesRegex(ValueError,"service_cost_basis mismatch"):
                estimate_routed_item({**p,"service_cost_basis":"food_only"})
            with self.assertRaisesRegex(ValueError,"public_financing_scope mismatch"):
                estimate_routed_item({**p,"public_financing_scope":"central_treasury_only"})
            with self.assertRaisesRegex(ValueError,"year mismatch"):
                estimate_routed_item({**p,"start_year":2027})
            with self.assertRaisesRegex(ValueError,"future"):
                estimate_routed_item({**p,"cutoff_date":"2024-07-16"})

    def test_new_bill_reuses_rates_not_population(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"variables.sqlite3"
            save_variable_rows(school_meal_rows(),db)
            candidates=find_variable_candidates(target_bill_no="new",cutoff_date="2026-10-03",db_path=db)
            self.assertFalse(any(r["variable_key"]=="recipient_count" for r in candidates))
            p=reviewed_school_meal_payload(db)
            keys=[k for k in p["selected_evidence_keys"] if k!="2201813:alternative_students_2023"]
            new={**p,"bill_no":"new","evidence_mode":"holdout","selected_evidence_keys":keys,
                 "evidence_selection_reasons":{k:"식품비·운영비 및 교육청·지자체 부담 구조 동일; 연도 조정 시나리오 확인" for k in keys},
                 "explicit_inputs":{"recipient_count":{"value":100,"source_ref":"합성 새 의안 학생100명"}}}
            result=estimate_routed_item(new)
            self.assertAlmostEqual(result.annual_amounts_thousand[0],100*1371000*.923*1.02/1000,delta=.5)
