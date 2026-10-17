from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from backend.erce_web.committee_estimator_v3.types import CandidateAudit, EvidenceValue


@dataclass(frozen=True)
class CommitteeRelation:
    relation_type: str
    name: str
    article_ref: str
    source_text: str
    mandatory: bool = False
    cost_bearing: bool = False


@dataclass(frozen=True)
class FormulaPlan:
    family: str
    formula: str
    components: tuple[str, ...]
    selection_basis: str
    requires_human_input: bool


@dataclass
class CommitteeEstimateV4:
    committee_name: str
    article_refs: list[str]
    source_quotes: list[str]
    relations: list[CommitteeRelation]
    formula_plan: FormulaPlan
    status: str
    decision: str
    reason_codes: list[str]
    reason: str
    variables: list[EvidenceValue] = field(default_factory=list)
    selected_candidate: CandidateAudit | None = None
    candidate_audits: list[CandidateAudit] = field(default_factory=list)
    annual_amount_thousand: int | None = None
    five_year_amount_thousand: int | None = None
    gross_draft_annual_thousand: int | None = None
    review_fields: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CommitteeEstimateResultV4:
    bill_no: str | None
    bill_name: str
    engine_version: str
    years: int
    estimates: list[CommitteeEstimateV4]
    warnings: list[str] = field(default_factory=list)

    def total_thousand(self) -> int:
        return sum(value.five_year_amount_thousand or 0 for value in self.estimates)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
