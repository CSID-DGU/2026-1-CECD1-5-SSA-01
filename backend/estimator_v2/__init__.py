"""Evidence-first experimental estimator.

This package is intentionally separate from ``backend.estimator`` and the
production API.  It keeps the same broad detect -> retrieve -> calculate
workflow while making evidence, additionality, recurrence, and reproducibility
explicit.
"""

from .pipeline import estimate_from_pdf
from .org_admin_resolver import (
    CanonicalInput,
    OrgAdminPlanRequest,
    resolve_org_admin_plan,
)
from .top_level_router import (
    BillRoutingRequest,
    FinalDisposition,
    FiscalRouteRequest,
    RouteReadiness,
    route_bill,
)
from .precedent_first import (
    FiscalFactor,
    LLMConclusion,
    LLMFactorDecision,
    LocalPrecedentIndex,
    build_contexts,
    build_decision_prompt,
    route_llm_decisions,
)

__all__ = [
    "CanonicalInput",
    "BillRoutingRequest",
    "FinalDisposition",
    "FiscalFactor",
    "FiscalRouteRequest",
    "LLMConclusion",
    "LLMFactorDecision",
    "LocalPrecedentIndex",
    "OrgAdminPlanRequest",
    "RouteReadiness",
    "estimate_from_pdf",
    "resolve_org_admin_plan",
    "route_bill",
    "build_contexts",
    "build_decision_prompt",
    "route_llm_decisions",
]
