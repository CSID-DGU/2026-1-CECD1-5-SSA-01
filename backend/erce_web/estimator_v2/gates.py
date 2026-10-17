from __future__ import annotations

import re
from dataclasses import dataclass, field

from .types import AtomicEvent, EventType, RowStatus


@dataclass(frozen=True)
class GateDecision:
    automatic: bool
    status: RowStatus
    reason: str
    reason_codes: list[str] = field(default_factory=list)


_PUBLIC_BEARERS = {"state", "local"}
_AUTO_TYPES = {EventType.COMMITTEE.value, EventType.RESEARCH_PLAN.value}


def _is_formula_ready_discretionary_committee(event: AtomicEvent) -> bool:
    """Return true for an auditable *conditional* committee scenario.

    A discretionary clause does not prove that expenditure will occur.  NABO
    cost estimates can nevertheless show an "if established" scenario when
    the statute identifies both the committee and its numerical composition.
    Keep this exception deliberately narrow: it must not promote vague
    discretionary programmes or organizations into automatic estimates.
    """
    if event.event_type != EventType.COMMITTEE.value:
        return False
    if event.bearer not in _PUBLIC_BEARERS:
        return False
    if event.additionality not in {"explicit_new_or_expanded", "incremental"}:
        return False

    source = re.sub(
        r"\s+",
        "",
        " ".join([event.object, event.action, *event.quotes]),
    )
    has_committee_identity = bool(
        re.search(r"(?:위원회|협의회|심의회|자문회)", source)
    )
    has_installation_clause = bool(
        re.search(
            r"(?:위원회|협의회|심의회|자문회).{0,30}"
            r"(?:둔다|둘수있다|설치한다|설치할수있다)",
            source,
        )
    )
    has_explicit_composition = bool(
        re.search(
            r"(?:위원장\s*\d+\s*명.{0,30})?"
            r"\d+\s*(?:명|인)(?:\s*이내)?(?:의)?\s*위원",
            source,
        )
        or re.search(
            r"위원.{0,30}\d+\s*(?:명|인)(?:\s*이내)?(?:으로)?\s*구성",
            source,
        )
    )
    return (
        has_committee_identity
        and has_installation_clause
        and has_explicit_composition
    )


def _is_cost_bearing_research_artifact(event: AtomicEvent) -> bool:
    """Separate a produced plan/study from a policy decision or agenda item."""
    source = re.sub(
        r"\s+",
        "",
        " ".join(
            [
                event.action,
                event.object,
                event.cost_mechanism,
                event.explanation,
                *event.quotes,
            ]
        ),
    )
    return bool(
        re.search(
            r"계획(?:을)?수립|실태조사|조사(?:를)?실시|연구(?:를)?수행"
            r"|연구용역|평가(?:를)?실시|통계(?:를)?작성|분석(?:을)?실시",
            source,
        )
    )


def _is_subordinate_rulemaking_clause(event: AtomicEvent) -> bool:
    """Return true when a clause only delegates implementation details.

    Such a clause may constrain another cost event, but promulgating the
    implementing decree is not a second independent fiscal event.
    """
    if event.event_type != EventType.ADMINISTRATIVE.value:
        return False
    action = re.sub(r"\s+", "", event.action or "")
    source = re.sub(
        r"\s+",
        "",
        " ".join([event.object, *event.quotes]),
    )
    return bool(
        re.search(r"정한다|위임", action)
        and re.search(r"대통령령|총리령|부령|조례|규칙", source)
        and re.search(r"필요한사항|범위|방법|절차|기준", source)
    )


def assess_event(event: AtomicEvent) -> GateDecision:
    """Decide whether an event may enter automatic analogy estimation.

    The gate primarily consumes the grounded, typed event contract produced by
    ``detect``.  It also recognises the narrow legal form of an implementing-
    rule delegation so that it is not counted as a second cost event.  A
    retrieved precedent cannot turn an ineligible event into an estimable one.
    """
    if not event.grounded:
        return GateDecision(
            False,
            RowStatus.EXCLUDED,
            "원문에서 인용문을 확인할 수 없어 자동 계산에서 제외합니다.",
            ["UNGROUNDED_EVENT"],
        )
    if event.obligation == "declarative":
        return GateDecision(
            False,
            RowStatus.EXCLUDED,
            "목적·책무 등 선언적 규정은 독립 비용사건으로 계산하지 않습니다.",
            ["DECLARATIVE_ONLY"],
        )
    if event.additionality == "existing_or_unchanged":
        return GateDecision(
            False,
            RowStatus.EXCLUDED,
            "현행 유지 사건으로 판정되어 추가재정소요에서 제외합니다.",
            ["NO_ADDITIONALITY"],
        )
    if _is_subordinate_rulemaking_clause(event):
        return GateDecision(
            False,
            RowStatus.EXCLUDED,
            "하위법령에 세부사항을 위임하는 조항은 다른 비용사건의 조건이지 독립 비용사건이 아닙니다.",
            ["IMPLEMENTING_RULEMAKING_NOT_INDEPENDENT_COST_EVENT"],
        )
    if (
        event.obligation == "discretionary"
        and _is_formula_ready_discretionary_committee(event)
    ):
        return GateDecision(
            True,
            RowStatus.COMPUTED_REVIEW,
            "설치 여부는 재량이므로 실제 지출로 단정하지 않고, 조문에 명시된 "
            "위원회 구성에 따라 '설치할 경우'의 조건부 금액을 계산합니다.",
            ["CONDITIONAL_DISCRETIONARY_COMMITTEE_SCENARIO"],
        )
    if event.obligation == "discretionary":
        return GateDecision(
            False,
            RowStatus.NEEDS_EVIDENCE,
            "임의규정은 실제 시행 여부를 확인하기 전에는 자동 계산하지 않습니다.",
            ["DISCRETIONARY_EXECUTION_UNKNOWN"],
        )
    if event.bearer in {"private", "unclear"}:
        return GateDecision(
            False,
            RowStatus.NEEDS_EVIDENCE,
            "비용 부담 주체가 공공재정인지 확인되지 않았습니다.",
            ["PUBLIC_BEARER_UNPROVEN"],
        )
    if event.event_type == EventType.ADMINISTRATIVE.value:
        return GateDecision(
            False,
            RowStatus.NEEDS_EVIDENCE,
            "보고·감사·평가 등 행정행위는 별도 인력·용역·예산의 증가가 입증될 때만 계산합니다.",
            ["ADMIN_ADDITIONALITY_UNPROVEN"],
        )
    if event.event_type == EventType.OTHER.value:
        return GateDecision(
            False,
            RowStatus.NEEDS_EVIDENCE,
            "비용 구조가 특정되지 않아 총액 선례를 임의로 준용하지 않습니다.",
            ["UNSUPPORTED_COST_STRUCTURE"],
        )
    if event.bearer == "public_institution":
        return GateDecision(
            False,
            RowStatus.NEEDS_EVIDENCE,
            "개별 공공기관의 내부 이행비용은 대상 기관 수와 추가 예산 부담을 확인해야 합니다.",
            ["INSTITUTION_SCALE_UNKNOWN"],
        )
    if (
        event.event_type == EventType.RESEARCH_PLAN.value
        and not _is_cost_bearing_research_artifact(event)
    ):
        return GateDecision(
            False,
            RowStatus.NEEDS_EVIDENCE,
            "위원회의 심의 안건·정책 결정·예산 편성은 그 자체가 조사·연구·계획 "
            "용역은 아닙니다. 별도 사업비가 확인되기 전에는 연구비 선례를 적용하지 "
            "않습니다.",
            ["POLICY_DECISION_NOT_RESEARCH_ARTIFACT"],
        )
    if (
        event.event_type == EventType.RESEARCH_PLAN.value
        and event.additionality == "possibly_incremental"
    ):
        return GateDecision(
            False,
            RowStatus.NEEDS_EVIDENCE,
            "조사·연구 의무는 확인되지만 기존 사업·예산으로 수행 가능한지 "
            "확정되지 않았습니다. 신규·증액 근거를 확인해야 합니다.",
            ["RESEARCH_ADDITIONALITY_UNPROVEN"],
        )
    if event.event_type not in _AUTO_TYPES or event.bearer not in _PUBLIC_BEARERS:
        return GateDecision(
            False,
            RowStatus.NEEDS_EVIDENCE,
            "현재 v2 자동계산 범위 밖입니다. 산식·대상 수·단가를 확인해야 합니다.",
            ["OUTSIDE_AUTO_SCOPE"],
        )
    if event.additionality == "unknown":
        return GateDecision(
            False,
            RowStatus.NEEDS_EVIDENCE,
            "현행 대비 신규·확대인지 확인되지 않았습니다.",
            ["ADDITIONALITY_UNKNOWN"],
        )
    if event.obligation not in {"mandatory", "unclear"}:
        return GateDecision(
            False,
            RowStatus.NEEDS_EVIDENCE,
            "의무성과 시행 가능성을 확인해야 합니다.",
            ["OBLIGATION_UNRESOLVED"],
        )
    return GateDecision(
        True,
        RowStatus.COMPUTED_REVIEW,
        "원문 근거·공공 부담·비용 구조·추가성이 자동계산 게이트를 통과했습니다.",
        ["AUTO_GATE_PASSED"],
    )
