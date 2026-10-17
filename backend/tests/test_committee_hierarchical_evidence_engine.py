import unittest
from unittest.mock import patch

from backend.legacy.committee.committee_hierarchical_evidence_engine import evaluate
from backend.committee_precedent_resolver import PrecedentResolution


def _resolution(decision: str) -> PrecedentResolution:
    return PrecedentResolution(
        bill_no="T",
        decision=decision,
        selected_bill_no="P" if decision != "abstain" else None,
        relation_route="same_law" if decision != "abstain" else None,
        relation_score=1.0 if decision != "abstain" else 0.0,
        matched_item_ids=("I",) if decision != "abstain" else (),
        missing_components=(),
        conflicts=(),
        reasons=(),
        relation_top5=("P",) if decision != "abstain" else (),
    )


class HierarchicalEvidenceEngineTests(unittest.TestCase):
    def test_exact_package_short_circuits_component_recommendation(self) -> None:
        with (
            patch(
                "backend.legacy.committee.committee_hierarchical_evidence_engine.resolve_package",
                return_value=_resolution("exact_package"),
            ),
            patch(
                "backend.legacy.committee.committee_hierarchical_evidence_engine.recommend_components"
            ) as components,
        ):
            result = evaluate({"bill_no": "T"})
        self.assertEqual(result.route, "exact_legislative_package")
        self.assertEqual(result.decision, "exact_package_candidate")
        self.assertEqual(result.components, ())
        components.assert_not_called()

    def test_non_exact_route_never_becomes_automatic(self) -> None:
        with (
            patch(
                "backend.legacy.committee.committee_hierarchical_evidence_engine.resolve_package",
                return_value=_resolution("component_only"),
            ),
            patch(
                "backend.legacy.committee.committee_hierarchical_evidence_engine.recommend_components",
                return_value=[],
            ),
        ):
            result = evaluate({"bill_no": "T"})
        self.assertEqual(result.route, "component_evidence_hitl")
        self.assertEqual(result.decision, "needs_user_input")


if __name__ == "__main__":
    unittest.main()
