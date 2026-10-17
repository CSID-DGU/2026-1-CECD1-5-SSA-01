"""Shadow-only fallback for evidence buried in precedent narratives.

The primary estimator remains authoritative.  This module only attaches
candidate evidence to unresolved rows; it never changes a row's status,
formula, variables, recurrence or amount.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re
from typing import Iterable

from ..analyzer_v2 import GEMINI_MODEL, gemini_json
from .cache import get_or_create_json
from .evidence_index import EVIDENCE_INDEX_VERSION, search_evidence_atoms
from .retrieval import target_metadata
from .types import EstimateResult, EstimateRow, RowStatus


SHADOW_FALLBACK_VERSION = "narrative-evidence-shadow-v1"
SHADOW_SELECTION_VERSION = "narrative-evidence-rerank-v2"

_ELIGIBLE_REASON_CODES = {
    "NO_SEMANTIC_PRECEDENT",
    "NO_TRANSFERABLE_PRECEDENT",
    "SELECTED_PRECEDENT_NOT_COMPUTABLE",
    "NO_TRANSFERABLE_ORGANIZATION_CASE",
    "NO_TRANSFERABLE_ORGANIZATION_STRUCTURE",
    "TARGET_ANNUAL_OPERATING_BUDGET_MISSING",
    "INSTITUTION_SCALE_UNKNOWN",
    "DISCRETIONARY_EXECUTION_UNKNOWN",
}

_GROUPS: dict[str, tuple[set[str], set[str]]] = {
    "governance_operation": (
        {"organization_change", "committee_operation"},
        {"support_office", "organization_operation", "committee_operation"},
    ),
    "personnel": ({"personnel"}, {"personnel"}),
    "research_plan": ({"research_plan"}, {"research_plan"}),
    "facility_system": ({"facility_system"}, {"facility_system"}),
    "subsidy": ({"subsidy"}, {"subsidy"}),
    "tax_revenue": ({"tax_revenue"}, {"tax_revenue"}),
}


@dataclass(frozen=True)
class ShadowGroup:
    name: str
    scopes: set[str]
    rows: tuple[EstimateRow, ...]
    context_rows: tuple[EstimateRow, ...]
    query: str


_FINITE_LIFECYCLE_PATTERN = re.compile(
    r"활동\s*기간|존속\s*기간|한시|해산|기간\s*만료|"
    r"\d+\s*(?:년|개월)(?:\s*\d+\s*개월)?\s*(?:동안|간)?\s*활동"
)

_SELECTION_PROMPT = """당신은 비용추계 근거 선례를 고르는 심사위원이다.
후보는 이미 대상 의안 자체, 미래 자료, 비용유형 불일치가 1차 제거된 결과다.
먼저 여러 대상 비용사건을 한꺼번에 덮는 운영 패키지 선례가 있는지 판단한다.
패키지로 덮이지 않은 사건에만 개별 근거 원자 하나를 고르거나 없음을 선언한다.

판단 우선순위:
1. 비용범위가 같은가: 사무처 전체 운영비인지, 위원회 회의비인지, 인건비인지
2. 상설/한시 등 수명주기와 조직 법형식이 양립하는가
3. 수행 기능, 부담 주체, 대상 집단이 의미상 가까운가
4. 금액의 단위·기간·구성항목과 출처가 문장 또는 표 안에서 확인 가능한가
5. 마지막으로 임베딩 유사도를 참고한다

범위 판단:
- 같은 상위기관 아래 여러 위원회·분과·사무조직이 함께 신설되면, 이름이 같은
  작은 회의비 하나보다 기능과 조직 규모가 비슷한 전체 운영 패키지 선례를 우선한다.
- 반대로 대상이 명백히 한 위원회의 회의수당뿐이면 전체 기관예산을 고르지 않는다.
- 패키지 선례를 여러 사건에 중복 적용해서는 안 되므로 이유에 포괄 범위를 명시한다.
- target_packages에 2개 이상의 관련 사건이 있으면 전체 범위·기능·규모를 실제로
  함께 담은 후보가 있는지 먼저 판단한다. 패키지를 선택했다면 covered_event_ids의
  사건에는 같은 금액을 개별로 다시 배정하지 않는다.

금지:
- 정답 금액을 추측하거나 금액이 비슷해 보인다는 이유로 고르지 마라.
- 여러 선례의 숫자를 섞지 마라.
- 비용범위가 다르면 단어가 비슷해도 고르지 마라.
- 적합한 후보가 없으면 반드시 빈 atom_id를 반환하라.

JSON만 반환:
{"packages":[{"package_id":"P001","covered_event_ids":["E001","E002"],
"atom_id":"정확한 후보 ID 또는 빈 문자열","reason":"전체 포괄 범위 선택 이유",
"confidence":0.0}],
"assignments":[{"event_id":"E003","atom_id":"정확한 후보 ID 또는 빈 문자열",
"reason":"비용범위·수명주기·기능에 근거한 이유","confidence":0.0}]}
"""


def _eligible(row: EstimateRow) -> bool:
    return (
        row.status in {RowStatus.NEEDS_EVIDENCE, RowStatus.NEEDS_USER_INPUT}
        and bool(set(row.reason_codes) & _ELIGIBLE_REASON_CODES)
    )


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        compact = " ".join(str(value).split())
        if not compact or compact in seen:
            continue
        seen.add(compact)
        result.append(compact)
    return result


def _actor_key(row: EstimateRow) -> str:
    """Return a concrete parent body instead of a generic state actor."""
    generic = {
        "국가",
        "정부",
        "대통령",
        "국무총리",
        "위원장",
        "장관",
        "기관장",
    }
    actors = [
        value.strip()
        for value in re.split(r"[,·ㆍ/]", row.event.actor)
        if value.strip()
    ]
    concrete = [
        value
        for value in actors
        if value not in generic and len(value) >= 4
    ]
    return concrete[0] if concrete else row.event.bearer


def _same_parent(row: EstimateRow, parent_key: str) -> bool:
    if parent_key in {"state", "public_institution", "local_government", ""}:
        return row.event.bearer == parent_key
    return parent_key in row.event.actor


def build_shadow_groups(result: EstimateResult) -> list[ShadowGroup]:
    """Group related unresolved events to avoid one embedding call per row."""
    eligible_rows = [row for row in result.rows if _eligible(row)]
    grouped: dict[str, list[EstimateRow]] = defaultdict(list)
    group_base: dict[str, str] = {}
    for row in eligible_rows:
        for group_name, (event_types, _) in _GROUPS.items():
            if row.event.event_type in event_types:
                group_key = group_name
                if group_name == "governance_operation":
                    group_key = f"{group_name}:{_actor_key(row)}"
                grouped[group_key].append(row)
                group_base[group_key] = group_name
                break

    groups: list[ShadowGroup] = []
    for group_key, rows in grouped.items():
        group_name = group_base[group_key]
        event_types, scopes = _GROUPS[group_name]
        parent_key = (
            _actor_key(rows[0])
            if group_name == "governance_operation"
            else ""
        )
        context_rows = [
            row
            for row in result.rows
            if row.event.event_type in event_types
            and (
                group_name != "governance_operation"
                or _same_parent(row, parent_key)
            )
        ]
        targets = _unique(
            value
            for row in rows
            for value in (
                row.event.object,
                row.event.action,
            )
        )
        # Put every related object's name before longer quotes so later
        # package members are not lost when the query is capped.
        context = _unique(
            [
                *(row.event.object for row in context_rows),
                *(
                    row.event.quotes[0][:160]
                    for row in context_rows
                    if row.event.quotes
                ),
            ]
        )
        query = " ".join(
            [
                f"법안: {result.bill_name}",
                f"미확정 비용대상: {'; '.join(targets[:6])}",
                f"같은 상위기관의 비용묶음: {'; '.join(context[:16])}",
                "찾을 근거: 개별 회의비뿐 아니라 유사 기능 조직의 전체 "
                "예산·집행액·운영비·기관 기본경비",
            ]
        )[:1_200]
        groups.append(
            ShadowGroup(
                name=group_key,
                scopes=set(scopes),
                rows=tuple(rows),
                context_rows=tuple(context_rows),
                query=query,
            )
        )
    return groups


def _target_is_finite(row: EstimateRow) -> bool:
    return bool(
        _FINITE_LIFECYCLE_PATTERN.search(
            " ".join([row.event.recurrence_text, *row.event.quotes])
        )
    )


def _has_transferable_amount_for_event(row: EstimateRow, hit: object) -> bool:
    evidence = [
        value
        for value in hit.atom.amount_evidence
        if value.get("transferable")
    ]
    if not evidence:
        return False
    if row.event.event_type == "organization_change":
        target_text = f"{row.event.object} {row.event.action}"
        if re.search(r"사무처|사무국|지원단", target_text):
            return any(
                set(value.get("scopes") or ())
                & {"support_office", "organization_operation"}
                for value in evidence
            )
        return any(
            set(value.get("scopes") or ())
            & {"support_office", "organization_operation"}
            for value in evidence
        )
    if row.event.event_type == "committee_operation":
        return any(
            "committee_operation" in set(value.get("scopes") or ())
            and value.get("primary_scope") != "support_office"
            for value in evidence
        )
    return any(
        row.event.event_type in set(value.get("scopes") or ())
        for value in evidence
    )


def _compatible_hits(row: EstimateRow, hits: list) -> list:
    """Apply factual scope/lifecycle gates before the LLM sees candidates."""
    result = []
    target_finite = _target_is_finite(row)
    for hit in hits:
        scopes = set(hit.atom.scopes)
        if row.event.event_type == "organization_change":
            target_text = f"{row.event.object} {row.event.action}"
            if re.search(r"사무처|사무국|지원단", target_text):
                if not scopes & {"support_office", "organization_operation"}:
                    continue
            elif not scopes & {"support_office", "organization_operation"}:
                continue
        elif row.event.event_type == "committee_operation":
            if "committee_operation" not in scopes:
                continue
        elif row.event.event_type not in scopes:
            continue
        source_finite = bool(_FINITE_LIFECYCLE_PATTERN.search(hit.atom.source_text))
        if not target_finite and source_finite:
            continue
        if not _has_transferable_amount_for_event(row, hit):
            continue
        result.append(hit)
    return result


def _diverse_hits(hits: list, *, limit: int = 12, per_bill: int = 2) -> list:
    counts: dict[str, int] = defaultdict(int)
    result = []
    for hit in hits:
        if counts[hit.atom.bill_no] >= per_bill:
            continue
        counts[hit.atom.bill_no] += 1
        result.append(hit)
        if len(result) >= limit:
            break
    return result


def _package_rows(group: ShadowGroup) -> list[EstimateRow]:
    """Find additive sibling events owned by the same parent cost centre."""
    unresolved_ids = {row.event.id for row in group.rows}
    return [
        row
        for row in group.context_rows
        if row.event.event_type == "committee_operation"
        and (
            row.event.id in unresolved_ids
            or row.status == RowStatus.COMPUTED_REVIEW
        )
        and "CONFLICTING_PRECEDENT_CHANNELS" not in row.reason_codes
    ]


def _select_for_group(
    group: ShadowGroup,
    hits: list,
    *,
    refresh: bool,
) -> tuple[
    dict[str, dict[str, object]],
    list[dict[str, object]],
    bool,
]:
    candidate_by_event = {
        row.event.id: _diverse_hits(_compatible_hits(row, hits))
        for row in group.rows
    }
    package_rows = _package_rows(group)
    package_candidates: list = []
    if len(package_rows) >= 2:
        allowed_sets = [
            {
                hit.atom.atom_id
                for hit in _compatible_hits(row, hits)
            }
            for row in package_rows
        ]
        common_ids = set.intersection(*allowed_sets) if allowed_sets else set()
        package_candidates = _diverse_hits(
            [hit for hit in hits if hit.atom.atom_id in common_ids]
        )
    atom_by_id = {
        hit.atom.atom_id: hit
        for values in [*candidate_by_event.values(), package_candidates]
        for hit in values
    }
    payload = {
        "selection_version": SHADOW_SELECTION_VERSION,
        "model": GEMINI_MODEL,
        "group": group.name,
        "group_context": [
            {
                "event_id": row.event.id,
                "event_type": row.event.event_type,
                "object": row.event.object,
                "actor": row.event.actor,
                "bearer": row.event.bearer,
                "quotes": row.event.quotes,
            }
            for row in group.context_rows
        ],
        "target_packages": (
            [
                {
                    "package_id": "P001",
                    "covered_event_ids": [
                        row.event.id
                        for row in package_rows
                    ],
                    "description": (
                        "같은 상위기관이 부담하는 관련 위원회·분과의 "
                        "전체 운영비 묶음"
                    ),
                    "candidate_atom_ids": [
                        hit.atom.atom_id
                        for hit in package_candidates
                    ],
                }
            ]
            if len(package_rows) >= 2
            else []
        ),
        "events": [
            {
                "event_id": row.event.id,
                "event_type": row.event.event_type,
                "object": row.event.object,
                "action": row.event.action,
                "actor": row.event.actor,
                "bearer": row.event.bearer,
                "quotes": row.event.quotes,
                "candidate_atom_ids": [
                    hit.atom.atom_id
                    for hit in candidate_by_event[row.event.id]
                ],
            }
            for row in group.rows
        ],
        "candidates": [
            {
                "atom_id": hit.atom.atom_id,
                "bill_no": hit.atom.bill_no,
                "bill_name": hit.atom.bill_name,
                "scopes": hit.atom.scopes,
                "entities": hit.atom.entities,
                "years": hit.atom.years,
                "units": hit.atom.units,
                "semantic_similarity": hit.semantic_similarity,
                "source_text": hit.atom.source_text[:900],
            }
            for hit in atom_by_id.values()
        ],
    }
    result, cache_hit = get_or_create_json(
        "narrative_evidence_selection",
        payload,
        lambda: gemini_json(
            f"{_SELECTION_PROMPT}\n입력:\n{payload}",
            temperature=0.0,
        ),
        refresh=refresh,
    )
    raw_assignments = (
        result.get("assignments")
        if isinstance(result, dict)
        else []
    )
    assignments: dict[str, dict[str, object]] = {}
    row_ids = {row.event.id for row in group.rows}
    for assignment in raw_assignments or []:
        if not isinstance(assignment, dict):
            continue
        event_id = str(assignment.get("event_id") or "")
        atom_id = str(assignment.get("atom_id") or "")
        allowed_ids = {
            hit.atom.atom_id
            for hit in candidate_by_event.get(event_id, [])
        }
        if event_id not in row_ids or (atom_id and atom_id not in allowed_ids):
            continue
        try:
            confidence = max(
                0.0,
                min(1.0, float(assignment.get("confidence") or 0)),
            )
        except (TypeError, ValueError):
            confidence = 0.0
        assignments[event_id] = {
            "atom_id": atom_id,
            "reason": str(assignment.get("reason") or ""),
            "confidence": confidence,
        }
    raw_packages = (
        result.get("packages")
        if isinstance(result, dict)
        else []
    )
    packages: list[dict[str, object]] = []
    package_event_ids = {row.event.id for row in package_rows}
    package_candidate_ids = {
        hit.atom.atom_id
        for hit in package_candidates
    }
    for package in raw_packages or []:
        if not isinstance(package, dict):
            continue
        atom_id = str(package.get("atom_id") or "")
        covered = [
            str(value)
            for value in package.get("covered_event_ids") or []
            if str(value) in package_event_ids
        ]
        if (
            not atom_id
            or atom_id not in package_candidate_ids
            or len(set(covered)) < 2
        ):
            continue
        try:
            confidence = max(
                0.0,
                min(1.0, float(package.get("confidence") or 0)),
            )
        except (TypeError, ValueError):
            confidence = 0.0
        packages.append(
            {
                "package_id": str(package.get("package_id") or "P001"),
                "atom_id": atom_id,
                "covered_event_ids": list(dict.fromkeys(covered)),
                "reason": str(package.get("reason") or ""),
                "confidence": confidence,
            }
        )
    covered_by_package = {
        event_id
        for package in packages
        for event_id in package["covered_event_ids"]
    }
    assignments = {
        event_id: assignment
        for event_id, assignment in assignments.items()
        if event_id not in covered_by_package
    }
    return assignments, packages, cache_hit


def attach_narrative_evidence_shadow(
    result: EstimateResult,
    *,
    refresh: bool = False,
    k: int = 15,
    max_groups: int | None = None,
) -> dict[str, object]:
    """Attach narrative candidates without changing the estimate.

    Exact target-bill rows and post-target evidence are hard-excluded before
    retrieval.  The return value is an execution summary suitable for logs.
    """
    cutoff_date, _ = target_metadata(result.bill_no)
    groups = build_shadow_groups(result)
    if max_groups is not None:
        groups = groups[: max(0, max_groups)]

    searched_groups: list[dict[str, object]] = []
    for group in groups:
        hits = search_evidence_atoms(
            group.query,
            allowed_scopes=group.scopes,
            exclude_bill_nos={result.bill_no} if result.bill_no else set(),
            cutoff_date=cutoff_date,
            k=k,
            refresh=refresh,
        )
        assignments, packages, selection_cache_hit = _select_for_group(
            group,
            hits,
            refresh=refresh,
        )
        package_by_event = {
            event_id: package
            for package in packages
            for event_id in package["covered_event_ids"]
        }
        attachment_rows = list(group.rows)
        attached_ids = {row.event.id for row in attachment_rows}
        for row in group.context_rows:
            if row.event.id in package_by_event and row.event.id not in attached_ids:
                attachment_rows.append(row)
                attached_ids.add(row.event.id)
        for row in attachment_rows:
            compatible = _diverse_hits(_compatible_hits(row, hits))
            assignment = assignments.get(row.event.id, {})
            package = package_by_event.get(row.event.id, {})
            selected_id = str(
                package.get("atom_id")
                or assignment.get("atom_id")
                or ""
            )
            ordered = sorted(
                compatible,
                key=lambda hit: (
                    hit.atom.atom_id != selected_id if selected_id else True,
                    -hit.semantic_similarity,
                    hit.atom.bill_no,
                ),
            )
            row.narrative_evidence = [
                {
                    **hit.to_dict(),
                    "shadow_only": True,
                    "group": group.name,
                    "selected": hit.atom.atom_id == selected_id,
                    "selection_scope": (
                        "package"
                        if package and hit.atom.atom_id == selected_id
                        else "individual"
                    ),
                    "covered_event_ids": (
                        package.get("covered_event_ids", [])
                        if package and hit.atom.atom_id == selected_id
                        else [row.event.id]
                    ),
                    "selection_method": SHADOW_SELECTION_VERSION,
                    "selection_reason": (
                        (package or assignment).get("reason")
                        if hit.atom.atom_id == selected_id
                        else ""
                    ),
                    "selection_confidence": (
                        (package or assignment).get("confidence", 0.0)
                        if hit.atom.atom_id == selected_id
                        else 0.0
                    ),
                }
                for hit in ordered[:3]
            ]
        searched_groups.append(
            {
                "group": group.name,
                "event_ids": [row.event.id for row in group.rows],
                "hit_count": len(hits),
                "top_bill_no": hits[0].atom.bill_no if hits else None,
                "top_similarity": (
                    hits[0].semantic_similarity if hits else None
                ),
                "selection_cache_hit": selection_cache_hit,
                "selected": {
                    event_id: assignment
                    for event_id, assignment in assignments.items()
                    if assignment.get("atom_id")
                },
                "packages": packages,
            }
        )

    if groups:
        result.warnings.append(
            f"보조 근거 검색 {SHADOW_FALLBACK_VERSION}/"
            f"{EVIDENCE_INDEX_VERSION}: 미확정 행에 후보만 첨부했으며 "
            "상태·산식·변수·금액은 변경하지 않았습니다."
        )
    return {
        "version": SHADOW_FALLBACK_VERSION,
        "shadow_only": True,
        "amounts_changed": False,
        "groups": searched_groups,
    }
