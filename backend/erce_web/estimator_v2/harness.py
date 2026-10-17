"""Evaluation-only evidence audit for the estimator.

This module is deliberately separated from the runtime estimator.  It may read
the target bill's official cost-estimate TAG rows to diagnose an error, but it
never feeds those values or source names back into estimation.  The target
answer is an oracle for evaluation only.

The audit answers a narrower, actionable question:

    Did an independent, pre-cutoff document in our DB contain the official
    source institution/evidence, and did the estimator use it?

That distinction keeps genuine data gaps separate from retrieval/indexing
failures and prevents a ``needs_user_input`` result from hiding a missed DB
precedent.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from ..estimator import tag_db
from .organization import _cost_estimate_contexts
from .retrieval import _amount_rows, _normalise_law_name, target_metadata
from .types import EstimateResult


HARNESS_VERSION = "missed-evidence-audit-v1"

_SOURCE_SUFFIX = (
    r"위원회|심의회|협의회|사무국|사무처|지원단|공단|공사|"
    r"연구원|진흥원|법원|검찰청|행정기관"
)
_GENERIC_SOURCE_NAMES = {
    "위원회",
    "전문위원회",
    "소위원회",
    "운영위원회",
    "자문위원회",
    "심의위원회",
    "협의회",
    "사무국",
    "사무처",
    "지원단",
}
_BUDGET_TERMS = re.compile(
    r"예산|예산액|집행액|운영비|운영경비|기본경비|인건비|사업비|"
    r"수당|단가|재정소요|비용"
)
_HISTORY_TERMS = re.compile(r"최근\s*\d+\s*년|평균|연평균|예[·ㆍ]?결산|추이")
_AMOUNT_TERMS = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s*(?:백만원|억원|만원|천원|원)"
)


@dataclass(frozen=True)
class EvidenceHit:
    bill_no: str
    bill_name: str
    propose_date: str
    anchor: str
    strength: float
    has_budget_term: bool
    has_history_term: bool
    has_amount_term: bool
    snippet: str


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _source_anchors(value: str) -> list[str]:
    """Extract named precedent bodies, excluding generic body labels.

    The regex is intentionally non-greedy.  For
    ``최저임금위원회 전문위원회`` it extracts ``최저임금위원회`` and rejects
    the generic ``전문위원회`` rather than fabricating one long entity name.
    """
    compact = _compact(value)
    anchors: set[str] = set()
    pattern = re.compile(rf"([가-힣A-Za-z0-9·ㆍ]{{2,30}}?(?:{_SOURCE_SUFFIX}))")
    for match in pattern.finditer(compact):
        anchor = match.group(1)
        if anchor in _GENERIC_SOURCE_NAMES:
            continue
        if len(anchor) < 5:
            continue
        anchors.add(anchor)
    return sorted(anchors, key=lambda anchor: (-len(anchor), anchor))


def _bill_metadata() -> dict[str, dict[str, str]]:
    metadata: dict[str, dict[str, str]] = {}
    for meta in tag_db._load()["items"].values():
        bill_no = str(meta.get("bill_no") or "")
        if not bill_no:
            continue
        current = metadata.setdefault(
            bill_no,
            {
                "bill_name": str(meta.get("bill_name") or ""),
                "propose_date": str(meta.get("propose_date") or ""),
            },
        )
        # Prefer populated metadata if duplicate generated datasets differ.
        if not current["bill_name"] and meta.get("bill_name"):
            current["bill_name"] = str(meta["bill_name"])
        if not current["propose_date"] and meta.get("propose_date"):
            current["propose_date"] = str(meta["propose_date"])
    return metadata


def _snippet(text: str, anchor: str, radius: int = 450) -> str:
    index = text.find(anchor)
    if index < 0:
        # Contexts usually preserve Korean entity spelling.  This fallback is
        # only for whitespace inserted inside an extracted table.
        compact = _compact(text)
        compact_index = compact.find(_compact(anchor))
        if compact_index < 0:
            return text[: radius * 2].strip()
        # A precise reverse map is unnecessary for an audit excerpt.  Find the
        # first distinctive prefix in the original text instead.
        prefix = anchor[: max(3, len(anchor) // 2)]
        index = text.find(prefix)
        if index < 0:
            return text[: radius * 2].strip()
    start = max(0, index - radius)
    end = min(len(text), index + len(anchor) + radius)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def _hit_strength(snippet: str) -> tuple[float, bool, bool, bool]:
    has_budget = bool(_BUDGET_TERMS.search(snippet))
    has_history = bool(_HISTORY_TERMS.search(snippet))
    has_amount = bool(_AMOUNT_TERMS.search(snippet))
    # Named-source equality is the hard signal (0.55).  Budget scope,
    # historical basis and an explicit monetary amount make it actionable.
    strength = 0.55
    strength += 0.20 if has_budget else 0.0
    strength += 0.15 if has_history else 0.0
    strength += 0.10 if has_amount else 0.0
    return round(min(1.0, strength), 2), has_budget, has_history, has_amount


def _independent_hits(
    anchors: list[str],
    *,
    target_bill_no: str,
    target_bill_name: str,
    cutoff_date: str | None,
) -> list[EvidenceHit]:
    contexts = _cost_estimate_contexts()
    metadata = _bill_metadata()
    same_law = _normalise_law_name(target_bill_name)
    hits: list[EvidenceHit] = []
    seen: set[tuple[str, str]] = set()

    for bill_no, text in contexts.items():
        if bill_no == target_bill_no:
            continue
        meta = metadata.get(bill_no, {})
        propose_date = str(meta.get("propose_date") or "")
        bill_name = str(meta.get("bill_name") or "")
        if cutoff_date and (not propose_date or propose_date > cutoff_date):
            continue
        if same_law and _normalise_law_name(bill_name) == same_law:
            continue
        compact_text = _compact(text)
        for anchor in anchors:
            if _compact(anchor) not in compact_text:
                continue
            signature = (bill_no, anchor)
            if signature in seen:
                continue
            seen.add(signature)
            excerpt = _snippet(text, anchor)
            strength, has_budget, has_history, has_amount = _hit_strength(excerpt)
            hits.append(
                EvidenceHit(
                    bill_no=bill_no,
                    bill_name=bill_name,
                    propose_date=propose_date,
                    anchor=anchor,
                    strength=strength,
                    has_budget_term=has_budget,
                    has_history_term=has_history,
                    has_amount_term=has_amount,
                    snippet=excerpt,
                )
            )
    return sorted(
        hits,
        key=lambda hit: (-hit.strength, hit.propose_date, hit.bill_no, hit.anchor),
    )


def _selected_bill_nos(result: EstimateResult | dict[str, Any] | None) -> set[str]:
    if result is None:
        return set()
    payload = result.to_dict() if isinstance(result, EstimateResult) else result
    selected: set[str] = set()
    for row in payload.get("rows") or []:
        for candidate in row.get("selected_candidates") or []:
            bill_no = str(candidate.get("bill_no") or "")
            if bill_no:
                selected.add(bill_no)
        for evidence in row.get("variable_evidence") or []:
            bill_no = str(evidence.get("bill_no") or evidence.get("source_bill_no") or "")
            if bill_no:
                selected.add(bill_no)
    return selected


def _official_items(bill_no: str) -> list[dict[str, Any]]:
    """Read target answer rows for evaluation; never called by the estimator."""
    data = tag_db._load()
    formulas = tag_db._formula_by_item()
    amounts = _amount_rows()
    rows: list[dict[str, Any]] = []
    for item_id, meta in data["items"].items():
        if str(meta.get("bill_no") or "") != bill_no:
            continue
        variables = data["vars"].get(item_id, [])
        formula = formulas.get(item_id, "")
        # The target item name describes what is being estimated, not the
        # precedent source.  Reading it here would falsely turn the target body
        # itself into an oracle anchor.  Source names must come from the
        # official formula/variable basis only.
        source_fields = [
            formula,
            *[str(variable.get("name") or "") for variable in variables],
        ]
        anchors = sorted(
            {
                anchor
                for field in source_fields
                for anchor in _source_anchors(field)
            },
            key=lambda anchor: (-len(anchor), anchor),
        )
        rows.append(
            {
                "item_id": item_id,
                "item_name": str(meta.get("name") or ""),
                "family": str(meta.get("family") or ""),
                "formula": formula,
                "variables": variables,
                "year_amounts_thousand": [
                    int(amount.get("amount_thousand") or 0)
                    for amount in amounts.get(item_id, [])
                    if amount.get("year_offset") is not None
                ],
                "source_anchors": anchors,
            }
        )
    return sorted(rows, key=lambda row: (row["item_name"], row["item_id"]))


def audit_missed_evidence(
    bill_no: str,
    result: EstimateResult | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify independent DB evidence as selected, missed, absent or unknown."""
    cutoff_date, bill_name = target_metadata(bill_no)
    selected_bill_nos = _selected_bill_nos(result)
    item_audits: list[dict[str, Any]] = []

    for item in _official_items(bill_no):
        anchors = item["source_anchors"]
        hits = _independent_hits(
            anchors,
            target_bill_no=bill_no,
            target_bill_name=bill_name,
            cutoff_date=cutoff_date,
        )
        strong_hits = [hit for hit in hits if hit.strength >= 0.75]
        selected_hits = [
            hit for hit in strong_hits if hit.bill_no in selected_bill_nos
        ]
        if not anchors:
            status = "audit_inconclusive_no_source_anchor"
        elif selected_hits:
            status = "independent_evidence_selected"
        elif strong_hits:
            status = "independent_evidence_missed"
        else:
            status = "no_independent_source_evidence"
        item_audits.append(
            {
                **item,
                "status": status,
                "independent_hits": [asdict(hit) for hit in hits[:5]],
                "selected_hit_bill_nos": sorted(
                    {hit.bill_no for hit in selected_hits}
                ),
                "diagnosis": {
                    "independent_exact_answer_not_assumed": True,
                    "meaning": {
                        "independent_evidence_selected": (
                            "대상 정답을 제외한 과거 DB 근거를 현재 결과가 사용했습니다."
                        ),
                        "independent_evidence_missed": (
                            "대상 정답을 제외한 과거 DB에 강한 근거가 있었지만 현재 결과가 "
                            "사용하지 않았습니다. 데이터 부족이 아니라 검색·인덱싱·선정 결함입니다."
                        ),
                        "no_independent_source_evidence": (
                            "공식 출처기관 기준으로 독립적인 과거 DB 근거를 찾지 못했습니다."
                        ),
                        "audit_inconclusive_no_source_anchor": (
                            "공식 항목에 명시적인 출처기관이 없어 이 감사만으로 데이터 부족을 "
                            "확정할 수 없습니다."
                        ),
                    }[status],
                },
            }
        )

    counts: dict[str, int] = {}
    for item in item_audits:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return {
        "harness_version": HARNESS_VERSION,
        "bill_no": bill_no,
        "bill_name": bill_name,
        "cutoff_date": cutoff_date,
        "target_answer_used_only_as_evaluation_oracle": True,
        "target_excluded_from_candidate_search": True,
        "selected_bill_nos": sorted(selected_bill_nos),
        "target_leak": bill_no in selected_bill_nos,
        "summary": counts,
        "items": item_audits,
    }


def audit_has_missed_evidence(audit: dict[str, Any]) -> bool:
    return bool(
        (audit.get("summary") or {}).get("independent_evidence_missed")
    )
