import tempfile
import unittest
from pathlib import Path

from backend.erce.engine import estimate_routed_item
from backend.erce.noise_support_evidence import noise_support_rows,reviewed_noise_replay
from backend.erce.variable_evidence_store import save_variable_rows,find_variable_candidates


class NoiseSupportTests(unittest.TestCase):
    def test_phased_installation_stops_and_population_delta_does_not_double_count(self):
        r=estimate_routed_item(dict(route_key="capital_phased_installation",years=3,
            explicit_inputs=dict(total_installation_quantity=10,installation_years=2,installation_unit_cost=1000)))
        self.assertEqual(r.annual_amounts_thousand,(5,5,0))
        r=estimate_routed_item(dict(route_key="transfer_population_amount_delta",years=1,
            explicit_inputs=dict(new_recipient_count=12,existing_recipient_count=10,
                                 benefit_per_recipient=2000,existing_benefit_per_recipient=1000,payments_per_year=12)))
        self.assertEqual(r.annual_amounts_thousand,(168,))
        with self.assertRaises(ValueError):
            estimate_routed_item(dict(route_key="capital_phased_installation",years=1,
                explicit_inputs=dict(total_installation_quantity=10,installation_years=0,installation_unit_cost=1000)))

    def test_db_replay_and_related_budget_uses_parent_not_answer_total(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"variables.sqlite3"
            save_variable_rows(noise_support_rows(),db)
            result=reviewed_noise_replay(db)
            self.assertEqual(sum(sum(r.annual_amounts_thousand) for r in result.values()),6709406771)
            self.assertEqual(result["cool_school"].annual_amounts_thousand,(0,)*5)
            related=result["resident_support"]
            self.assertEqual(related.resolved_variables["reference_project_cost"].source_class,"calculated_estimate")
            parent=sum(r.annual_amounts_thousand[0]*1000 for k,r in result.items()
                       if not k.startswith("zone") and k!="resident_support")
            self.assertEqual(related.annual_amounts_thousand[0],round(parent*.268/1000))

    def test_quantity_and_component_gates(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"variables.sqlite3"
            rows=noise_support_rows()
            save_variable_rows(rows,db)
            candidates=find_variable_candidates(cutoff_date="2026-10-03",target_bill_no="other",db_path=db)
            self.assertTrue(candidates)
            self.assertTrue(all(r["reuse_policy"]!="target_only" for r in candidates))
            keys=[r["evidence_key"] for r in rows if r["noise_support_component"]=="sound_house"]
            base=dict(route_key="capital_phased_installation",bill_no="2203380",years=5,start_year=2026,
                      cutoff_date="2026-10-03",variable_db_path=db,evidence_mode="development_review",
                      noise_support_component="sound_house",selected_evidence_keys=keys)
            with self.assertRaisesRegex(ValueError,"noise_support_component mismatch"):
                estimate_routed_item({**base,"noise_support_component":"cool_house"})
            with self.assertRaisesRegex(ValueError,"target answer"):
                estimate_routed_item({**base,"evidence_mode":"holdout"})
