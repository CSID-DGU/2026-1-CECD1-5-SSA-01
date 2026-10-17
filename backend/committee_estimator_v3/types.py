from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvidenceValue:
    key: str
    label: str
    value: float | None
    unit: str
    provenance: str
    source_id: str
    source_text: str
    requires_review: bool = False


@dataclass(frozen=True)
class CandidateAudit:
    item_id: str
    bill_no: str
    bill_name: str
    item_name: str
    embedding_similarity: float
    scores: dict[str, int]
    accepted: bool
    rejection_reasons: tuple[str, ...] = ()

    @property
    def total_score(self) -> int:
        return sum(self.scores.values())


@dataclass
class CommitteeEstimate:
    committee_name: str
    article_refs: list[str]
    source_quotes: list[str]
    status: str
    reason_codes: list[str]
    reason: str
    formula: str = "순증 수당 지급대상 인원 × 연간 회의 횟수 × 1인 1회당 수당"
    variables: list[EvidenceValue] = field(default_factory=list)
    selected_candidate: CandidateAudit | None = None
    candidate_audits: list[CandidateAudit] = field(default_factory=list)
    annual_amount_thousand: int | None = None
    five_year_amount_thousand: int | None = None
    gross_draft_annual_thousand: int | None = None
    evidence_coverage: float = 0.0
    calibrated_confidence: float = 0.0
    review_fields: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CommitteeEstimateResult:
    bill_no: str | None
    bill_name: str
    engine_version: str
    years: int
    estimates: list[CommitteeEstimate]
    warnings: list[str] = field(default_factory=list)

    def total_thousand(self) -> int:
        return sum(value.five_year_amount_thousand or 0 for value in self.estimates)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
