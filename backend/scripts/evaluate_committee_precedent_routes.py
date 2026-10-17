"""Offline pilot for committee precedent routing.

This script does not modify the runtime estimator and never uses a target
cost-estimate answer as a retrieval query.  Target queries are extracted only
from the uploaded bill text.  Official source anchors are used after ranking
solely to audit whether the local DB contained independent evidence.

The pilot separates three questions that were previously conflated:

1. Is an actionable official precedent present before the target date?
2. Does a retrieval method put that precedent in its candidate set?
3. Should the system retrieve it or abstain because only partial/external
   evidence exists?
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import fitz


ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "backend" / "generated"
DEFAULT_CASES = GENERATED / "committee_precedent_pilot" / "pilot_cases.json"

_COMMITTEE = re.compile(r"위원회|심의회|협의회")
_ACTION_TERMS = re.compile(r"가정|산출|추계|적용|곱하|나누|참고|준용")
_NUMBER_WITH_UNIT = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s*(?:명|회|원|만원|백만원|억원|천원|%|퍼센트|개)"
)

_STRUCTURE_FLAGS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("standing_member", re.compile(r"상임위원")),
    ("secretariat", re.compile(r"사무처|사무국|사무기구|지원조직|전담조직")),
    ("subcommittee", re.compile(r"전문위원회|분과위원회|소위원회|실무위원회")),
    ("staff", re.compile(r"소속직원|필요한직원|상근직원|직원정원")),
    ("equal_groups", re.compile(r"동수로|같은수로")),
    (
        "non_public_majority",
        re.compile(r"(?:민간위원|공무원이아닌위원).{0,25}(?:과반|절반이상)"),
    ),
)


@dataclass(frozen=True)
class CandidateText:
    bill_no: str
    bill_name: str
    propose_date: str
    available_date: str
    chunks: tuple[str, ...]

    @property
    def full_text(self) -> str:
        return " ".join(self.chunks)


def _compact(value: str) -> str:
    return re.sub(r"[^가-힣A-Za-z0-9]", "", value or "")


def _normalise_law_name(value: str) -> str:
    compact = re.sub(r"[\sㆍ·・･]", "", value or "")
    return re.sub(r"(?:일부|전부)?개정법률안$|법률안$", "", compact)


def _char_ngrams(value: str, n: int = 3) -> set[str]:
    compact = _compact(value)
    if len(compact) < n:
        return {compact} if compact else set()
    return {compact[index : index + n] for index in range(len(compact) - n + 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _tokens(value: str) -> set[str]:
    compacted = re.sub(r"[^가-힣A-Za-z0-9]+", " ", value or "")
    return {token for token in compacted.split() if len(token) >= 2}


def _load_metadata() -> dict[str, dict[str, str]]:
    metadata: dict[str, dict[str, str]] = {}
    for path in glob.glob(str(GENERATED / "**/cost_estimate_structures.jsonl"), recursive=True):
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            bill_no = str(row.get("bill_no") or "")
            if not bill_no:
                continue
            candidate = {
                "bill_name": str(row.get("bill_name") or ""),
                "propose_date": str(row.get("propose_date") or ""),
            }
            current = metadata.get(bill_no)
            if current is None or (
                not current.get("propose_date") and candidate["propose_date"]
            ):
                metadata[bill_no] = candidate

    # Some raw cost-estimate documents have not yet been promoted into the
    # structured TAG tables.  They remain valid retrieval evidence, and the
    # bill catalogue carries the date needed for a leakage-safe cutoff.
    for path in glob.glob(str(GENERATED / "**/bills.jsonl"), recursive=True):
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            bill_no = str(row.get("billNo") or row.get("bill_no") or "")
            if not bill_no:
                continue
            candidate = {
                "bill_name": str(row.get("billName") or row.get("bill_name") or ""),
                "propose_date": str(row.get("proposeDate") or row.get("propose_date") or ""),
            }
            current = metadata.get(bill_no)
            if current is None:
                metadata[bill_no] = candidate
            else:
                if not current.get("bill_name") and candidate["bill_name"]:
                    current["bill_name"] = candidate["bill_name"]
                if not current.get("propose_date") and candidate["propose_date"]:
                    current["propose_date"] = candidate["propose_date"]
    return metadata


def _load_candidate_texts(metadata: dict[str, dict[str, str]]) -> dict[str, CandidateText]:
    chunks_by_bill: dict[str, list[str]] = defaultdict(list)
    reply_dates: dict[str, str] = {}
    seen: set[tuple[str, str]] = set()
    for path in glob.glob(str(GENERATED / "**/chunks.jsonl"), recursive=True):
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            document_type = str(row.get("documentType") or row.get("document_type") or "")
            if document_type != "cost_estimate":
                continue
            text = str(row.get("text") or row.get("content") or "")
            if not _COMMITTEE.search(text):
                continue
            bill_no = str(row.get("billNo") or row.get("bill_no") or "")
            signature = (bill_no, _compact(text))
            if not bill_no or not signature[1] or signature in seen:
                continue
            seen.add(signature)
            chunks_by_bill[bill_no].append(re.sub(r"\s+", " ", text).strip())
            reply_date = re.search(
                r"회답일\s*(\d{4})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})",
                text,
            )
            if reply_date:
                reply_dates[bill_no] = (
                    f"{reply_date.group(1)}-{reply_date.group(2).zfill(2)}-"
                    f"{reply_date.group(3).zfill(2)}"
                )

    candidates: dict[str, CandidateText] = {}
    for bill_no, chunks in chunks_by_bill.items():
        meta = metadata.get(bill_no, {})
        candidates[bill_no] = CandidateText(
            bill_no=bill_no,
            bill_name=str(meta.get("bill_name") or ""),
            propose_date=str(meta.get("propose_date") or ""),
            available_date=reply_dates.get(bill_no, ""),
            chunks=tuple(chunks),
        )
    return candidates


def _pdf_text(path: Path) -> str:
    document = fitz.open(path)
    try:
        return "\n".join(page.get_text() for page in document)
    finally:
        document.close()


def _target_passages(case: dict[str, Any]) -> list[str]:
    # New blind cases can persist the source-only article passages directly.
    # This keeps the evaluation reproducible without storing a duplicate PDF
    # and, importantly, cannot introduce the target cost-estimate answer.
    persisted = [
        re.sub(r"\s+", " ", str(value)).strip()
        for value in case.get("target_passages") or []
        if str(value).strip()
    ]
    if persisted:
        return persisted
    text = _pdf_text(ROOT / str(case["source_pdf"]))
    blocks = re.split(
        r"(?=제\s*\d+조(?:의\d+)?(?:\s*\([^\n]{0,100}\))?)",
        text,
    )
    terms = [_compact(str(term)) for term in case.get("target_terms") or []]
    selected = []
    for block in blocks:
        compact = _compact(block)
        if len(compact) < 40 or not _COMMITTEE.search(block):
            continue
        if terms and not any(term in compact for term in terms):
            continue
        selected.append(re.sub(r"\s+", " ", block).strip()[:4000])
    if selected:
        return selected

    # PDF extraction occasionally breaks an entity across article boundaries.
    # A bounded local window is preferable to silently querying with the full
    # bill, which would reward unrelated boilerplate elsewhere in the document.
    compact_text = _compact(text)
    fallback = []
    for term in terms:
        index = compact_text.find(term)
        if index >= 0:
            fallback.append(compact_text[max(0, index - 500) : index + len(term) + 1500])
    return fallback or [re.sub(r"\s+", " ", text).strip()[:4000]]


def _idf_by_token(candidates: Iterable[CandidateText]) -> dict[str, float]:
    rows = list(candidates)
    frequency: Counter[str] = Counter()
    for candidate in rows:
        frequency.update(_tokens(candidate.full_text))
    total = max(1, len(rows))
    return {
        token: math.log((total + 1) / (count + 1)) + 1.0
        for token, count in frequency.items()
    }


def _lexical_score(query: str, text: str, idf: dict[str, float]) -> float:
    query_tokens = _tokens(query)
    candidate_tokens = _tokens(text)
    if not query_tokens or not candidate_tokens:
        return 0.0
    numerator = sum(idf.get(token, 1.0) for token in query_tokens & candidate_tokens)
    denominator = sum(idf.get(token, 1.0) for token in query_tokens)
    return numerator / denominator if denominator else 0.0


def _completeness(text: str) -> float:
    number_count = len(_NUMBER_WITH_UNIT.findall(text))
    has_method = bool(_ACTION_TERMS.search(text))
    if number_count >= 3 and has_method:
        return 1.0
    if number_count >= 1 and has_method:
        return 0.65
    if number_count >= 1 or has_method:
        return 0.35
    return 0.0


def _structure_signature(text: str) -> dict[str, Any]:
    """Extract source-law facts that decide whether a whole precedent transfers.

    This is intentionally narrower than semantic similarity.  A prior bill can
    be an excellent *component* source while still being unsafe to execute as
    one coherent estimate when the target changed its legal member cap,
    secretariat, subordinate bodies, or composition rule.
    """
    compact = _compact(text)
    member_limits = sorted(
        {
            int(value)
            for value in re.findall(r"(\d+)(?:명|인)(?:이내|내외|이상)", compact)
        }
    )
    standing_counts = sorted(
        {
            int(value)
            for value in re.findall(
                r"(?:상임위원(?:은|을|이|의|수는)?|그중)(\d+)(?:명|인)(?:이내)?(?:는)?상임",
                compact,
            )
        }
    )
    chair_counts = sorted(
        {
            int(value)
            for value in re.findall(r"위원장(?:을|를)?(\d+)(?:명|인)", compact)
        }
    )
    return {
        "member_limits": member_limits,
        "standing_counts": standing_counts,
        "chair_counts": chair_counts,
        "flags": sorted(
            name for name, pattern in _STRUCTURE_FLAGS if pattern.search(compact)
        ),
    }


def _structure_compatibility(
    target_text: str,
    candidate_text: str,
) -> tuple[str, list[str]]:
    """Classify full-document transferability without judging numeric values.

    ``compatible`` may authorize the later formula/operand completeness gate.
    ``changed`` downgrades the document to component evidence.  ``unknown`` is
    conservative metadata: it cannot independently create an executable link.
    """
    target = _structure_signature(target_text)
    candidate = _structure_signature(candidate_text)
    reasons: list[str] = []
    target_limits = set(target["member_limits"])
    candidate_limits = set(candidate["member_limits"])
    if target_limits and candidate_limits and not target_limits & candidate_limits:
        reasons.append("member_limit_changed")
    target_chairs = set(target["chair_counts"])
    candidate_chairs = set(candidate["chair_counts"])
    if target_chairs and candidate_chairs and not target_chairs & candidate_chairs:
        reasons.append("chair_count_changed")
    target_standing = set(target["standing_counts"])
    candidate_standing = set(candidate["standing_counts"])
    if target_standing and candidate_standing and not target_standing & candidate_standing:
        reasons.append("standing_member_count_changed")

    target_flags = set(target["flags"])
    candidate_flags = set(candidate["flags"])
    for flag in {
        "standing_member",
        "secretariat",
        "subcommittee",
        "staff",
        "equal_groups",
        "non_public_majority",
    }:
        if (flag in target_flags) != (flag in candidate_flags):
            reasons.append(f"{flag}_changed")
    if reasons:
        return "changed", sorted(reasons)
    has_comparable_fact = bool(
        (target_limits and candidate_limits)
        or (target_flags and candidate_flags)
        or (target_chairs and candidate_chairs)
    )
    return ("compatible" if has_comparable_fact else "unknown"), []


def _best_passage_scores(
    target_passages: list[str],
    candidate: CandidateText,
    idf: dict[str, float],
) -> tuple[float, float, str]:
    best_template = 0.0
    best_lexical = 0.0
    best_text = ""
    target_grams = [_char_ngrams(passage) for passage in target_passages]
    for chunk in candidate.chunks:
        chunk_grams = _char_ngrams(chunk)
        template = max((_jaccard(grams, chunk_grams) for grams in target_grams), default=0.0)
        lexical = max(
            (_lexical_score(passage, chunk, idf) for passage in target_passages),
            default=0.0,
        )
        if (template, lexical) > (best_template, best_lexical):
            best_template = template
            best_lexical = lexical
            best_text = chunk
    return best_template, best_lexical, best_text


def _relation_candidate(
    case: dict[str, Any],
    passages: list[str],
    candidate: CandidateText,
    idf: dict[str, float],
) -> dict[str, Any]:
    template, lexical, best_text = _best_passage_scores(passages, candidate, idf)
    target_law = _normalise_law_name(str(case["bill_name"]))
    candidate_law = _normalise_law_name(candidate.bill_name)
    same_law = bool(target_law and target_law == candidate_law)
    title_similarity = _jaccard(_char_ngrams(target_law), _char_ngrams(candidate_law))
    # Formula operands are often split across adjacent PDF chunks.  Measure
    # document-level availability here, while keeping the relationship score
    # tied to the best target-event passage.  Completeness is only a soft
    # reranking/acceptance signal and cannot create a relationship by itself.
    completeness = _completeness(candidate.full_text)
    target_structure_text = " ".join(passages)
    structure_status, structure_reasons = _structure_compatibility(
        target_structure_text,
        candidate.full_text,
    )

    # A relationship signal creates the candidate set.  Completeness only
    # reranks candidates after that; it must never rescue an unrelated body.
    if same_law:
        relation_score = 0.62 + 0.28 * template + 0.10 * completeness
        route = "same_law_history"
    else:
        relation_score = 0.45 * title_similarity + 0.45 * template + 0.10 * completeness
        route = "template_lineage"
    return {
        "bill_no": candidate.bill_no,
        "bill_name": candidate.bill_name,
        "propose_date": candidate.propose_date,
        "available_date": candidate.available_date,
        "route": route,
        "same_law": same_law,
        "title_similarity": round(title_similarity, 4),
        "template_similarity": round(template, 4),
        "lexical_score": round(lexical, 4),
        "completeness": round(completeness, 2),
        "structure_status": structure_status,
        "structure_reasons": structure_reasons,
        "target_structure": _structure_signature(target_structure_text),
        "candidate_structure": _structure_signature(candidate.full_text),
        "relation_score": round(relation_score, 4),
        "snippet": best_text[:280],
    }


def _select_relation_candidate(ranking: list[dict[str, Any]]) -> tuple[str, str | None]:
    if not ranking:
        return "abstain", None
    first = ranking[0]
    # Multiple prior estimates from the same law and the same target-like cost
    # event corroborate one legislative lineage; they are not independent
    # alternatives.  Counting them as runner-up competitors caused a correct
    # same-bill history to abstain merely because the bill had been reintroduced
    # several times.  Weakly matching amendments to the same broad law remain
    # competitors and cannot create this cluster.
    corroborating_history = bool(first["same_law"])
    competitors = [
        row
        for row in ranking[1:]
        if not (
            corroborating_history
            and bool(row["same_law"])
            and float(row["template_similarity"]) >= 0.18
        )
    ]
    second_score = float(competitors[0]["relation_score"]) if competitors else 0.0
    margin = float(first["relation_score"]) - second_score
    complete_enough = float(first["completeness"]) >= 0.65
    structure_allows_full_reuse = first.get("structure_status") != "changed"
    # Same-law history is accepted only when the actual cost event also
    # resembles the target.  This rejects unrelated amendments to the same
    # broad law (observed template similarity 0.01~0.05 in the pilot).
    strong_history = bool(first["same_law"]) and float(first["template_similarity"]) >= 0.18
    # A renamed/reintroduced bill can have a different formal law title.  In
    # that route require near-copy article structure, a related title, and a
    # large lead over the runner-up.  These are relationship signals rather
    # than target-specific institution names or amounts.
    strong_lineage = (
        float(first["title_similarity"]) >= 0.25
        and float(first["template_similarity"]) >= 0.65
        and margin >= 0.15
    )
    if (
        complete_enough
        and structure_allows_full_reuse
        and margin >= 0.04
        and (strong_history or strong_lineage)
    ):
        return "retrieve", str(first["bill_no"])
    return "abstain", None


def _source_anchor_hits(
    case: dict[str, Any],
    candidates: dict[str, CandidateText],
) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    cutoff = str(case.get("cutoff_date") or case["propose_date"])
    target = str(case["bill_no"])
    for anchor in case.get("official_source_anchors") or []:
        compact_anchor = _compact(str(anchor))
        matched = [
            bill_no
            for bill_no, candidate in candidates.items()
            if _eligible_at_cutoff(candidate, target_bill_no=target, cutoff_date=cutoff)
            and compact_anchor in _compact(candidate.full_text)
        ]
        hits[str(anchor)] = sorted(matched)
    return hits


def _eligible_at_cutoff(
    candidate: CandidateText,
    *,
    target_bill_no: str,
    cutoff_date: str,
) -> bool:
    """Return whether a cost estimate was actually available to the target.

    Proposal date is insufficient: two bills can be proposed days apart while
    their official estimates are produced together later.  A missing reply
    date is treated conservatively as unavailable in historical evaluation.
    """
    return bool(
        candidate.bill_no != target_bill_no
        and candidate.available_date
        # A document answered on the same day as the target is not a safely
        # ordered precedent.  Without timestamps we cannot know which analyst
        # had access to which document first, so historical evaluation keeps
        # only strictly earlier evidence.
        and candidate.available_date < cutoff_date
    )


def evaluate(cases_path: Path) -> dict[str, Any]:
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    metadata = _load_metadata()
    candidates = _load_candidate_texts(metadata)
    idf = _idf_by_token(candidates.values())
    results = []

    for case in cases:
        target = str(case["bill_no"])
        # Historical experiments keep proposal-date cutoffs.  A separately
        # frozen blind run may instead use the official reply date, which is
        # the latest evidence that could have existed when that estimate was
        # produced.  The target document itself is always excluded below.
        cutoff = str(case.get("cutoff_date") or case["propose_date"])
        passages = _target_passages(case)
        eligible = [
            candidate
            for candidate in candidates.values()
            if _eligible_at_cutoff(
                candidate,
                target_bill_no=target,
                cutoff_date=cutoff,
            )
        ]
        ranking = sorted(
            (
                _relation_candidate(case, passages, candidate, idf)
                for candidate in eligible
            ),
            key=lambda row: (float(row["relation_score"]), row["available_date"], row["bill_no"]),
            reverse=True,
        )
        lexical_ranking = sorted(
            ranking,
            key=lambda row: (float(row["lexical_score"]), row["available_date"], row["bill_no"]),
            reverse=True,
        )
        template_ranking = sorted(
            ranking,
            key=lambda row: (float(row["template_similarity"]), row["available_date"], row["bill_no"]),
            reverse=True,
        )
        decision, selected = _select_relation_candidate(ranking)
        expected = str(case["expected_decision"])
        gold = {str(value) for value in case.get("gold_bill_nos") or []}
        correct = decision == expected and (decision == "abstain" or selected in gold)
        candidate_recall_at_10 = (
            any(str(row["bill_no"]) in gold for row in ranking[:10]) if gold else None
        )
        results.append(
            {
                "bill_no": target,
                "db_status": case["db_status"],
                "expected_decision": expected,
                "decision": decision,
                "selected_bill_no": selected,
                "correct": correct,
                "candidate_recall_at_10": candidate_recall_at_10,
                "official_anchor_hits": _source_anchor_hits(case, candidates),
                "relation_top5": ranking[:5],
                "lexical_top5": lexical_ranking[:5],
                "template_top5": template_ranking[:5],
                "label_note": case["label_note"],
            }
        )

    actionable = [row for row in results if row["expected_decision"] == "retrieve"]
    abstentions = [row for row in results if row["expected_decision"] == "abstain"]
    return {
        "case_count": len(results),
        "correct_count": sum(bool(row["correct"]) for row in results),
        "actionable_count": len(actionable),
        "actionable_correct": sum(bool(row["correct"]) for row in actionable),
        "safe_abstention_count": len(abstentions),
        "safe_abstention_correct": sum(bool(row["correct"]) for row in abstentions),
        "candidate_recall_at_10": (
            sum(bool(row["candidate_recall_at_10"]) for row in actionable) / len(actionable)
            if actionable
            else None
        ),
        "results": results,
    }


def _print_summary(payload: dict[str, Any]) -> None:
    recall = payload["candidate_recall_at_10"]
    recall_text = f"{recall:.2f}" if recall is not None else "n/a"
    print(
        "pilot "
        f"correct={payload['correct_count']}/{payload['case_count']} "
        f"actionable={payload['actionable_correct']}/{payload['actionable_count']} "
        f"safe_abstention={payload['safe_abstention_correct']}/{payload['safe_abstention_count']} "
        f"candidate_recall@10={recall_text}"
    )
    for row in payload["results"]:
        relation = row["relation_top5"][0] if row["relation_top5"] else {}
        lexical = row["lexical_top5"][0] if row["lexical_top5"] else {}
        print(
            f"{row['bill_no']} expected={row['expected_decision']} "
            f"actual={row['decision']} selected={row['selected_bill_no'] or '-'} "
            f"correct={row['correct']} "
            f"relation_top={relation.get('bill_no', '-')}:{relation.get('relation_score', '-')} "
            f"lexical_top={lexical.get('bill_no', '-')}:{lexical.get('lexical_score', '-')}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = evaluate(args.cases)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_summary(payload)


if __name__ == "__main__":
    main()
