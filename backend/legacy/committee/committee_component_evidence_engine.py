"""Typed, component-wise committee evidence recommendations (experimental).

The previous experiment selected one structurally similar committee and
borrowed all operands from it.  This engine deliberately does not select a
single precedent.  It builds separate evidence channels for member counts,
meeting cadence, and per-person/per-meeting allowance, then leaves every
unsupported operand to HITL.

It is isolated from ``tag_pipeline`` and ``server`` and never emits a total.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
import statistics
from typing import Any

from backend.committee_component_recommender import (
    _Target,
    _available_dates,
    _build_target,
    _target_contexts,
)


ENGINE_VERSION = "committee-component-evidence-v0.3.0"
PROFILE_PATH = Path("backend/generated/committee_evidence_v1/committee_profiles.jsonl")
ATOM_PATH = Path("backend/generated/committee_evidence_v1/committee_evidence_atoms.jsonl")

_ACTUAL_MARKERS = re.compile(
    r"실적|운영사례|개최하였|개최됨|최근\d*년|현황|"
    r"\d{4}년.{0,30}\d+회"
)
_PRICE_ROLE = re.compile(r"수당|사례금|회의비|참석비")
_PER_PERSON_ROLE = re.compile(
    r"1인당|인당|1명당|명당|명·회|명/회|인/회|"
    r"수당단가|민간위원수당|회의수당단가|1회당|회당"
)
_WHOLE_COST = re.compile(
    r"운영비|운영경비|사무국|사무처|기획단|예산금액|"
    r"예산.{0,8}준용|1개월운영비|연간운영비|회의당운영비용"
)
_MONEY_MANWON = re.compile(r"(\d+(?:\.\d+)?)만원")


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@dataclass(frozen=True)
class EvidenceSource:
    bill_no: str
    committee_name: str
    value: float
    unit: str
    evidence_kind: str
    source_text: str
    basis_year: int | None


@dataclass(frozen=True)
class OperandSuggestion:
    role: str
    unit: str
    low: float
    high: float
    representative: float
    confidence: str
    evidence_count: int
    sources: tuple[EvidenceSource, ...]


@dataclass(frozen=True)
class TargetOperand:
    role: str
    value: float
    unit: str
    source: str


@dataclass(frozen=True)
class ComponentEvidenceResult:
    bill_no: str
    target_name: str
    formula: str
    decision: str
    target_operands: tuple[TargetOperand, ...]
    suggestions: tuple[OperandSuggestion, ...]
    missing_roles: tuple[str, ...]
    point_amount_won: None = None
    amount_range_won: None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@lru_cache(maxsize=1)
def _profiles() -> tuple[dict[str, Any], ...]:
    return tuple(_read_jsonl(PROFILE_PATH))


@lru_cache(maxsize=1)
def _atoms() -> tuple[dict[str, Any], ...]:
    return tuple(_read_jsonl(ATOM_PATH))


@lru_cache(maxsize=1)
def _profile_index() -> dict[str, dict[str, Any]]:
    return {str(row["profile_key"]): row for row in _profiles()}


def _available(atom: dict[str, Any], *, target_bill_no: str, cutoff: str) -> bool:
    profile = _profile_index().get(str(atom.get("profile_key") or ""), {})
    bill_no = str(profile.get("bill_no") or "")
    available_date = str(_available_dates().get(bill_no) or "")
    return bool(
        bill_no
        and bill_no != target_bill_no
        and available_date
        and (not cutoff or available_date <= cutoff)
    )


def _kind(atom: dict[str, Any]) -> str:
    text = _compact(str(atom.get("source_text") or ""))
    derivation = str(atom.get("derivation_type") or "")
    # Explicit derivation metadata wins over surface words.  A sentence such
    # as "the current body met monthly, therefore assume 12 meetings" is an
    # assumption, not a reported actual for the proposed body.
    if derivation in {"assumption", "analogy", "reverse_engineered"}:
        if "지침" in text:
            return "official_guideline_prior"
        return "weak_prior"
    if derivation == "official_guideline":
        return "official_guideline"
    if derivation == "reported_actual":
        return "reported_actual"
    if derivation == "direct_statement" and "가정" not in text and _ACTUAL_MARKERS.search(text):
        return "reported_actual"
    if "가정" in text or "준용" in text:
        return "weak_prior"
    return "document_statement"


def _subject_matches_profile(atom: dict[str, Any]) -> bool:
    """Reject facts about an unnamed comparator stored under the target profile.

    The v1 schema has no evidence-subject column.  Until v2 adds it, an
    operational actual is transferable only when the profile's committee name
    occurs in the evidence sentence itself.  This is intentionally
    conservative and affects suggestions only.
    """
    profile = _profile_index().get(str(atom.get("profile_key") or ""), {})
    subject = _compact(
        str(profile.get("normalized_name") or profile.get("committee_name") or "")
    )
    text = _compact(str(atom.get("source_text") or ""))
    return bool(subject and subject in text)


def _price_value(atom: dict[str, Any]) -> float | None:
    """Return only a per-person/per-meeting allowance, never an operating budget."""
    text = _compact(str(atom.get("source_text") or ""))
    if not _PRICE_ROLE.search(text) or not _PER_PERSON_ROLE.search(text):
        return None
    if _WHOLE_COST.search(text):
        return None
    try:
        value = float(atom.get("normalized_value"))
    except (TypeError, ValueError):
        return None
    if 0 < value <= 1_000_000:
        return value
    # Repair scale mistakes only from the evidence sentence itself.  For
    # example, a stored 4,000,000 with source ``40만원`` becomes 400,000.
    textual = [float(number) * 10_000 for number in _MONEY_MANWON.findall(text)]
    plausible = [number for number in textual if 0 < number <= 1_000_000]
    return max(plausible) if plausible else None


def _observation(
    atom: dict[str, Any],
    *,
    value: float,
    unit: str,
) -> EvidenceSource:
    profile = _profile_index()[str(atom["profile_key"])]
    return EvidenceSource(
        bill_no=str(profile.get("bill_no") or ""),
        committee_name=str(profile.get("normalized_name") or profile.get("committee_name") or ""),
        value=value,
        unit=unit,
        evidence_kind=_kind(atom),
        source_text=str(atom.get("source_text") or "")[:500],
        basis_year=(int(atom["basis_year"]) if atom.get("basis_year") is not None else None),
    )


def _suggestion(
    role: str,
    unit: str,
    sources: list[EvidenceSource],
    *,
    confidence: str,
) -> OperandSuggestion | None:
    if not sources:
        return None
    # Repeated rows of the same committee/value do not become independent
    # evidence merely because several atoms restate them.
    unique: dict[tuple[str, str, float], EvidenceSource] = {}
    for source in sources:
        unique.setdefault((source.bill_no, source.committee_name, source.value), source)
    rows = list(unique.values())
    values = sorted(source.value for source in rows)
    return OperandSuggestion(
        role=role,
        unit=unit,
        low=min(values),
        high=max(values),
        representative=float(statistics.median(values)),
        confidence=confidence,
        evidence_count=len(rows),
        sources=tuple(rows[:8]),
    )


def _price_suggestion(case: dict[str, Any]) -> OperandSuggestion | None:
    target_bill_no = str(case["bill_no"])
    cutoff = str(case.get("cutoff_date") or case.get("propose_date") or "")
    rows: list[EvidenceSource] = []
    for atom in _atoms():
        if atom.get("evidence_role") != "meeting_unit_price":
            continue
        if not _available(atom, target_bill_no=target_bill_no, cutoff=cutoff):
            continue
        value = _price_value(atom)
        if value is None:
            continue
        kind = _kind(atom)
        if kind not in {"official_guideline", "official_guideline_prior"}:
            continue
        rows.append(_observation(atom, value=value, unit="원/인·회"))
    return _suggestion(
        "meeting_unit_price",
        "원/인·회",
        rows,
        confidence="guideline_reference",
    )


def _meeting_suggestion(
    case: dict[str, Any],
    target: _Target,
) -> OperandSuggestion | None:
    target_bill_no = str(case["bill_no"])
    cutoff = str(case.get("cutoff_date") or case.get("propose_date") or "")
    rows: list[EvidenceSource] = []
    for atom in _atoms():
        if atom.get("evidence_role") != "annual_meetings":
            continue
        if not _available(atom, target_bill_no=target_bill_no, cutoff=cutoff):
            continue
        if _kind(atom) != "reported_actual":
            continue
        if not _subject_matches_profile(atom):
            continue
        profile = _profile_index().get(str(atom.get("profile_key") or ""), {})
        if str(profile.get("function_class") or "general") != target.function_class:
            continue
        try:
            value = float(atom.get("normalized_value"))
        except (TypeError, ValueError):
            continue
        if not 0 < value <= 365:
            continue
        rows.append(_observation(atom, value=value, unit="회/년"))
    return _suggestion(
        "annual_meetings",
        "회/년",
        rows,
        confidence="same_function_reported_actual",
    )


def _paid_member_suggestion(
    case: dict[str, Any],
    target: _Target,
) -> OperandSuggestion | None:
    if target.total_high is None:
        return None
    target_bill_no = str(case["bill_no"])
    cutoff = str(case.get("cutoff_date") or case.get("propose_date") or "")
    rows: list[EvidenceSource] = []
    for atom in _atoms():
        if atom.get("evidence_role") != "paid_members":
            continue
        if not _available(atom, target_bill_no=target_bill_no, cutoff=cutoff):
            continue
        if _kind(atom) != "reported_actual":
            continue
        profile = _profile_index().get(str(atom.get("profile_key") or ""), {})
        total = profile.get("total_member_count")
        try:
            paid = float(atom.get("normalized_value"))
            total_value = float(total)
        except (TypeError, ValueError):
            continue
        if not (0 < paid <= total_value and total_value > 0):
            continue
        scaled = max(1.0, min(target.total_high, round(target.total_high * paid / total_value)))
        rows.append(_observation(atom, value=scaled, unit="명"))
    return _suggestion(
        "paid_members",
        "명",
        rows,
        confidence="reported_actual_ratio_prior",
    )


def _target_operands(target: _Target) -> tuple[TargetOperand, ...]:
    rows = [
        TargetOperand("committee_instances", target.instances, "개", "bill_text")
    ]
    if target.total_high is not None:
        rows.append(
            TargetOperand(
                "total_members_cap" if target.total_kind == "cap" else "total_members",
                target.total_high,
                "명",
                "bill_text",
            )
        )
    if target.paid_exact is not None:
        rows.append(TargetOperand("paid_members", target.paid_exact, "명", "bill_text"))
    elif target.paid_floor is not None:
        rows.append(TargetOperand("paid_members_floor", target.paid_floor, "명 이상", "bill_text"))
    if target.meetings_exact is not None:
        rows.append(TargetOperand("annual_meetings", target.meetings_exact, "회/년", "bill_text"))
    return tuple(rows)


def _recommend_target(case: dict[str, Any], target: _Target) -> ComponentEvidenceResult:
    target_rows = _target_operands(target)
    exact_roles = {row.role for row in target_rows}
    suggestions = [
        _paid_member_suggestion(case, target)
        if "paid_members" not in exact_roles
        else None,
        _meeting_suggestion(case, target)
        if "annual_meetings" not in exact_roles
        else None,
        _price_suggestion(case),
    ]
    available_suggestions = tuple(row for row in suggestions if row is not None)
    missing: list[str] = []
    if "paid_members" not in exact_roles:
        missing.append("paid_members")
    if "annual_meetings" not in exact_roles:
        missing.append("annual_meetings")
    missing.append("meeting_unit_price")
    # Suggestions are priors, not confirmed target values, so they remain in
    # missing_roles until a reviewer accepts or replaces them.
    return ComponentEvidenceResult(
        bill_no=str(case["bill_no"]),
        target_name=target.name,
        formula="committee_instances * paid_members * annual_meetings * meeting_unit_price",
        decision="needs_user_input",
        target_operands=target_rows,
        suggestions=available_suggestions,
        missing_roles=tuple(missing),
    )


def recommend(case: dict[str, Any]) -> list[ComponentEvidenceResult]:
    targets = [_build_target(name, context) for name, context in _target_contexts(case)]
    return [_recommend_target(case, target) for target in targets]
