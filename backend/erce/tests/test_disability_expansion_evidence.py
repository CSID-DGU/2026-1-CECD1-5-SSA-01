import copy
import tempfile
import unittest
from pathlib import Path

from backend.erce.disability_expansion_evidence import disability_expansion_rows
from backend.erce.scripts.check_disability_expansion import payload
from backend.erce.scripts.check_disability_expansion_population import projected_payload
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.web_bridge import calculate_erce_web_item


class DisabilityExpansionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/"evidence.sqlite3"
        save_variable_rows(disability_expansion_rows(),self.db)
        self.p={**payload(),"bill_no":"SYNTHETIC_EXPANSION","evidence_mode":"holdout"}

    def run_item(self,p):return calculate_erce_web_item(p,variable_db_path=self.db)

    def test_counts_subtract_existing_and_weight_benefit_types(self):
        r=self.run_item(self.p)
        self.assertEqual(r["status"],"computed_review")
        t={x["variable_key"]:x for x in r["derivationTrace"]}
        self.assertAlmostEqual(t["recipient_count"]["values"][0],(904029-508975)*.7059)
        self.assertLess(t["benefit_per_recipient"]["values"][0],334810*1.022)

    def test_missing_population_is_not_inferred_from_gold(self):
        p=copy.deepcopy(self.p)
        p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if "expanded_eligible_reference" not in k]
        r=self.run_item(p)
        self.assertEqual(r["missingVariables"],["recipient_count"])
        self.assertIn("expanded_eligible_reference",r["missingDerivationVariables"])

    def test_wrong_scope_period_missing_confirmation_and_source_block(self):
        for change in ({"disability_population_basis":"forecast"},{"composition_conflict_note":""},
            {"disability_benefit_scope":"couple_recovery"},{"disability_composition_basis":"2022"},
            {"start_year":2026},{"supplementary_benefit_policy_unchanged":False},
            {"use_unmatched_source_as_reference":False},{"cutoff_date":"2024-08-23"},
            {"bill_no":"2203497","evidence_mode":"development_review"}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.run_item({**self.p,**change})

    def test_duplicate_rate_rejected_and_explicit_count_preserved(self):
        p=copy.deepcopy(self.p)
        p["explicit_inputs"]["participation_rate"]=dict(value=.7059,unit="ratio",source_ref="중복")
        with self.assertRaises(ValueError):self.run_item(p)
        p=copy.deepcopy(self.p)
        p["explicit_inputs"]["recipient_count"]=dict(value=10,unit="person",source_ref="합성원문 명시인원")
        r=self.run_item(p)
        self.assertFalse(next(t for t in r["derivationTrace"] if t["variable_key"]=="recipient_count")["applied"])

    def test_projected_population_has_no_frozen_fallback(self):
        p={**projected_payload(),"bill_no":"SYNTHETIC_PROJECTED_POPULATION","evidence_mode":"holdout"}
        r=self.run_item(p)
        self.assertEqual(r["status"],"computed_review")
        self.assertAlmostEqual(sum(r["annualAmountsThousand"])/1e9,5.717224906,places=8)
        p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if "recipient_count:official_population" not in k]
        with self.assertRaises(ValueError):self.run_item(p)
