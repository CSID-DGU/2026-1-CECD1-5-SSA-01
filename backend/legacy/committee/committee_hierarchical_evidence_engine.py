"""Route committee evidence through the strongest available provenance.

This experimental orchestrator is intentionally isolated from ``tag_pipeline``
and ``server``.  It does not blend unrelated similarity scores:

1. execute only a complete package on a strong legislative relationship;
2. otherwise expose bill-text facts and role-specific evidence priors;
3. leave unsupported operands to HITL.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from backend.legacy.committee.committee_component_evidence_engine import (
    ComponentEvidenceResult,
    recommend as recommend_components,
)
from backend.erce_web.committee_precedent_resolver import (
    PrecedentResolution,
    resolve as resolve_package,
)


ENGINE_VERSION = "committee-hierarchical-evidence-v0.1.0"


@dataclass(frozen=True)
class HierarchicalEvidenceResult:
    bill_no: str
    route: str
    decision: str
    package: PrecedentResolution
    components: tuple[ComponentEvidenceResult, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate(case: dict[str, Any]) -> HierarchicalEvidenceResult:
    package = resolve_package(case)
    if package.decision == "exact_package":
        return HierarchicalEvidenceResult(
            bill_no=str(case["bill_no"]),
            route="exact_legislative_package",
            decision="exact_package_candidate",
            package=package,
            components=(),
            warnings=(
                "The package is auditable but remains experimental until runtime integration.",
            ),
        )

    components = tuple(recommend_components(case))
    return HierarchicalEvidenceResult(
        bill_no=str(case["bill_no"]),
        route="component_evidence_hitl",
        decision="needs_user_input",
        package=package,
        components=components,
        warnings=(
            "Component suggestions are priors, not confirmed target values.",
            "No total is emitted until every required operand is confirmed.",
        ),
    )
