"""Top-level disposition router for every cost-estimate outcome.

Detailed estimators are intentionally plugged in one route at a time.  This
module owns the stable outer decision contract:

* cost estimate
* partial cost estimate
* non-attachment reasons 1, 2 and 3
* not applicable
* review required

The router never asks an LLM for the final disposition.  AI output may propose
an event route and evidence, but deterministic gates decide whether that
evidence is sufficient.  At present only the organization/administration route
is connected to a real calculator; unsupported routes remain review-required
instead of being mislabeled as reason 3.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from .org_admin_resolver import (
    OrgAdminPlanRequest,
    request_from_dict as org_request_from_dict,
    resolve_org_admin_plan,
)


ROUTE_ORGANIZATION = "organization_administration"
ROUTE_WELFARE = "welfare_benefit"
ROUTE_SUBSIDY = "subsidy_compensation"
ROUTE_PROGRAM = "program_service"
ROUTE_FACILITY = "facility_asset"
ROUTE_REVENUE = "tax_non_tax_revenue"

STANDARD_ROUTES = {
    ROUTE_ORGANIZATION,
    ROUTE_WELFARE,
    ROUTE_SUBSIDY,
    ROUTE_PROGRAM,
    ROUTE_FACILITY,
    ROUTE_REVENUE,
}


class RouteReadiness(str, Enum):
    """Pre-calculation conclusion for one grounded fiscal event."""

    READY = "ready"
    NEEDS_INPUT = "needs_input"
    NEEDS_EVIDENCE = "needs_evidence"
    TECHNICALLY_UNESTIMABLE = "technically_unestimable"
    SECURITY_RESTRICTED = "security_restricted"
    NO_FISCAL_EFFECT = "no_fiscal_effect"


class OutcomeStatus(str, Enum):
    COMPUTED = "computed"
    NEEDS_INPUT = "needs_input"
    NEEDS_EVIDENCE = "needs_evidence"
    TECHNICALLY_UNESTIMABLE = "technically_unestimable"
    SECURITY_RESTRICTED = "security_restricted"
    NO_FISCAL_EFFECT = "no_fiscal_effect"


class FinalDisposition(str, Enum):
    COST_ESTIMATE = "cost_estimate"
    PARTIAL_ESTIMATE = "partial_estimate"
    NON_ATTACHMENT_1 = "non_attachment_1"
    NON_ATTACHMENT_2 = "non_attachment_2"
    NON_ATTACHMENT_3 = "non_attachment_3"
    NOT_APPLICABLE = "not_applicable"
    REVIEW_REQUIRED = "review_required"


class CostProfile(str, Enum):
    RECURRING = "recurring"
    TEMPORARY = "temporary"
    MIXED = "mixed"


DISPOSITION_LABELS = {
    FinalDisposition.COST_ESTIMATE: "비용추계서",
    FinalDisposition.PARTIAL_ESTIMATE: "비용추계서(일부추계)",
    FinalDisposition.NON_ATTACHMENT_1: "비용추계서 미첨부 사유서 1호",
    FinalDisposition.NON_ATTACHMENT_2: "비용추계서 미첨부 사유서 2호",
    FinalDisposition.NON_ATTACHMENT_3: "비용추계서 미첨부 사유서 3호",
    FinalDisposition.NOT_APPLICABLE: "비용추계 미대상 사유서",
    FinalDisposition.REVIEW_REQUIRED: "판단 보류(근거 또는 입력 필요)",
}


@dataclass(frozen=True)
class ThresholdPolicy:
    annual_average_thousand: int
    temporary_total_thousand: int


THRESHOLD_POLICIES = {
    "assembly": ThresholdPolicy(
        annual_average_thousand=1_000_000,
        temporary_total_thousand=3_000_000,
    ),
    "gyeonggi": ThresholdPolicy(
        annual_average_thousand=100_000,
        temporary_total_thousand=300_000,
    ),
}


@dataclass(frozen=True)
class RoutingEvidence:
    """Evidence attached to an AI-proposed pre-calculation conclusion.

    ``verified`` must be set by a trusted parser, official-document workflow,
    or human review.  An LLM proposal alone must leave it false.
    """

    kind: str
    source_ref: str
    quote: str
    verified: bool = False


@dataclass(frozen=True)
class FiscalRouteRequest:
    event_id: str
    route: str
    description: str
    readiness: RouteReadiness = RouteReadiness.READY
    payload: Mapping[str, Any] = field(default_factory=dict)
    reason: str = ""
    missing_variables: tuple[str, ...] = ()
    evidence: tuple[RoutingEvidence, ...] = ()


@dataclass(frozen=True)
class BillRoutingRequest:
    routes: tuple[FiscalRouteRequest, ...]
    form_type: str = "assembly"
    years: int = 5
    cost_profile: CostProfile = CostProfile.RECURRING


@dataclass(frozen=True)
class RouteOutcome:
    event_id: str
    route: str
    component: str
    status: OutcomeStatus
    annual_amounts_thousand: tuple[int | None, ...]
    reason: str
    missing_variables: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    evidence: tuple[RoutingEvidence, ...] = ()

    @property
    def total_thousand(self) -> int:
        return sum(value or 0 for value in self.annual_amounts_thousand)


@dataclass(frozen=True)
class BillRoutingDecision:
    disposition: FinalDisposition
    label: str
    reason: str
    reason_codes: tuple[str, ...]
    year_totals_thousand: tuple[int, ...]
    outcomes: tuple[RouteOutcome, ...]
    required_actions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["disposition"] = self.disposition.value
        payload["outcomes"] = [
            {
                **asdict(outcome),
                "status": outcome.status.value,
            }
            for outcome in self.outcomes
        ]
        return payload


_SECURITY_EVIDENCE_KINDS = {
    "official_security_classification",
    "security_review",
    "human_security_confirmation",
}
_TECHNICAL_EVIDENCE_KINDS = {
    "official_non_attachment",
    "same_law_scope",
    "human_unestimability_confirmation",
}


def _has_verified_evidence(
    evidence: Iterable[RoutingEvidence],
    *,
    allowed_kinds: set[str],
) -> bool:
    return any(
        row.verified
        and row.kind in allowed_kinds
        and bool(row.source_ref.strip())
        and bool(row.quote.strip())
        for row in evidence
    )


def _single_outcome(
    request: FiscalRouteRequest,
    *,
    status: OutcomeStatus,
    years: int,
    reason: str,
    reason_codes: tuple[str, ...],
) -> list[RouteOutcome]:
    return [
        RouteOutcome(
            event_id=request.event_id,
            route=request.route,
            component="event",
            status=status,
            annual_amounts_thousand=(None,) * years,
            reason=reason,
            missing_variables=request.missing_variables,
            reason_codes=reason_codes,
            evidence=request.evidence,
        )
    ]


def _resolve_organization(
    request: FiscalRouteRequest,
    *,
    years: int,
    profiles: Iterable[dict[str, Any]],
    variable_evidence: Iterable[dict[str, Any]],
) -> tuple[list[RouteOutcome], list[str]]:
    if not request.payload:
        return (
            _single_outcome(
                request,
                status=OutcomeStatus.NEEDS_INPUT,
                years=years,
                reason="조직·행정운영 계산 요청이 없어 필수 비용항목과 변수를 확인해야 합니다.",
                reason_codes=("ORGANIZATION_PLAN_REQUIRED",),
            ),
            [],
        )

    payload = dict(request.payload)
    payload["route"] = "organization"
    payload["years"] = years
    try:
        plan_request: OrgAdminPlanRequest = org_request_from_dict(payload)
        resolution = resolve_org_admin_plan(
            plan_request,
            profiles=profiles,
            evidence=variable_evidence,
        )
    except (TypeError, ValueError) as exc:
        return (
            _single_outcome(
                request,
                status=OutcomeStatus.NEEDS_EVIDENCE,
                years=years,
                reason=f"조직·행정운영 계산 요청을 검증하지 못했습니다: {exc}",
                reason_codes=("INVALID_ORGANIZATION_PLAN",),
            ),
            [],
        )

    status_map = {
        "computed_review": OutcomeStatus.COMPUTED,
        "needs_user_input": OutcomeStatus.NEEDS_INPUT,
        "needs_evidence": OutcomeStatus.NEEDS_EVIDENCE,
        # Unsupported components are not evidence that no cost exists.
        "excluded": OutcomeStatus.NEEDS_EVIDENCE,
    }
    outcomes: list[RouteOutcome] = []
    for row in resolution.rows:
        status = status_map.get(row.status, OutcomeStatus.NEEDS_EVIDENCE)
        if status == OutcomeStatus.COMPUTED:
            reason = f"기존 조직·행정운영 계산기가 {row.formula} 산식을 적용했습니다."
        elif status == OutcomeStatus.NEEDS_INPUT:
            reason = "대상 법안 고유의 조직 규모 또는 운영비 입력이 필요합니다."
        else:
            reason = "산식은 확인했지만 단가·비율 또는 적용 근거가 부족합니다."
        outcomes.append(
            RouteOutcome(
                event_id=request.event_id,
                route=request.route,
                component=row.component,
                status=status,
                annual_amounts_thousand=tuple(row.annual_amounts_thousand),
                reason=reason,
                missing_variables=tuple(row.missing_variables),
                reason_codes=tuple(row.reason_codes),
                evidence=request.evidence,
            )
        )
    return outcomes, list(resolution.warnings)


def _resolve_route(
    request: FiscalRouteRequest,
    *,
    years: int,
    organization_profiles: Iterable[dict[str, Any]],
    organization_evidence: Iterable[dict[str, Any]],
) -> tuple[list[RouteOutcome], list[str]]:
    if request.readiness == RouteReadiness.NO_FISCAL_EFFECT:
        return (
            _single_outcome(
                request,
                status=OutcomeStatus.NO_FISCAL_EFFECT,
                years=years,
                reason=request.reason or "추가 재정지출 또는 재정수입 감소가 확인되지 않았습니다.",
                reason_codes=("NO_FISCAL_EFFECT",),
            ),
            [],
        )

    if request.readiness == RouteReadiness.SECURITY_RESTRICTED:
        verified = _has_verified_evidence(
            request.evidence,
            allowed_kinds=_SECURITY_EVIDENCE_KINDS,
        )
        return (
            _single_outcome(
                request,
                status=(
                    OutcomeStatus.SECURITY_RESTRICTED
                    if verified
                    else OutcomeStatus.NEEDS_EVIDENCE
                ),
                years=years,
                reason=(
                    request.reason or "국가안전보장·군사기밀 관련 근거가 확인되었습니다."
                    if verified
                    else "AI의 2호 제안만으로 확정하지 않고 공식 보안 근거 또는 사람의 확인을 요청합니다."
                ),
                reason_codes=(
                    "VERIFIED_SECURITY_RESTRICTION"
                    if verified
                    else "SECURITY_EVIDENCE_REQUIRED",
                ),
            ),
            [],
        )

    if request.readiness == RouteReadiness.TECHNICALLY_UNESTIMABLE:
        verified = bool(request.missing_variables) and _has_verified_evidence(
            request.evidence,
            allowed_kinds=_TECHNICAL_EVIDENCE_KINDS,
        )
        return (
            _single_outcome(
                request,
                status=(
                    OutcomeStatus.TECHNICALLY_UNESTIMABLE
                    if verified
                    else OutcomeStatus.NEEDS_EVIDENCE
                ),
                years=years,
                reason=(
                    request.reason or "핵심 변수의 범위를 합리적으로 설정할 수 없다는 공식 근거가 확인되었습니다."
                    if verified
                    else "3호 제안을 확정하려면 핵심 누락 변수와 공식 미첨부 근거가 모두 필요합니다."
                ),
                reason_codes=(
                    "VERIFIED_TECHNICAL_UNESTIMABILITY"
                    if verified
                    else "TECHNICAL_UNESTIMABILITY_NOT_PROVEN",
                ),
            ),
            [],
        )

    if request.readiness == RouteReadiness.NEEDS_INPUT:
        return (
            _single_outcome(
                request,
                status=OutcomeStatus.NEEDS_INPUT,
                years=years,
                reason=request.reason or "사람이 대상 고유값을 입력하면 계산할 수 있습니다.",
                reason_codes=("TARGET_INPUT_REQUIRED",),
            ),
            [],
        )

    if request.readiness == RouteReadiness.NEEDS_EVIDENCE:
        return (
            _single_outcome(
                request,
                status=OutcomeStatus.NEEDS_EVIDENCE,
                years=years,
                reason=request.reason or "추계 가능 여부를 결정할 근거가 더 필요합니다.",
                reason_codes=("MORE_EVIDENCE_REQUIRED",),
            ),
            [],
        )

    if request.route == ROUTE_ORGANIZATION:
        return _resolve_organization(
            request,
            years=years,
            profiles=organization_profiles,
            variable_evidence=organization_evidence,
        )

    reason = (
        "표준 상위 경로는 등록되어 있지만 세부 계산기가 아직 연결되지 않았습니다. "
        "세부 엔진 미구현을 3호 사유로 오인하지 않고 판단 보류로 남깁니다."
        if request.route in STANDARD_ROUTES
        else "알 수 없는 비용 경로이므로 비용구조를 다시 분류해야 합니다."
    )
    return (
        _single_outcome(
            request,
            status=OutcomeStatus.NEEDS_EVIDENCE,
            years=years,
            reason=reason,
            reason_codes=(
                "ROUTE_ENGINE_NOT_IMPLEMENTED"
                if request.route in STANDARD_ROUTES
                else "UNKNOWN_COST_ROUTE",
            ),
        ),
        [],
    )


def _year_totals(outcomes: Iterable[RouteOutcome], years: int) -> tuple[int, ...]:
    totals = [0] * years
    for outcome in outcomes:
        if outcome.status != OutcomeStatus.COMPUTED:
            continue
        for index, amount in enumerate(outcome.annual_amounts_thousand[:years]):
            totals[index] += amount or 0
    return tuple(totals)


def _below_reason_1_threshold(
    *,
    totals: tuple[int, ...],
    form_type: str,
    cost_profile: CostProfile,
) -> bool:
    policy = THRESHOLD_POLICIES[form_type]
    total = sum(totals)
    average = total / len(totals) if totals else 0.0
    if cost_profile == CostProfile.TEMPORARY:
        return total < policy.temporary_total_thousand
    if cost_profile == CostProfile.RECURRING:
        return average < policy.annual_average_thousand
    # Mixed costs get a conservative automatic decision.  A reviewer can
    # still separate recurring and temporary portions later.
    return (
        average < policy.annual_average_thousand
        and total < policy.temporary_total_thousand
    )


def _required_actions(outcomes: Iterable[RouteOutcome]) -> tuple[str, ...]:
    actions: list[str] = []
    for outcome in outcomes:
        if outcome.status == OutcomeStatus.NEEDS_INPUT:
            variables = ", ".join(outcome.missing_variables) or "대상 고유값"
            actions.append(f"{outcome.event_id}/{outcome.component}: {variables} 입력")
        elif outcome.status == OutcomeStatus.NEEDS_EVIDENCE:
            actions.append(f"{outcome.event_id}/{outcome.component}: 적용 근거 확인")
        elif outcome.status == OutcomeStatus.SECURITY_RESTRICTED:
            actions.append(f"{outcome.event_id}: 미첨부 2호 사람 검토")
        elif outcome.status == OutcomeStatus.TECHNICALLY_UNESTIMABLE:
            actions.append(f"{outcome.event_id}: 미첨부 3호 사람 검토")
    return tuple(dict.fromkeys(actions))


def route_bill(
    request: BillRoutingRequest,
    *,
    organization_profiles: Iterable[dict[str, Any]] = (),
    organization_evidence: Iterable[dict[str, Any]] = (),
) -> BillRoutingDecision:
    """Resolve route branches and produce one deterministic final disposition."""

    if request.form_type not in THRESHOLD_POLICIES:
        raise ValueError("form_type must be assembly or gyeonggi")
    if not 1 <= request.years <= 10:
        raise ValueError("years must be between 1 and 10")
    if not request.routes:
        disposition = FinalDisposition.REVIEW_REQUIRED
        return BillRoutingDecision(
            disposition=disposition,
            label=DISPOSITION_LABELS[disposition],
            reason="분류할 재정수반 사건이 없어 원문 분석 결과를 확인해야 합니다.",
            reason_codes=("EMPTY_FISCAL_ROUTE_SET",),
            year_totals_thousand=(0,) * request.years,
            outcomes=(),
            required_actions=("재정수반 사건 추출 결과 확인",),
        )

    outcomes: list[RouteOutcome] = []
    warnings: list[str] = []
    for route_request in request.routes:
        resolved, route_warnings = _resolve_route(
            route_request,
            years=request.years,
            organization_profiles=organization_profiles,
            organization_evidence=organization_evidence,
        )
        outcomes.extend(resolved)
        warnings.extend(route_warnings)

    totals = _year_totals(outcomes, request.years)
    cost_outcomes = [
        outcome
        for outcome in outcomes
        if outcome.status != OutcomeStatus.NO_FISCAL_EFFECT
    ]
    computed = [
        outcome for outcome in cost_outcomes if outcome.status == OutcomeStatus.COMPUTED
    ]
    unresolved = [
        outcome
        for outcome in cost_outcomes
        if outcome.status in {OutcomeStatus.NEEDS_INPUT, OutcomeStatus.NEEDS_EVIDENCE}
    ]
    security = [
        outcome
        for outcome in cost_outcomes
        if outcome.status == OutcomeStatus.SECURITY_RESTRICTED
    ]
    technical = [
        outcome
        for outcome in cost_outcomes
        if outcome.status == OutcomeStatus.TECHNICALLY_UNESTIMABLE
    ]

    if not cost_outcomes:
        disposition = FinalDisposition.NOT_APPLICABLE
        reason = "모든 사건에서 추가 재정지출 또는 재정수입 감소가 없는 것으로 확인되었습니다."
        codes = ("NO_FISCAL_EFFECTS",)
    elif computed:
        if len(computed) != len(cost_outcomes):
            disposition = FinalDisposition.PARTIAL_ESTIMATE
            reason = (
                "계산 가능한 비용항목은 추계하고, 근거·입력 부족 또는 미첨부 검토 항목은 "
                "별도로 남겼습니다."
            )
            codes = ("COMPUTABLE_ITEM_EXISTS_PARTIAL_ESTIMATE",)
        elif _below_reason_1_threshold(
            totals=totals,
            form_type=request.form_type,
            cost_profile=request.cost_profile,
        ):
            disposition = FinalDisposition.NON_ATTACHMENT_1
            reason = "모든 비용항목을 계산한 결과 적용 양식의 미첨부 1호 금액 기준 미만입니다."
            codes = ("COMPLETE_ESTIMATE_BELOW_REASON_1_THRESHOLD",)
        else:
            disposition = FinalDisposition.COST_ESTIMATE
            reason = "모든 비용항목이 계산되었고 미첨부 1호 금액 기준 이상입니다."
            codes = ("COMPLETE_COST_ESTIMATE",)
    elif unresolved:
        disposition = FinalDisposition.REVIEW_REQUIRED
        reason = (
            "필수값이나 적용 근거를 보완하면 계산할 수 있으므로 미첨부 3호로 확정하지 않습니다."
        )
        codes = ("RESOLVABLE_GAPS_REMAIN",)
    elif security and len(security) == len(cost_outcomes):
        disposition = FinalDisposition.NON_ATTACHMENT_2
        reason = "모든 재정수반 사건에 대해 검증된 국가안전보장·군사기밀 근거가 확인되었습니다."
        codes = ("ALL_COST_EVENTS_SECURITY_RESTRICTED",)
    elif technical and len(technical) == len(cost_outcomes):
        disposition = FinalDisposition.NON_ATTACHMENT_3
        reason = (
            "모든 재정수반 사건에서 핵심 변수의 범위를 합리적으로 설정할 수 없다는 "
            "공식 근거가 확인되었고 계산 가능한 항목이 없습니다."
        )
        codes = ("ALL_COST_EVENTS_TECHNICALLY_UNESTIMABLE",)
    else:
        disposition = FinalDisposition.REVIEW_REQUIRED
        reason = "서로 다른 미첨부 사유가 혼재하여 최종 분류를 자동 확정하지 않습니다."
        codes = ("MIXED_UNRESOLVED_DISPOSITIONS",)

    return BillRoutingDecision(
        disposition=disposition,
        label=DISPOSITION_LABELS[disposition],
        reason=reason,
        reason_codes=codes,
        year_totals_thousand=totals,
        outcomes=tuple(outcomes),
        required_actions=_required_actions(outcomes),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def routing_request_from_dict(payload: Mapping[str, Any]) -> BillRoutingRequest:
    routes: list[FiscalRouteRequest] = []
    for raw in payload.get("routes") or ():
        evidence = tuple(
            RoutingEvidence(
                kind=str(row.get("kind") or ""),
                source_ref=str(row.get("source_ref") or ""),
                quote=str(row.get("quote") or ""),
                verified=bool(row.get("verified")),
            )
            for row in raw.get("evidence") or ()
        )
        routes.append(
            FiscalRouteRequest(
                event_id=str(raw.get("event_id") or ""),
                route=str(raw.get("route") or ""),
                description=str(raw.get("description") or ""),
                readiness=RouteReadiness(str(raw.get("readiness") or "ready")),
                payload=dict(raw.get("payload") or {}),
                reason=str(raw.get("reason") or ""),
                missing_variables=tuple(
                    str(value) for value in raw.get("missing_variables") or ()
                ),
                evidence=evidence,
            )
        )
    return BillRoutingRequest(
        routes=tuple(routes),
        form_type=str(payload.get("form_type") or "assembly"),
        years=int(payload.get("years") or 5),
        cost_profile=CostProfile(str(payload.get("cost_profile") or "recurring")),
    )


__all__ = [
    "BillRoutingDecision",
    "BillRoutingRequest",
    "CostProfile",
    "DISPOSITION_LABELS",
    "FinalDisposition",
    "FiscalRouteRequest",
    "OutcomeStatus",
    "ROUTE_FACILITY",
    "ROUTE_ORGANIZATION",
    "ROUTE_PROGRAM",
    "ROUTE_REVENUE",
    "ROUTE_SUBSIDY",
    "ROUTE_WELFARE",
    "RouteOutcome",
    "RouteReadiness",
    "RoutingEvidence",
    "STANDARD_ROUTES",
    "route_bill",
    "routing_request_from_dict",
]
