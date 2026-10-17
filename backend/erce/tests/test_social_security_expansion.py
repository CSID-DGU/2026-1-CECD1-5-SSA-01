import tempfile
import unittest
from pathlib import Path
from backend.erce.central_social_committee_evidence import central_social_committee_rows
from backend.erce.variable_evidence_store import save_variable_rows
from backend.erce.method_evidence_store import save_method_rows
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.scripts.check_social_security_expansion import expansion_payload
from backend.erce.web_bridge import calculate_erce_web_item


class SocialSecurityExpansionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "test.sqlite3"
        save_variable_rows(central_social_committee_rows(), self.db)
        save_method_rows([r for r in reviewed_method_rows() if r["source_bill_no"] == "2209259"], self.db)

    def payload(self, mode="face_to_face"):
        return {**expansion_payload(mode), "bill_no": "NEW_SOCIAL_SECURITY_EXPANSION", "evidence_mode": "holdout"}

    def calculate(self, p):
        return calculate_erce_web_item(p, variable_db_path=self.db)

    def test_delta_members_and_modes(self):
        r = self.calculate(self.payload())
        self.assertEqual(r["annualAmountsThousand"], [2400] * 5)
        self.assertEqual(r["derivationTrace"][0]["paid_members"], 4)
        self.assertEqual(self.calculate(self.payload("written"))["annualAmountsThousand"], [1200] * 5)
        p = self.payload()
        p["explicit_inputs"]["new_member_limit"]["value"] = 36
        self.assertEqual(self.calculate(p)["annualAmountsThousand"], [3000] * 5)

    def test_missing_approval_and_counts_are_not_silently_filled(self):
        r = self.calculate({**self.payload(), "expansion_scenario_confirmed": False})
        self.assertEqual(r["status"], "needs_input")
        self.assertIn("committee_expansion_confirmation", r["missingDerivationVariables"])
        p = self.payload()
        del p["explicit_inputs"]["new_member_limit"]
        self.assertIn("new_member_limit", self.calculate(p)["missingDerivationVariables"])

    def test_invalid_scope_and_own_source_rejected(self):
        with self.assertRaises(ValueError):
            self.calculate({**self.payload(), "bill_no": "2209259"})
        with self.assertRaises(ValueError):
            self.calculate({**self.payload(), "committee_role_profile": "central_social_policy_deliberation"})
        p = self.payload()
        p["explicit_inputs"]["incremental_unpaid_members"] = dict(value=6, unit="person", source_ref="잘못된 구성 검증")
        with self.assertRaises(ValueError):
            self.calculate(p)
