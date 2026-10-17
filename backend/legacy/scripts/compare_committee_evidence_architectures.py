"""Compare committee evidence retrieval architectures on fixed manual labels.

This is an offline development harness.  It never imports into the runtime
estimator, and it never uses the target cost estimate as query material.
Target text comes only from the source bill PDF.  Manual labels are read only
after all rankings have been produced.

The experiment deliberately separates two jobs:

* exact precedent routing: a prior document may become executable evidence;
* component discovery: useful personnel/basic/program-cost evidence may be
  shown to a reviewer, but it cannot by itself authorize a numeric estimate.

That separation lets us improve evidence coverage without turning a merely
similar organization into an invented answer.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.estimator import tag_db
from backend.analyzer_v2 import split_articles, strip_appendices
from backend.legacy.committee.committee_estimator_v5.structure import extract_committee_events
from backend.scripts import evaluate_committee_precedent_routes as routes


DEFAULT_CASES = ROOT / "backend/generated/committee_precedent_pilot/pilot_cases.json"
DEFAULT_LABELS = (
    ROOT / "backend/generated/committee_precedent_pilot/manual_best_evidence_labels.json"
)

_FEATURE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    # Operating function.  These are domain classes, not institution-specific
    # names or answers from the evaluation set.
    ("function:investigation", re.compile(r"진상.{0,20}(?:규명|조사)|사실.{0,10}조사|조사대상|사건.{0,10}조사|특별조사")),
    ("function:rights_redress", re.compile(r"인권|권익|고충|차별|피해.{0,10}구제|민원")),
    ("function:regulator", re.compile(r"인가|허가|등록|관리.{0,3}감독|시정명령|제재")),
    ("function:adjudication", re.compile(r"심판|심사|분쟁.{0,5}조정|징계|평가")),
    ("function:strategy", re.compile(r"기본계획|종합계획|정책.{0,5}심의|전략|정책.{0,5}조정")),
    ("function:appointment", re.compile(r"후보.{0,5}추천|임명.{0,5}추천|인사위원회")),
    # Stable legal/organizational structure.
    ("structure:secretariat", re.compile(r"사무처|사무국|사무기구|지원조직|전담조직")),
    ("structure:staff", re.compile(r"소속.{0,8}직원|필요한.{0,5}직원|정원|인력.{0,5}구성")),
    ("structure:standing_member", re.compile(r"상임위원")),
    ("structure:subcommittee", re.compile(r"실무위원회|전문위원회|분과위원회|소위원회")),
    ("structure:independent", re.compile(r"독립적|독립.{0,8}(?:수행|업무|직무)|정치적.{0,5}중립")),
    ("structure:branches", re.compile(r"지부|지방.{0,5}위원회|시.{0,2}도.{0,5}위원회")),
    ("scope:central", re.compile(r"대통령.{0,5}소속|국무총리.{0,5}소속|장관.{0,5}소속")),
    ("scope:local", re.compile(r"지방자치단체.{0,15}(?:소속|설치|둔다)|시장.{0,3}군수.{0,3}구청장")),
)

_GENERIC_PHRASES = re.compile(
    r"위원장\d*(?:명|인)?(?:을|를)?포함(?:하여|한)?|"
    r"\d+(?:명|인)이내의위원으로구성|"
    r"위원회의구성및운영|위원회의설치|"
    r"위원회의사무를처리하기위하여|"
    r"대통령령으로정한다|필요한사항|"
    r"할수있다|하여야한다|둔다|설치한다"
)

_COST_SCOPE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cost:committee", re.compile(r"회의.{0,8}수당|참석.{0,8}수당|위원회.{0,8}운영")),
    ("cost:personnel", re.compile(r"인건비|보수|봉급|급여|기관부담금|직급별.{0,8}인력")),
    ("cost:basic", re.compile(r"기본경비|기관운영경비")),
    ("cost:program", re.compile(r"사업비|조사.{0,8}사업|운영사업")),
    ("cost:asset", re.compile(r"자산취득비|사무실.{0,8}공사|임차료")),
)


def _compact(value: str) -> str:
    return re.sub(r"[^가-힣A-Za-z0-9%]", "", value or "")


def extract_features(text: str) -> set[str]:
    compact = _compact(text)
    return {name for name, pattern in _FEATURE_RULES if pattern.search(compact)}


def cost_scopes(text: str) -> set[str]:
    compact = _compact(text)
    return {name for name, pattern in _COST_SCOPE_RULES if pattern.search(compact)}


def target_required_scopes(text: str) -> set[str]:
    """Infer only the cost families implied by the source bill's structure."""
    compact = _compact(text)
    scopes = {"cost:committee"}
    organization_heavy = bool(
        re.search(r"사무처|사무국|사무기구|소속.{0,8}직원|상임위원", compact)
    )
    if organization_heavy:
        scopes.update({"cost:personnel", "cost:basic", "cost:program"})
    return scopes


def _ngrams(value: str, n: int = 3) -> set[str]:
    compact = _compact(_GENERIC_PHRASES.sub("", value))
    if len(compact) < n:
        return {compact} if compact else set()
    return {compact[index:index + n] for index in range(len(compact) - n + 1)}


def _idf(gram_sets: Iterable[set[str]]) -> dict[str, float]:
    rows = list(gram_sets)
    document_frequency: dict[str, int] = defaultdict(int)
    for grams in rows:
        for gram in grams:
            document_frequency[gram] += 1
    total = max(1, len(rows))
    return {
        gram: math.log((total + 1) / (count + 1)) + 1.0
        for gram, count in document_frequency.items()
    }


def _weighted_containment(query: set[str], document: set[str], idf: dict[str, float]) -> float:
    if not query or not document:
        return 0.0
    denominator = sum(idf.get(gram, 1.0) for gram in query)
    if not denominator:
        return 0.0
    return sum(idf.get(gram, 1.0) for gram in query & document) / denominator


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left and right else 0.0


def _load_bill_sidecars() -> tuple[dict[str, str], dict[str, set[str]]]:
    """Build multi-field candidate text and normalized cost scopes per bill."""
    data = tag_db._load()
    text_parts: dict[str, list[str]] = defaultdict(list)
    scopes: dict[str, set[str]] = defaultdict(set)
    for item_id, meta in data["items"].items():
        bill_no = str(meta.get("bill_no") or "")
        if not bill_no:
            continue
        item_parts = [
            str(meta.get("bill_name") or ""),
            str(meta.get("name") or ""),
            str(meta.get("category") or ""),
        ]
        for variable in data["vars"].get(item_id, []):
            item_parts.extend(
                [
                    str(variable.get("name") or ""),
                    str(variable.get("source_text") or "")[:800],
                ]
            )
        item_text = " ".join(item_parts)
        text_parts[bill_no].append(item_text)
        family = str(meta.get("family") or "")
        if family == "committee":
            scopes[bill_no].add("cost:committee")
        elif family == "personnel":
            scopes[bill_no].add("cost:personnel")
        scopes[bill_no].update(cost_scopes(item_text))
    return (
        {bill_no: " ".join(parts) for bill_no, parts in text_parts.items()},
        dict(scopes),
    )


def _feature_score(target: set[str], candidate: set[str]) -> float:
    function = {value for value in target if value.startswith("function:")}
    candidate_function = {value for value in candidate if value.startswith("function:")}
    structure = {value for value in target if value.startswith("structure:")}
    candidate_structure = {value for value in candidate if value.startswith("structure:")}
    scope = {value for value in target if value.startswith("scope:")}
    candidate_scope = {value for value in candidate if value.startswith("scope:")}
    function_score = _jaccard(function, candidate_function)
    structure_score = (
        len(structure & candidate_structure) / len(structure)
        if structure else 0.0
    )
    scope_score = _jaccard(scope, candidate_scope) if scope else 0.0
    mismatch_penalty = 0.0
    if "scope:central" in target and "scope:local" in candidate and "scope:central" not in candidate:
        mismatch_penalty = 0.20
    elif "scope:local" in target and "scope:central" in candidate and "scope:local" not in candidate:
        mismatch_penalty = 0.20
    return max(
        0.0,
        0.55 * function_score + 0.35 * structure_score + 0.10 * scope_score
        - mismatch_penalty,
    )


def _target_event_text(case: dict[str, Any]) -> str:
    """Return only the named committee event, not the bill's unrelated tail.

    Some enactments amend dozens of other laws.  Feeding that entire PDF to a
    feature scorer makes words in consequential amendments look like duties of
    the target committee.  v5 already has a deterministic article/event
    extractor, so the comparison reuses that production-shaped boundary.
    """
    persisted = routes._target_passages(case)
    if case.get("target_passages"):
        # Frozen blind cases deliberately retain only source-law passages.
        # They contain no target estimate and are therefore safe query input.
        return " ".join([str(case["bill_name"]), *persisted])

    raw_text = routes._pdf_text(ROOT / str(case["source_pdf"]))
    articles, _ = split_articles(strip_appendices(raw_text))
    events = extract_committee_events(raw_text, articles)
    terms = [routes._compact(str(value)) for value in case.get("target_terms") or []]
    matched = [
        event for event in events
        if any(
            term and (
                term in routes._compact(event.name)
                or routes._compact(event.name) in term
            )
            for term in terms
        )
    ]
    selected = matched or events
    event_parts: list[str] = [str(case["bill_name"])]
    for event in selected:
        event_parts.extend(
            [
                event.name,
                *event.texts,
                *event.subordinate_bodies,
                *event.optional_subordinate_bodies,
                *event.support_organizations,
            ]
        )
        if event.has_standing_members:
            event_parts.append("상임위원")
        if event.has_standing_staff:
            event_parts.append("상근 직원 정원")
    return " ".join(event_parts)


def _target_anchored_text(
    case: dict[str, Any],
    passages: list[str] | None = None,
) -> str:
    """Build a query from the named body's bounded source-law passages.

    The structural event extractor deliberately ignores appendices and can
    miss a cost-bearing preparation committee established there.  Falling
    back to every other event in the main body then creates a query-boundary
    error before ranking even begins.  This route stays source-only and uses
    the existing bounded passage extractor, so it repairs that boundary
    without consulting the target cost estimate.
    """
    selected = passages if passages is not None else routes._target_passages(case)
    return " ".join([str(case["bill_name"]), *selected])


def _target_proposal_text(case: dict[str, Any]) -> str:
    """Return the proposal/major-content window as a separate domain field."""
    if case.get("target_passages"):
        return " ".join([str(case["bill_name"]), *routes._target_passages(case)])
    raw_text = routes._pdf_text(ROOT / str(case["source_pdf"]))
    compact = re.sub(r"\s+", "", raw_text)
    boundaries = [
        position for marker in ("법률제", "법률 제")
        if (position := compact.find(marker)) > 0
    ]
    end = min(boundaries) if boundaries else min(len(compact), 5_000)
    return " ".join([str(case["bill_name"]), compact[:end]])


def _domain_history_score(
    event_features: set[str],
    proposal_features: set[str],
    candidate_history: set[str],
    required_scopes: set[str],
    available_scopes: set[str],
    proposal_fielded: float,
) -> float:
    event_structure = {
        value for value in event_features
        if value.startswith("structure:") or value.startswith("scope:")
    }
    candidate_structure = {
        value for value in candidate_history
        if value.startswith("structure:") or value.startswith("scope:")
    }
    domain = {
        value for value in proposal_features if value.startswith("function:")
    }
    candidate_domain = {
        value for value in candidate_history if value.startswith("function:")
    }
    structure_coverage = (
        len(event_structure & candidate_structure) / len(event_structure)
        if event_structure else 0.0
    )
    domain_overlap = _jaccard(domain, candidate_domain)
    incompatible_scope = (
        "scope:central" in event_structure
        and "scope:local" in candidate_structure
        and "scope:central" not in candidate_structure
    )
    score = (
        0.38 * structure_coverage
        + 0.30 * domain_overlap
        + 0.25 * _scope_score(required_scopes, available_scopes)
        + 0.07 * proposal_fielded
    )
    return max(0.0, score - (0.18 if incompatible_scope else 0.0))


def _scope_score(required: set[str], available: set[str]) -> float:
    return len(required & available) / len(required) if required else 0.0


def _institution_history_score(
    target: set[str],
    candidate: set[str],
    required_scopes: set[str],
    available_scopes: set[str],
    fielded: float,
) -> float:
    """Compare institutional form across all prior versions of one law.

    A single amendment estimate may discuss only one subcommittee even though
    another estimate of the same institution contains its secretariat or
    standing-member structure.  Aggregating stable observations by law family
    repairs that fragmented view without importing a target answer.
    """
    target_structure = {
        value for value in target
        if value.startswith("structure:") or value.startswith("scope:")
    }
    candidate_structure = {
        value for value in candidate
        if value.startswith("structure:") or value.startswith("scope:")
    }
    structural_coverage = (
        len(target_structure & candidate_structure) / len(target_structure)
        if target_structure else 0.0
    )
    target_function = {value for value in target if value.startswith("function:")}
    candidate_function = {
        value for value in candidate if value.startswith("function:")
    }
    function_overlap = _jaccard(target_function, candidate_function)
    incompatible_scope = (
        (
            "scope:central" in target
            and "scope:local" in candidate
            and "scope:central" not in candidate
        )
        or (
            "scope:local" in target
            and "scope:central" in candidate
            and "scope:local" not in candidate
        )
    )
    score = (
        0.58 * structural_coverage
        + 0.25 * _scope_score(required_scopes, available_scopes)
        + 0.12 * function_overlap
        + 0.05 * fielded
    )
    return max(0.0, score - (0.20 if incompatible_scope else 0.0))


def _rank_map(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {str(row["bill_no"]): index for index, row in enumerate(rows, 1)}


def _rrf(rankings: list[list[dict[str, Any]]], k: int = 20) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, row in enumerate(ranking, 1):
            scores[str(row["bill_no"])] += 1.0 / (k + rank)
    return dict(scores)


def _first_rank(ranking: list[dict[str, Any]], wanted: set[str]) -> int | None:
    return next(
        (index for index, row in enumerate(ranking, 1) if str(row["bill_no"]) in wanted),
        None,
    )


def compare(cases_path: Path, labels_path: Path) -> dict[str, Any]:
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    labels = {
        str(row["bill_no"]): row
        for row in json.loads(labels_path.read_text(encoding="utf-8"))
    }
    metadata = routes._load_metadata()
    candidates = routes._load_candidate_texts(metadata)
    relation_idf = routes._idf_by_token(candidates.values())
    sidecar_text, sidecar_scopes = _load_bill_sidecars()

    candidate_docs = {
        bill_no: " ".join(
            [candidate.bill_name, candidate.full_text, sidecar_text.get(bill_no, "")]
        )
        for bill_no, candidate in candidates.items()
    }
    candidate_grams = {
        bill_no: _ngrams(text[:30_000])
        for bill_no, text in candidate_docs.items()
    }
    gram_idf = _idf(candidate_grams.values())
    candidate_features = {
        bill_no: extract_features(text)
        for bill_no, text in candidate_docs.items()
    }
    candidate_scopes: dict[str, set[str]] = {}
    for candidate_no, candidate in candidates.items():
        available = set(sidecar_scopes.get(candidate_no, set()))
        available.update(cost_scopes(candidate.full_text))
        candidate_scopes[candidate_no] = available
    results: list[dict[str, Any]] = []

    for case in cases:
        bill_no = str(case["bill_no"])
        label = labels[bill_no]
        passages = routes._target_passages(case)
        target_text = _target_event_text(case)
        anchored_text = _target_anchored_text(case, passages)
        target_features = extract_features(target_text)
        proposal_text = _target_proposal_text(case)
        proposal_features = extract_features(proposal_text)
        required_scopes = target_required_scopes(target_text)
        query_grams = _ngrams(target_text[:12_000])
        anchored_grams = _ngrams(anchored_text[:12_000])
        proposal_grams = _ngrams(proposal_text[:8_000])
        eligible = [
            candidate
            for candidate in candidates.values()
            if routes._eligible_at_cutoff(
                candidate,
                target_bill_no=bill_no,
                cutoff_date=str(case.get("cutoff_date") or case["propose_date"]),
            )
        ]
        # Rebuild institution-history profiles inside the target's historical
        # cutoff.  A future amendment of the same law must not enrich an older
        # candidate with information unavailable at prediction time.
        law_features: dict[str, set[str]] = defaultdict(set)
        law_scopes: dict[str, set[str]] = defaultdict(set)
        for historical in eligible:
            historical_key = routes._normalise_law_name(historical.bill_name)
            if not historical_key:
                continue
            law_features[historical_key].update(
                candidate_features[historical.bill_no]
            )
            law_scopes[historical_key].update(
                candidate_scopes[historical.bill_no]
            )

        relation = sorted(
            (
                routes._relation_candidate(case, passages, candidate, relation_idf)
                for candidate in eligible
            ),
            key=lambda row: (float(row["relation_score"]), row["available_date"], row["bill_no"]),
            reverse=True,
        )
        relation_scores = {
            str(row["bill_no"]): float(row["relation_score"])
            for row in relation
        }
        fielded_rows: list[dict[str, Any]] = []
        anchored_rows: list[dict[str, Any]] = []
        structural_rows: list[dict[str, Any]] = []
        component_rows: list[dict[str, Any]] = []
        institution_rows: list[dict[str, Any]] = []
        domain_rows: list[dict[str, Any]] = []
        for candidate in eligible:
            candidate_no = candidate.bill_no
            document = candidate_docs[candidate_no]
            features = candidate_features[candidate_no]
            available_scopes = candidate_scopes[candidate_no]
            law_key = routes._normalise_law_name(candidate.bill_name)
            history_features = set(law_features.get(law_key, features))
            history_scopes = set(law_scopes.get(law_key, available_scopes))
            fielded = _weighted_containment(
                query_grams,
                candidate_grams[candidate_no],
                gram_idf,
            )
            anchored = _weighted_containment(
                anchored_grams,
                candidate_grams[candidate_no],
                gram_idf,
            )
            proposal_fielded = _weighted_containment(
                proposal_grams,
                candidate_grams[candidate_no],
                gram_idf,
            )
            feature = _feature_score(target_features, features)
            scope = _scope_score(required_scopes, available_scopes)
            base = relation_scores.get(candidate_no, 0.0)
            shared = {
                "bill_no": candidate_no,
                "bill_name": candidate.bill_name,
                "available_date": candidate.available_date,
                "fielded_score": round(fielded, 6),
                "feature_score": round(feature, 6),
                "scope_score": round(scope, 6),
                "relation_score": round(base, 6),
                "features": sorted(features),
                "cost_scopes": sorted(available_scopes),
            }
            fielded_rows.append({**shared, "score": fielded})
            anchored_rows.append({**shared, "score": anchored})
            structural_rows.append(
                {**shared, "score": 0.72 * feature + 0.18 * scope + 0.10 * fielded}
            )
            # Component discovery values structural compatibility first, then
            # whether the document actually contains the required cost fields.
            # The relation score remains a small corroborating signal only.
            component_rows.append(
                {
                    **shared,
                    "score": 0.52 * feature + 0.28 * scope + 0.12 * fielded + 0.08 * base,
                }
            )
            institution_rows.append(
                {
                    **shared,
                    "score": _institution_history_score(
                        target_features,
                        history_features,
                        required_scopes,
                        history_scopes,
                        fielded,
                    ),
                    "history_features": sorted(history_features),
                    "history_cost_scopes": sorted(history_scopes),
                }
            )
            domain_rows.append(
                {
                    **shared,
                    "score": _domain_history_score(
                        target_features,
                        proposal_features,
                        history_features,
                        required_scopes,
                        history_scopes,
                        proposal_fielded,
                    ),
                    "proposal_fielded_score": round(proposal_fielded, 6),
                    "history_features": sorted(history_features),
                    "history_cost_scopes": sorted(history_scopes),
                }
            )

        def sorted_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return sorted(
                rows,
                key=lambda row: (float(row["score"]), row["available_date"], row["bill_no"]),
                reverse=True,
            )

        fielded = sorted_rows(fielded_rows)
        anchored = sorted_rows(anchored_rows)
        structural = sorted_rows(structural_rows)
        component = sorted_rows(component_rows)
        institution = sorted_rows(institution_rows)
        domain = sorted_rows(domain_rows)
        decision, selected = routes._select_relation_candidate(relation)
        top_relation = relation[0] if relation else None
        relationship_visible = bool(
            decision == "retrieve"
            or (
                top_relation
                and bool(top_relation.get("same_law"))
            )
        )
        # Route selection, not score averaging: provenance-bearing history is
        # stronger than analogy.  The fielded component channel is used only
        # when no such relationship is visible, and remains non-executable.
        routed = relation if relationship_visible else anchored
        routed_name = (
            "relationship_history" if relationship_visible
            else "anchored_component_discovery"
        )
        fusion_scores = _rrf(
            [relation, fielded, anchored, structural, component, institution, domain]
        )
        fusion = sorted(
            (
                {
                    "bill_no": candidate.bill_no,
                    "bill_name": candidate.bill_name,
                    "score": fusion_scores.get(candidate.bill_no, 0.0),
                    "available_date": candidate.available_date,
                }
                for candidate in eligible
            ),
            key=lambda row: (float(row["score"]), row["available_date"], row["bill_no"]),
            reverse=True,
        )
        rankings = {
            "relation_baseline": relation,
            "masked_fielded": fielded,
            "anchored_passage": anchored,
            "structural_profile": structural,
            "component_scope": component,
            "institution_history": institution,
            "domain_structure": domain,
            "routed_evidence": routed,
            "late_fusion": fusion,
        }
        exact = {str(value) for value in label.get("exact_bill_nos") or []}
        primary = {
            str(value) for value in label.get("primary_component_bill_nos") or []
        }
        results.append(
            {
                "bill_no": bill_no,
                "status": label["evidence_status"],
                "target_features": sorted(target_features),
                "proposal_features": sorted(proposal_features),
                "required_scopes": sorted(required_scopes),
                "executable_decision": decision,
                "executable_selected": selected,
                "routed_evidence_channel": routed_name,
                "methods": {
                    name: {
                        "exact_rank": _first_rank(ranking, exact),
                        "component_rank": _first_rank(ranking, primary),
                        "top5": [str(row["bill_no"]) for row in ranking[:5]],
                    }
                    for name, ranking in rankings.items()
                },
            }
        )

    method_names = list(results[0]["methods"]) if results else []
    summaries: dict[str, dict[str, Any]] = {}
    exact_cases = [row for row in results if row["status"] == "exact_document"]
    component_cases = [
        row for row in results
        if row["status"] in {"related_but_stale", "component_bundle"}
    ]
    none_cases = [row for row in results if row["status"] == "none"]
    for name in method_names:
        def count_at(rows: list[dict[str, Any]], field: str, cutoff: int) -> int:
            return sum(
                row["methods"][name][field] is not None
                and int(row["methods"][name][field]) <= cutoff
                for row in rows
            )

        summaries[name] = {
            "exact_at_1": f"{count_at(exact_cases, 'exact_rank', 1)}/{len(exact_cases)}",
            "exact_at_10": f"{count_at(exact_cases, 'exact_rank', 10)}/{len(exact_cases)}",
            "component_at_5": f"{count_at(component_cases, 'component_rank', 5)}/{len(component_cases)}",
            "component_at_10": f"{count_at(component_cases, 'component_rank', 10)}/{len(component_cases)}",
        }

    return {
        "evaluation_type": "committee_evidence_architecture_comparison",
        "query_source": "source_bill_only",
        "runtime_modified": False,
        "case_count": len(results),
        "label_counts": {
            "exact": len(exact_cases),
            "component": len(component_cases),
            "none": len(none_cases),
        },
        "safety": {
            "component_routes_can_authorize_numeric_estimate": False,
            "safe_none_abstention": (
                f"{sum(row['executable_decision'] == 'abstain' for row in none_cases)}/"
                f"{len(none_cases)}"
            ),
        },
        "summaries": summaries,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = compare(args.cases, args.labels)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(
        f"cases={payload['case_count']} safe_none={payload['safety']['safe_none_abstention']}"
    )
    for name, summary in payload["summaries"].items():
        print(
            f"{name}: exact@1={summary['exact_at_1']} exact@10={summary['exact_at_10']} "
            f"component@5={summary['component_at_5']} "
            f"component@10={summary['component_at_10']}"
        )
    for row in payload["results"]:
        print(f"\n{row['bill_no']} [{row['status']}]")
        for name, result in row["methods"].items():
            print(
                f"  {name}: exact={result['exact_rank'] or '-'} "
                f"component={result['component_rank'] or '-'} "
                f"top5={','.join(result['top5'])}"
            )


if __name__ == "__main__":
    main()
