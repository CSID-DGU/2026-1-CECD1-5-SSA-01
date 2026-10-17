import tempfile
import unittest
from pathlib import Path

from backend.erce.engine import estimate_routed_item
from backend.erce.variable_evidence_store import save_variable_rows, find_variable_candidates
from backend.erce.veteran_support_evidence import veteran_support_rows, reviewed_replay_payloads


class VeteranSupportTests(unittest.TestCase):
    def test_db_replay_and_no_double_counting(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"variables.sqlite3"
            save_variable_rows(veteran_support_rows(),db)
            result={p["veteran_support_kind"]:estimate_routed_item(p)
                    for p in reviewed_replay_payloads(db)}
            amounts=[r.annual_amounts_thousand for r in result.values()]
            self.assertEqual(sum(map(sum,amounts)),2969974102)
            self.assertEqual(result["self_compensation"].annual_amounts_thousand[0],75578964)
            self.assertEqual(result["dependent_spouse"].annual_amounts_thousand[0],5050800)
            # Government support per visit is already net of the insurer's payment:
            # multiplying the support ratio .6 again would understate the answer.
            self.assertEqual(result["hospital_inpatient"].annual_amounts_thousand[0],120994)
            self.assertEqual(result["contract_inpatient"].annual_amounts_thousand[0],113989)

    def test_target_populations_are_not_reusable_and_channels_cannot_be_mixed(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"variables.sqlite3"
            save_variable_rows(veteran_support_rows(),db)
            rows=find_variable_candidates(cutoff_date="2026-10-03",target_bill_no="other",db_path=db)
            self.assertTrue(rows)
            self.assertTrue(all(r["reuse_policy"] != "target_only" for r in rows))
            payload=reviewed_replay_payloads(db)[3]
            with self.assertRaisesRegex(ValueError,"target answer"):
                estimate_routed_item({**payload,"evidence_mode":"holdout"})
            with self.assertRaisesRegex(ValueError,"different target"):
                estimate_routed_item({**payload,"bill_no":"other"})
            with self.assertRaisesRegex(ValueError,"veteran_support_kind mismatch"):
                estimate_routed_item({**payload,"veteran_support_kind":"contract_inpatient"})
            with self.assertRaisesRegex(ValueError,"year mismatch"):
                estimate_routed_item({**payload,"start_year":2027})

    def test_population_basis_and_raw_visit_ratios_preserve_provenance(self):
        rows=veteran_support_rows()
        basis=rows[-1]["value"]
        self.assertEqual(sum(basis["living_by_age"].values()),7165)
        self.assertEqual(basis["living_count"]+basis["already_deceased"],32549)
        visits=[r for r in rows if r["variable_key"]=="visits_per_recipient"]
        self.assertEqual(len(visits),5)
        for row in visits:
            self.assertEqual(row["value"],row["historical_visits"]/row["historical_eligible_persons"])
            self.assertEqual(row["cost_basis"],"government_paid_support")
