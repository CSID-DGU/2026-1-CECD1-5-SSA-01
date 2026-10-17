from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class CostComponent:
    kind: str
    formula: str
    operands: tuple[str, ...]
    basis: str
    required: bool = True


@dataclass(frozen=True)
class ComponentFormulaPlan:
    family: str
    formula: str
    components: tuple[CostComponent, ...]
    selection_basis: str
    evidence_alternatives: tuple[str, ...] = ()
    requires_human_input: bool = True


@dataclass(frozen=True)
class CommitteeEventV5:
    name: str
    article_refs: tuple[str, ...]
    texts: tuple[str, ...]
    change_kind: str
    actor: str
    multiplicity: str
    subordinate_bodies: tuple[str, ...] = ()
    optional_subordinate_bodies: tuple[str, ...] = ()
    support_organizations: tuple[str, ...] = ()
    has_support_staff: bool = False
    has_standing_staff: bool = False
    has_standing_members: bool = False
    whole_operating_baseline: bool = False
    source_kind: str = "legal_provision"

    @property
    def context(self) -> str:
        return " ".join(self.texts)


@dataclass
class CommitteeEstimateV5:
    committee_name: str
    article_refs: list[str]
    source_quotes: list[str]
    change_kind: str
    multiplicity: str
    formula_plan: ComponentFormulaPlan
    status: str
    decision: str
    reason_codes: list[str]
    reason: str
    structure_facts: dict[str, Any] = field(default_factory=dict)
    variables: list[dict[str, Any]] = field(default_factory=list)
    selected_precedent_bill: str | None = None
    annual_amount_thousand: int | None = None
    five_year_amount_thousand: int | None = None
    review_fields: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CommitteeEstimateResultV5:
    bill_no: str | None
    bill_name: str
    engine_version: str
    years: int
    estimates: list[CommitteeEstimateV5]
    warnings: list[str] = field(default_factory=list)

    def total_thousand(self) -> int:
        return sum(value.five_year_amount_thousand or 0 for value in self.estimates)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
