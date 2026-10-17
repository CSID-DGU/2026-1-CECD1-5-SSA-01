"""Formula-family-specific precedent resolution for committee v4.

The v3 evidence store represents a simple meeting allowance well, but a
main committee + subordinate committee + support organization is a compound
formula.  This module reads the same precedent profiles and normalizes that
compound formula without consulting the target bill's official estimate.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import re
import statistics

from backend.committee_estimator_v3.evidence_store import candidate_profile
from backend.estimator_v2.retrieval import search_cost_candidates
from backend.estimator_v2.types import TagCandidate

from .structure import CommitteeNode


@dataclass(frozen=True)
class SupportBundleOperands:
    main_paid_members: float
    subordinate_paid_members: float
    annual_meetings: float
    unit_price_won: float
    support_annual_budget_thousand: int

    @property
    def annual_amount_thousand(self) -> int:
        meeting_won = (
            (self.main_paid_members + self.subordinate_paid_members)
            * self.annual_meetings
            * self.unit_price_won
        )
        return int(round(meeting_won / 1_000)) + self.support_annual_budget_thousand


@dataclass(frozen=True)
class SupportBundleMatch:
    candidate: TagCandidate
    operands: SupportBundleOperands
    source_text: str
    independent_support_count: int


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _number(pattern: str, compact: str) -> float | None:
    match = re.search(pattern, compact)
    return float(match.group(1).replace(",", "")) if match else None


def _support_budget_from_table(text: str) -> int | None:
    """Read annual support-organization rows, excluding a table total.

    Official tables commonly contain a half-year first value followed by four
    full-year values and a sum.  The recurring baseline is the median of the
    full-year values; a partial first year is excluded only when it is clearly
    below 75% of the other years.  Values are stored as million won.
    """
    matches = list(re.finditer(r"실무지원단\s*운영비", text or ""))
    for match in reversed(matches):
        window = (text or "")[match.end():match.end() + 220]
        window = re.split(r"합\s*계", window, maxsplit=1)[0]
        values = [
            int(value.replace(",", ""))
            for value in re.findall(r"(?<![.\d])\d{1,3}(?:,\d{3})*(?![.\d])", window)
        ]
        # A usable annual row has at least three yearly observations.  Very
        # large values here are usually years or unrelated notes.
        values = [value for value in values if 0 < value < 10_000]
        if len(values) < 3:
            continue
        core = values[:5]
        if len(core) >= 4:
            later_median = statistics.median(core[1:])
            if core[0] < later_median * 0.75:
                core = core[1:]
        return int(round(statistics.median(core) * 1_000))
    return None


def parse_support_bundle_operands(text: str) -> SupportBundleOperands | None:
    """Normalize all operands of a compound committee precedent."""
    compact = _compact(text)
    main = _number(
        r"지원위원회의위원(?:은|수는)?.{0,40}?"
        r"이중민간위원(?:은|수는)?([\d,]+)명",
        compact,
    )
    subordinate = _number(
        r"실무위원회의위원(?:은|수는)?.{0,40}?"
        r"이중민간위원(?:은|수는)?([\d,]+)명",
        compact,
    )
    meetings = _number(r"각각연([\d,]+)회", compact)
    unit_manwon = _number(r"회의당([\d,.]+)만원", compact)
    support_budget = _support_budget_from_table(text)
    if None in {main, subordinate, meetings, unit_manwon, support_budget}:
        return None
    return SupportBundleOperands(
        main_paid_members=float(main),
        subordinate_paid_members=float(subordinate),
        annual_meetings=float(meetings),
        unit_price_won=float(unit_manwon) * 10_000,
        support_annual_budget_thousand=int(support_budget),
    )


def _is_exact_support_structure(node: CommitteeNode, profile: dict) -> bool:
    target_relations = {relation.relation_type for relation in node.relations}
    return bool(
        target_relations == {"subordinate_committee", "support_organization"}
        and profile.get("has_subcommittee") is True
        and profile.get("has_secretariat") is True
    )


def resolve_support_bundle(
    node: CommitteeNode,
    *,
    bill_no: str | None,
    bill_name: str,
    cutoff_date: str | None,
    refresh: bool,
) -> SupportBundleMatch | None:
    """Select a complete, structurally identical compound precedent.

    Semantic retrieval creates the shortlist.  Relation identity and operand
    completeness are hard evidence gates.  Independent precedents must also
    agree within 20%; otherwise the engine abstains.
    """
    query_event = replace(
        node.event,
        object=f"{node.name} 하위위원회 지원조직 복합 운영",
        action="본위원회 하위위원회 지원조직 설치 및 운영",
    )
    candidates, _ = search_cost_candidates(
        query_event,
        exclude_bill_nos={bill_no} if bill_no else set(),
        exclude_bill_name=bill_name,
        cutoff_date=cutoff_date,
        refresh=refresh,
        k=40,
        min_similarity=0.40,
    )
    matches: list[tuple[TagCandidate, SupportBundleOperands, str, bool]] = []
    for candidate in candidates:
        profile = candidate_profile(candidate)
        if not profile or not _is_exact_support_structure(node, profile):
            continue
        source_text = str(profile.get("source_text") or "")
        operands = parse_support_bundle_operands(source_text)
        if operands is None:
            continue
        profile_name = _compact(str(profile.get("normalized_name") or ""))
        concrete = bool(profile_name and not profile_name.startswith("각종"))
        matches.append((candidate, operands, source_text, concrete))
    if not matches:
        return None

    # One bill can expose both a concrete and an aggregate TAG item.  Keep the
    # most concrete/highest-similarity row per independent bill.
    by_bill: dict[str, tuple[TagCandidate, SupportBundleOperands, str, bool]] = {}
    for match in matches:
        candidate = match[0]
        current = by_bill.get(candidate.bill_no)
        key = (1 if match[3] else 0, candidate.similarity, candidate.item_id)
        current_key = (
            (1 if current[3] else 0, current[0].similarity, current[0].item_id)
            if current else None
        )
        if current_key is None or key > current_key:
            by_bill[candidate.bill_no] = match
    independent = list(by_bill.values())
    amounts = [match[1].annual_amount_thousand for match in independent]
    if len(amounts) >= 2 and max(amounts) / min(amounts) > 1.20:
        return None
    selected = max(
        independent,
        key=lambda match: (
            1 if match[3] else 0,
            match[0].similarity,
            match[0].propose_date,
            match[0].item_id,
        ),
    )
    return SupportBundleMatch(
        candidate=selected[0],
        operands=selected[1],
        source_text=selected[2],
        independent_support_count=len(independent),
    )
