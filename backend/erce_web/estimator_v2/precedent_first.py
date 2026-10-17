"""Precedent-first decision layer for cost-estimate disposition.

This module deliberately does *not* retrieve ``비용추계의 이해와 실제`` or
other methodology documents at runtime.  It separates the work into three
clear responsibilities:

1. an LLM reads the bill and identifies a fiscal factor plus its missing
   variables;
2. this module retrieves only earlier, official local precedents that have a
   matching fiscal mechanism / missing-variable shape;
3. the LLM makes the disposition proposal with those precedents in view and a
   small deterministic gate verifies that a reason-3 proposal is grounded.

A precedent is evidence for the LLM's reasoning, not a template answer to be
copied.  The target bill and all later bills are excluded before an LLM sees
the evidence, preventing answer leakage in holdout evaluation.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .top_level_router import (
    BillRoutingDecision,
    BillRoutingRequest,
    FiscalRouteRequest,
    RouteReadiness,
    RoutingEvidence,
    route_bill,
)


LOCAL_PRECEDENT_VERSION = "precedent-first-local-v1"
_DEFAULT_GENERATED_ROOT = Path("backend/generated")


class LLMConclusion(str, Enum):
    """The LLM's final conclusion for one fiscal factor after retrieval."""

    ESTIMATE = "estimate"
    TECHNICALLY_UNESTIMABLE = "technically_unestimable"
    SECURITY_RESTRICTED = "security_restricted"
    NO_FISCAL_EFFECT = "no_fiscal_effect"
    REVIEW = "review"


@dataclass(frozen=True)
class FiscalFactor:
    """A fiscal factor extracted by the first LLM pass from a bill article."""

    event_id: str
    route: str
    description: str
    article_ref: str
    quote: str
    fiscal_effect: bool
    mechanisms: tuple[str, ...] = ()
    missing_variables: tuple[str, ...] = ()
    payload: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class LocalPrecedent:
    """One official, historical non-attachment precedent stored locally."""

    bill_no: str
    bill_name: str
    propose_date: str
    reason_type: str
    reason_text: str
    evidence_text: str
    mechanisms: tuple[str, ...]
    missing_roles: tuple[str, ...]

    @property
    def source_ref(self) -> str:
        return f"local/non_attachment/{self.bill_no}"

    @property
    def quote(self) -> str:
        text = self.evidence_text or self.reason_text
        return re.sub(r"\s+", " ", text).strip()[:800]


@dataclass(frozen=True)
class PrecedentHit:
    precedent: LocalPrecedent
    score: int
    matched_mechanisms: tuple[str, ...]
    matched_roles: tuple[str, ...]


@dataclass(frozen=True)
class DecisionContext:
    """Evidence supplied to the second LLM pass for one fiscal factor."""

    factor: FiscalFactor
    precedents: tuple[PrecedentHit, ...]


@dataclass(frozen=True)
class LLMFactorDecision:
    """Structured second-pass LLM decision.

    ``precedent_bill_nos`` must name only records provided in ``DecisionContext``.
    This prevents an LLM from inventing citations or using the target answer.
    """

    event_id: str
    conclusion: LLMConclusion
    reason: str
    precedent_bill_nos: tuple[str, ...] = ()


@dataclass(frozen=True)
class PrecedentFirstResult:
    decision: BillRoutingDecision
    contexts: tuple[DecisionContext, ...]
    accepted_decisions: tuple[LLMFactorDecision, ...]


_ROLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("organization_scale", re.compile(r"(?:기관|조직|센터|정원|인력|인원).{0,30}(?:수|규모|정원|자료|미정|곤란)")),
    ("beneficiary_volume", re.compile(r"(?:대상자|수혜자|수급자|지원대상|신청자).{0,30}(?:수|규모|자료|미정|곤란)")),
    ("demand_volume", re.compile(r"(?:신청|사건|처리|수요|업무량|건수).{0,30}(?:수|규모|자료|미정|곤란)")),
    ("unit_cost", re.compile(r"(?:단가|지급액|지원액|감정|속기|비용).{0,30}(?:기준|금액|자료|미정|곤란)")),
    ("implementation_scope", re.compile(r"(?:사업|지원|시행|운영|계획|방안).{0,30}(?:범위|규모|방식|기준|자료|미정|곤란)")),
    ("tax_base", re.compile(r"(?:세수|과세|공시가격|납세자|주택).{0,40}(?:수|규모|자료|파악|곤란|없)")),
)

_MECHANISM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("revenue_change", re.compile(r"세수|조세|과세|세액|공제|감면|부동산세|양도소득세")),
    ("benefit_expansion", re.compile(r"지원대상|수혜자|수급자|지원금|급여|자립지원")),
    ("judicial_procedure", re.compile(r"법원|심리|사실조회|감정|속기|조서|사건")),
    ("organization_operation", re.compile(r"기관|조직|센터|기구|정원|인력|직원")),
    ("facility_asset", re.compile(r"시설|청사|공사|건축|장비|정보시스템")),
    ("program_service", re.compile(r"사업|운영|수행|계획|방안|지원")),
)


def _labels(text: str, patterns: tuple[tuple[str, re.Pattern[str]], ...]) -> tuple[str, ...]:
    compact = re.sub(r"\s+", "", text or "")
    return tuple(label for label, pattern in patterns if pattern.search(compact))


def _read_jsonl(path: Path) -> Iterable[dict]:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield json.loads(line)
    except (OSError, json.JSONDecodeError):
        return


@lru_cache(maxsize=2)
def _load_local_precedents(generated_root: str) -> tuple[LocalPrecedent, ...]:
    """Load and deduplicate official local 3호 examples without remote access."""
    root = Path(generated_root)
    dates: dict[str, str] = {}
    for path in root.glob("**/bills.jsonl"):
        for row in _read_jsonl(path):
            bill_no = str(row.get("billNo") or row.get("bill_no") or "")
            date = str(row.get("proposeDate") or row.get("propose_date") or "")
            if bill_no and date:
                dates.setdefault(bill_no, date)

    records: dict[str, LocalPrecedent] = {}
    for path in root.glob("**/non_attachment_classifications.jsonl"):
        for row in _read_jsonl(path):
            # NABO export uses B for the rule's third non-attachment reason.
            if str(row.get("reason_type") or "").upper() != "B":
                continue
            bill_no = str(row.get("bill_no") or row.get("billNo") or "")
            if not bill_no or bill_no in records:
                continue
            reason = str(row.get("reason_text") or "")
            evidence = str(row.get("evidence_text") or "")
            text = f"{reason} {evidence}"
            records[bill_no] = LocalPrecedent(
                bill_no=bill_no,
                bill_name=str(row.get("bill_name") or row.get("billName") or ""),
                propose_date=dates.get(bill_no, ""),
                reason_type="B",
                reason_text=reason,
                evidence_text=evidence,
                mechanisms=_labels(text, _MECHANISM_PATTERNS),
                missing_roles=_labels(text, _ROLE_PATTERNS),
            )
    return tuple(sorted(records.values(), key=lambda row: row.bill_no))


class LocalPrecedentIndex:
    """Historical official reason-3 records held in the local generated data."""

    def __init__(self, precedents: Sequence[LocalPrecedent]) -> None:
        self._precedents = tuple(precedents)

    @classmethod
    def from_generated(cls, root: Path = _DEFAULT_GENERATED_ROOT) -> "LocalPrecedentIndex":
        return cls(_load_local_precedents(str(root)))

    def search(
        self,
        factor: FiscalFactor,
        *,
        target_bill_no: str | None,
        cutoff_date: str | None,
        limit: int = 3,
    ) -> tuple[PrecedentHit, ...]:
        """Return earlier official cases matching the factor's evidence shape.

        Ranking uses only stable mechanism and missing-variable labels.  It
        intentionally does not compare raw target text with a target's own
        official result, and it never retrieves future bills.
        """
        wanted_mechanisms = set(factor.mechanisms)
        wanted_roles = set(factor.missing_variables)
        hits: list[PrecedentHit] = []
        for precedent in self._precedents:
            if target_bill_no and precedent.bill_no == target_bill_no:
                continue
            if cutoff_date and (not precedent.propose_date or precedent.propose_date > cutoff_date):
                continue
            mechanisms = tuple(sorted(wanted_mechanisms.intersection(precedent.mechanisms)))
            roles = tuple(sorted(wanted_roles.intersection(precedent.missing_roles)))
            # A mechanism match is mandatory.  A role match improves the rank
            # but is not mandatory because official prose often omits labels.
            if not mechanisms:
                continue
            score = 10 * len(mechanisms) + 3 * len(roles)
            hits.append(PrecedentHit(precedent, score, mechanisms, roles))
        return tuple(sorted(hits, key=lambda hit: (-hit.score, hit.precedent.bill_no))[:limit])


def build_decision_prompt(contexts: Sequence[DecisionContext]) -> str:
    """Create the second-pass LLM prompt without methodology-document RAG."""
    blocks: list[str] = []
    for context in contexts:
        factor = context.factor
        precedents = "\n".join(
            f"- [{hit.precedent.bill_no}] {hit.precedent.bill_name}: {hit.precedent.quote}"
            for hit in context.precedents
        ) or "- (적합한 선례 없음)"
        blocks.append(
            "\n".join(
                (
                    f"[사건 {factor.event_id}] {factor.description}",
                    f"조문: {factor.article_ref} / 근거: {factor.quote}",
                    f"재정 메커니즘: {', '.join(factor.mechanisms) or '미분류'}",
                    f"확인되지 않은 변수: {', '.join(factor.missing_variables) or '없음'}",
                    "과거 공식 미첨부 3호 선례:",
                    precedents,
                )
            )
        )
    return """당신은 국회 비용추계 판단자입니다.

법안의 현재 조문과 아래의 과거 공식 선례를 근거로 각 사건을 판단하세요.
선례는 정답을 복사하는 자료가 아니라, 현재 사건의 누락 변수와 재정 메커니즘이
정말 같은지 확인하는 근거입니다. 금액을 임의로 만들지 마세요.

각 사건에 대해 estimate / technically_unestimable / security_restricted /
no_fiscal_effect / review 중 하나를 선택하고, technically_unestimable이면
반드시 아래에 제시된 선례 번호만 인용하세요.

""" + "\n\n".join(blocks)


def build_contexts(
    factors: Sequence[FiscalFactor],
    *,
    index: LocalPrecedentIndex,
    target_bill_no: str | None,
    cutoff_date: str | None,
) -> tuple[DecisionContext, ...]:
    return tuple(
        DecisionContext(
            factor=factor,
            precedents=index.search(
                factor,
                target_bill_no=target_bill_no,
                cutoff_date=cutoff_date,
            ) if factor.fiscal_effect else (),
        )
        for factor in factors
    )


def _evidence_for(
    decision: LLMFactorDecision,
    context: DecisionContext,
) -> tuple[RoutingEvidence, ...]:
    allowed = {hit.precedent.bill_no: hit for hit in context.precedents}
    selected = [allowed[bill_no] for bill_no in decision.precedent_bill_nos if bill_no in allowed]
    return tuple(
        RoutingEvidence(
            kind="official_non_attachment",
            source_ref=hit.precedent.source_ref,
            quote=hit.precedent.quote,
            # The source is an official NABO document extracted into the local
            # corpus.  This verifies provenance, not that it is identical to
            # the target; mechanism/role matching above handles compatibility.
            verified=True,
        )
        for hit in selected
    )


def route_llm_decisions(
    contexts: Sequence[DecisionContext],
    decisions: Sequence[LLMFactorDecision],
    *,
    form_type: str = "assembly",
    years: int = 5,
) -> PrecedentFirstResult:
    """Validate LLM decisions and hand eligible cases to the top-level router."""
    by_id = {decision.event_id: decision for decision in decisions}
    requests: list[FiscalRouteRequest] = []
    accepted: list[LLMFactorDecision] = []
    for context in contexts:
        factor = context.factor
        decision = by_id.get(factor.event_id)
        if decision is None:
            requests.append(FiscalRouteRequest(
                event_id=factor.event_id,
                route=factor.route,
                description=factor.description,
                readiness=RouteReadiness.NEEDS_EVIDENCE,
                reason="LLM의 최종 판단이 없어 근거 확인이 필요합니다.",
                missing_variables=factor.missing_variables,
            ))
            continue
        accepted.append(decision)
        if not factor.fiscal_effect or decision.conclusion == LLMConclusion.NO_FISCAL_EFFECT:
            readiness = RouteReadiness.NO_FISCAL_EFFECT
            evidence: tuple[RoutingEvidence, ...] = ()
        elif decision.conclusion == LLMConclusion.TECHNICALLY_UNESTIMABLE:
            evidence = _evidence_for(decision, context)
            # Do not turn an unsupported LLM assertion into reason 3.
            readiness = (
                RouteReadiness.TECHNICALLY_UNESTIMABLE
                if factor.missing_variables and evidence
                else RouteReadiness.NEEDS_EVIDENCE
            )
        elif decision.conclusion == LLMConclusion.SECURITY_RESTRICTED:
            readiness = RouteReadiness.SECURITY_RESTRICTED
            evidence = ()
        elif decision.conclusion == LLMConclusion.ESTIMATE:
            readiness = RouteReadiness.READY
            evidence = ()
        else:
            readiness = RouteReadiness.NEEDS_EVIDENCE
            evidence = ()
        requests.append(FiscalRouteRequest(
            event_id=factor.event_id,
            route=factor.route,
            description=factor.description,
            readiness=readiness,
            payload=factor.payload,
            reason=decision.reason,
            missing_variables=factor.missing_variables,
            evidence=evidence,
        ))

    routed = route_bill(BillRoutingRequest(
        routes=tuple(requests),
        form_type=form_type,
        years=years,
    ))
    return PrecedentFirstResult(routed, tuple(contexts), tuple(accepted))


__all__ = [
    "DecisionContext",
    "FiscalFactor",
    "LLMConclusion",
    "LLMFactorDecision",
    "LOCAL_PRECEDENT_VERSION",
    "LocalPrecedent",
    "LocalPrecedentIndex",
    "PrecedentFirstResult",
    "PrecedentHit",
    "build_contexts",
    "build_decision_prompt",
    "route_llm_decisions",
]
