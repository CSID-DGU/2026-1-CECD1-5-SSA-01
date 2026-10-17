import tempfile
import unittest
from pathlib import Path

from backend.erce.method_evidence_store import (
    find_method_candidates, save_method_rows, validate_non_estimation_review,
    validate_selected_methods,
)
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.variable_evidence_store import save_variable_rows


class NonEstimationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "evidence.sqlite3"
        save_variable_rows([], self.path)
        self.row = next(r for r in reviewed_method_rows()
                        if r.get("evidence_kind") == "non_estimation")
        save_method_rows([self.row], self.path)
        self.payload = dict(
            bill_no="NEW_BILL", cutoff_date="2026-10-04",
            decision_evidence_key=self.row["method_key"],
            reliable_estimation_basis_available=False,
            decision_confirmations={
                "child_abuse_recovery_scope": "합성 검증: 아동학대 유죄보호자 아동수당 환수",
                "forecast_basis_review": "합성 검증: 대상 규모·기지급액·회수율의 합리적 예측 근거 없음",
            })

    def test_search_returns_sourced_candidate_not_zero(self):
        rows = find_method_candidates(query="아동수당 아동학대 유죄보호자 환수",
            cutoff_date="2026-10-04", target_bill_no="NEW_BILL", db_path=self.path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["selection_status"], "candidate_only")
        self.assertIn("예측이 어려워", rows[0]["source_quote"])
        self.assertEqual(rows[0]["allowed_routes"], [])
        self.assertEqual(find_method_candidates(query="법인세 환수",
            cutoff_date="2026-10-04", db_path=self.path), [])

    def test_confirmed_review_returns_unknown_amount_with_provenance(self):
        result = validate_non_estimation_review(self.payload, db_path=self.path)
        self.assertEqual(result["decision"], "not_estimated")
        self.assertIsNone(result["amount"])
        self.assertTrue(result["reestimate_when"])
        self.assertEqual(result["source_ref"], self.row["source_ref"])

    def test_self_future_family_and_exclusions_rejected(self):
        for overrides in ({"bill_no": "2202573"}, {"cutoff_date": "2026-10-03"},
                          {"target_family_key": self.row["family_key"]},
                          {"excluded_bill_nos": ["2202573"]}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                validate_non_estimation_review({**self.payload, **overrides}, db_path=self.path)

    def test_missing_review_or_available_basis_blocks_non_estimation(self):
        for overrides in ({"decision_confirmations": {}},
                          {"reliable_estimation_basis_available": True},
                          {"reliable_estimation_basis_available": None}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                validate_non_estimation_review({**self.payload, **overrides}, db_path=self.path)

    def test_not_selectable_as_calculation_method(self):
        with self.assertRaisesRegex(ValueError, "cannot be used as a calculation"):
            validate_selected_methods(dict(bill_no="NEW_BILL", cutoff_date="2026-10-04",
                selected_method_keys=[self.row["method_key"]]), db_path=self.path)
