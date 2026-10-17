from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from ..analyzer_v2 import GEMINI_MODEL, LLM_PROFILE, gemini_json
from ..llm_profiles import research_direct_prompt
from .cache import get_or_create_json
from .calculation import coherent_committee_case, positive_amount
from .types import AtomicEvent, EventType, TagCandidate
from .variable_selection import (
    committee_formula_roles,
    has_time_varying_operands,
)


# Committee reranking keeps its independently validated/cache-stable version.
# Research-plan selection has a separate scorecard version below.
SELECTION_VERSION = "formula-first-semantic-precedent-v11"
RESEARCH_SCORECARD_VERSION = "research-semantic-scorecard-v4"
COMMITTEE_COMPANION_SCORECARD_VERSION = "committee-companion-scorecard-v1"

_PROMPT = """당신은 비용추계 선례를 선택하는 reranker다.
대상 비용사건에 실제로 준용할 선례를 후보 중 정확히 하나만 고른다.

선택 우선순위:
1. 비용 발생 메커니즘과 산식 구조가 같은가
2. 행위 주체·부담 주체·정책 기능과 대상 범위가 비슷한가
3. 조문에 명시된 규모 상한과 비용 규모를 결정하는 요인이 양립하는가
4. 공식 추계서에 필요한 변수와 출처가 완결되어 있는가
5. 대상처럼 위원회와 계획을 함께 규정한 의안에서 나온 선례인가
6. 동반 사건의 주기·정책 대상·소관 분야까지 같은가
7. 그 다음에 임베딩 유사도를 참고한다

중요한 역할 분리:
- 대상 사건 하나에 적용할 산식은 하나의 원자적 비용범위여야 한다. 위원회 운영비와
  별도 조직 인건비·계획수립비·실태조사비·시설비 등을 합친 패키지 총액은 선택하지 마라.
- 이번 선택은 '1회 또는 1년당 얼마인가'를 정할 선례를 고르는 단계다.
- 비용이 몇 년마다 발생하는지는 대상 조문으로 별도 계산하므로, 선례의 반복 주기가
  다르다는 이유만으로 1회 단가가 더 적합한 선례를 탈락시키지 마라.
- research_plan은 계획 이름의 단어보다 계획 대상기관·정책 목적·조사/연구 범위와
  소관 분야가 가까운지를 우선한다. 같은 부처라는 이유보다 계획의 직접 대상기관과
  계획 산출물의 목적이 일치하는지를 먼저 본다.
- committee_operation은 법정 위원 정수, 수당 지급대상 구성, 심의 기능과 소관 분야를
  우선한다.

역할 분리:
- 이 단계는 산식만 선택한다.
- 필요한 변수는 산식 선례 자체의 값을 우선 사용하고, 값이 없을 때에만 다음 단계가
  역할·단위·규모가 맞는 다른 공식 선례를 찾는다. 따라서 변수 하나가 비어 있다는
  이유만으로 가장 적합한 산식을 탈락시키지 마라.

금지:
- 평균·중앙값·최빈값을 만들지 마라.
- 후보의 숫자·금액은 가려져 있다. 구조·의미로만 선택하라.
- 알 수 없는 정답 금액에 가까워 보이는 후보를 선택하지 마라.
- 단어 하나가 겹친다는 이유만으로 선택하지 마라.

모든 후보가 구조적으로 부적합하면 candidate_id를 빈 문자열로 반환한다.
JSON만 반환한다:
{"candidate_id":"후보의 정확한 item_id","reason":"선택 근거","confidence":0.0}

대상 사건:
"""

_RESEARCH_SCORECARD_PROMPT = """당신은 계획·연구 비용 선례의 의미 적합성을
구조화하는 평가자다. 산식 호환성은 별도 코드가 판정하므로 평가하지 않는다.
금액을 예측하거나 후보 하나를 직접 선택하지 말고, 모든 후보를 다음 세 차원에서
각각 0~3점으로 평가한다.

채점 기준:
- target_relation_type은 다음 중 하나만 사용한다.
  · same_named_entity: 같은 명시적 대상기관·대상집단
  · legal_parent_child: 한 기관이 다른 기관의 법적 상위·하위·소속 기관
  · same_entity_class: 둘 다 같은 종류의 기관 또는 같은 종류의 대상집단
  · functional_association: 한 기관이 후보의 서비스·정책을 제공하거나 참여할 뿐
    기관·대상 자체는 다름
  · broad_domain: 같은 넓은 정책 분야만 공유
  · none: 관계 없음
- artifact_purpose_match: 3=같은 종류의 계획·조사·연구 산출물과 목적,
  2=산출물은 같고 목적이 유사, 1=간접 관련, 0=다름
- domain_match: 3=같은 세부 도메인, 2=인접 도메인, 1=같은 넓은 분야, 0=무관

중요:
- 후보 금액은 제공되지 않으며 금액 크기를 추정해서도 안 된다.
- 같은 부처라는 사실만으로 대상 관계를 높이지 마라.
- 기관이 어떤 서비스·정책의 주요 제공자라는 이유만으로 same_named_entity,
  legal_parent_child, same_entity_class를 주지 말고 functional_association을 사용한다.
- 직접 대상기관 관계와 산출물 목적을 각각 독립적으로 평가하라.
- 후보마다 정확히 한 행을 반환하라.

JSON만 반환한다:
{"scores":[{"candidate_id":"정확한 ID","target_relation_type":"none",
"artifact_purpose_match":0,"domain_match":0,
"reason":"짧은 근거"}]}

평가 대상:
"""

_COMMITTEE_COMPANION_SCORECARD_PROMPT = """당신은 법정 위원회 운영비
선례의 구조적 적합성을 평가하는 분류기다. 금액·인원·횟수를 예측하거나
후보 하나를 직접 선택하지 말고, 모든 후보를 다음 네 차원에서 각각
0~3점으로 평가한다.

채점 기준:
- policy_domain_match: 3=같은 세부 정책·산업 도메인, 2=직접 인접한
  도메인, 1=넓은 분야만 같음, 0=무관
- authority_institution_match: 3=같은 소관부처와 같은 기관·대상 유형,
  2=같은 소관부처 또는 같은 기관 유형, 1=관련 주체, 0=다름
- companion_artifact_match: 3=위원회와 같은 정책 대상의 계획·조사가
  같은 의안에서 같이 비용사건으로 계상됨, 2=동반 산출물의 종류와
  주기는 같으나 직접 대상이 인접함, 1=간접 관련, 0=없음
- committee_function_match: 3=같은 정책·계획 심의 기능, 2=유사한 상설
  자문·조정 기능, 1=사건별 판정·인허가 등 다른 회의 기능, 0=무관

중요:
- 후보의 모든 수치는 가려져 있다. 숨은 수치를 추정하지 마라.
- 법안 이름의 단어 하나가 겹친다는 이유로 점수를 주지 마라.
- 위원회와 계획이 같이 있어도, 둘의 정책 대상이 다르면
  companion_artifact_match를 3점으로 주지 마라.
- 후보마다 정확히 한 행을 반환하라.

JSON만 반환한다:
{"scores":[{"candidate_id":"정확한 ID","policy_domain_match":0,
"authority_institution_match":0,"companion_artifact_match":0,
"committee_function_match":0,"reason":"짧은 근거"}]}

평가 대상:
"""


_INDEPENDENT_COST_SCOPE_PATTERNS = (
    re.compile(
        r"실무추진단|실무지원단|협의지원단|지원단|사무처|사무국|전담조직|"
        r"인건비|기준인건비|보수|직원|공무원|기본경비"
    ),
    re.compile(
        r"종합계획|기본계획|시행계획|계획수립|실태조사|연구용역|조사연구"
    ),
    re.compile(r"시설|설비|전산시스템|정보시스템|구축비|장비|임차료"),
    re.compile(r"지원금|보조금|출연금|급여지급|장려금"),
)


def _is_compound_committee_package(candidate: TagCandidate) -> bool:
    """Return whether a TAG row totals multiple independent cost events."""
    variable_text = " ".join(
        f"{variable.get('name') or ''} {variable.get('source_text') or ''}"
        for variable in candidate.variables
    )
    compact = re.sub(
        r"\s+",
        "",
        f"{candidate.item_name} {candidate.formula} {variable_text}",
    )
    has_independent_scope = any(
        pattern.search(compact)
        for pattern in _INDEPENDENT_COST_SCOPE_PATTERNS
    )
    if not has_independent_scope:
        return False
    additive_formula = bool(
        re.search(
            r"\+|합계|합산|총액|각비용의합",
            re.sub(r"\s+", "", candidate.formula or ""),
        )
    )
    item_lists_multiple_scopes = bool(
        re.search(
            r"(?:위원회|심의회|협의회).*(?:및|,|/|그리고).*"
            r"(?:실무추진단|실무지원단|지원단|사무처|사무국|"
            r"종합계획|기본계획|실태조사|연구용역|시설|시스템)|"
            r"(?:실무추진단|실무지원단|지원단|사무처|사무국|"
            r"종합계획|기본계획|실태조사|연구용역|시설|시스템).*"
            r"(?:및|,|/|그리고).*(?:위원회|심의회|협의회)",
            re.sub(r"\s+", "", candidate.item_name),
        )
    )
    return additive_formula or item_lists_multiple_scopes


def _target_committee_cap(source_text: str) -> int | None:
    # Assembly PDFs frequently split a legal token across lines
    # ("25인이 내").  Formula selection must use the same whitespace-
    # insensitive cap parsing as operand selection; otherwise an impossible
    # formula case can survive the first gate and fail much later.
    compact = re.sub(r"\s+", "", source_text or "")
    matches = re.findall(r"(\d+)(?:인|명)이내", compact)
    return max((int(value) for value in matches), default=None)


def _is_support_body(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    return bool(re.search(r"지원위원회|지원협의회", compact))


def _committee_scope(text: str) -> str:
    compact = re.sub(r"\s+", "", text or "")
    if re.search(r"실무지원단|협의지원단|사무처|사무국", compact):
        return "support_office"
    if "수당" in compact and "운영" not in compact:
        return "allowance_only"
    if "운영" in compact:
        return "full_operation"
    return "unknown"


def _periods_in_text(value: str) -> set[int]:
    compact = re.sub(r"\s+", "", value or "")
    return {
        int(period)
        for period in re.findall(r"(\d+)년(?:마다|주기)", compact)
        if int(period) > 0
    }


def _companion_research_periods(candidate: TagCandidate) -> set[int]:
    periods: set[int] = set()
    for item in candidate.context_items:
        if item.get("family") != "research":
            continue
        periods.update(_periods_in_text(str(item.get("formula") or "")))
        for variable in item.get("variables") or []:
            periods.update(
                _periods_in_text(str(variable.get("source_text") or ""))
            )
            if (
                variable.get("type") == "period"
                and variable.get("value") is not None
                and "년" in str(variable.get("unit") or "")
            ):
                try:
                    periods.add(int(float(variable["value"])))
                except (TypeError, ValueError):
                    pass
    return periods


def _typed_committee_precedent(
    event: AtomicEvent,
    source_text: str,
    candidates: list[TagCandidate],
) -> TagCandidate | None:
    """Resolve an exact support-body/full-operation scope before LLM reranking."""
    target_text = f"{event.object} {event.action} {source_text}"
    if not _is_support_body(target_text):
        return None
    # A support body created by law necessarily has an operation event even
    # when the article uses "둔다/설치" rather than the literal word "운영".
    # Only an explicitly allowance-only target should stay in the formula path.
    if _committee_scope(target_text) == "allowance_only":
        return None
    exact = [
        candidate
        for candidate in candidates
        if _is_support_body(candidate.item_name)
        and _committee_scope(candidate.item_name) == "full_operation"
        and positive_amount(candidate) is not None
    ]
    if not exact:
        return None
    ranked = sorted(
        exact,
        key=lambda candidate: (-candidate.similarity, candidate.item_id),
    )
    if len(ranked) == 1 or ranked[0].similarity - ranked[1].similarity >= 0.05:
        return ranked[0]
    return None


def usable_candidates(
    event: AtomicEvent,
    source_text: str,
    candidates: list[TagCandidate],
) -> list[TagCandidate]:
    """Apply factual compatibility gates before semantic reranking."""
    if event.event_type == EventType.COMMITTEE.value:
        cap = _target_committee_cap(source_text)
        result: list[TagCandidate] = []
        for candidate in candidates:
            if _is_compound_committee_package(candidate):
                continue
            case = coherent_committee_case(candidate)
            has_supported_formula = bool(
                committee_formula_roles(candidate)
                and not has_time_varying_operands(candidate)
            )
            is_full_operation = (
                _is_support_body(candidate.item_name)
                and _committee_scope(candidate.item_name) == "full_operation"
                and positive_amount(candidate) is not None
            )
            if not case and not has_supported_formula and not is_full_operation:
                continue
            # A precedent whose paid attendees already exceed the target's
            # entire legal membership cap cannot be transferred coherently.
            if case and cap is not None and case["count"] > cap:
                continue
            result.append(candidate)
        return result
    if event.event_type == EventType.RESEARCH_PLAN.value:
        return [
            candidate
            for candidate in candidates
            if positive_amount(candidate) is not None
            and (candidate.formula or candidate.variables)
        ]
    return []


def _candidate_payload(candidate: TagCandidate) -> dict[str, Any]:
    rows = [row.get("year_offset") for row in candidate.amounts]
    return {
        "candidate_id": candidate.item_id,
        "bill_no": candidate.bill_no,
        "bill_name": candidate.bill_name,
        "item_name": candidate.item_name,
        "category": candidate.category,
        "embedding_similarity": candidate.similarity,
        "formula_shape": _mask_candidate_numbers(candidate.formula),
        "variables": [
            {
                "type": variable.get("type"),
                "name": variable.get("name"),
                "unit": variable.get("unit"),
                "basis": _mask_candidate_numbers(
                    str(variable.get("source_text") or "")
                ),
            }
            for variable in candidate.variables
        ],
        "formula_roles": sorted(set(committee_formula_roles(candidate))),
        "same_companion_signature": bool(candidate.context_families),
        "companion_cost_families": candidate.context_families,
        "companion_context_similarity": candidate.context_similarity,
        "companion_items": [
            {
                "family": item.get("family"),
                "name": item.get("name"),
                "formula_shape": _mask_candidate_numbers(
                    str(item.get("formula") or "")
                ),
                "variables": [
                    {
                        "type": variable.get("type"),
                        "name": variable.get("name"),
                        "unit": variable.get("unit"),
                        "basis": _mask_candidate_numbers(
                            str(variable.get("source_text") or "")
                        ),
                    }
                    for variable in item.get("variables") or []
                ],
            }
            for item in candidate.context_items
        ],
        "year_offsets": rows,
        "has_priced_series": positive_amount(candidate) is not None,
    }


def _mask_candidate_numbers(value: str) -> str:
    """Hide operand/amount values while preserving semantic formula shape."""
    return re.sub(r"\d[\d,.]*", "<수치>", value or "")


def _research_scorecard_candidate_payload(
    candidate: TagCandidate,
) -> dict[str, Any]:
    """Return semantic evidence without exposing candidate amounts."""
    return {
        "candidate_id": candidate.item_id,
        "bill_name": candidate.bill_name,
        "item_name": candidate.item_name,
        "category": candidate.category,
        "formula_shape": _mask_candidate_numbers(candidate.formula),
        "variables": [
            {
                "type": variable.get("type"),
                "name": variable.get("name"),
                "unit": variable.get("unit"),
                "basis": _mask_candidate_numbers(
                    str(variable.get("source_text") or "")
                ),
            }
            for variable in candidate.variables
        ],
    }


def _committee_companion_scorecard_candidate_payload(
    candidate: TagCandidate,
) -> dict[str, Any]:
    """Expose structural meaning while hiding every candidate operand."""
    payload = _candidate_payload(candidate)
    # Embedding recall has already done its job.  Showing its score to the
    # semantic classifier would anchor the model on the noisy retrieval rank.
    payload.pop("embedding_similarity", None)
    payload.pop("companion_context_similarity", None)
    payload.pop("year_offsets", None)
    return payload


def _score(value: Any) -> int:
    try:
        return max(0, min(3, int(value)))
    except (TypeError, ValueError):
        return 0


def _choose_committee_companion_scorecard_candidate(
    candidates: list[TagCandidate],
    result: Any,
) -> tuple[TagCandidate | None, str, float]:
    """Choose by audited semantic dimensions, never by candidate amounts.

    The model only labels meaning.  Code applies the acceptance thresholds,
    refuses structural ties, and uses embedding similarity merely as audit
    metadata.  This prevents a numerically convenient but semantically remote
    formula case from winning by accident.
    """
    parsed = result if isinstance(result, dict) else {}
    rows = parsed.get("scores")
    if not isinstance(rows, list):
        return None, "위원회 동반 선례 의미 점수표를 생성하지 못했습니다.", 0.0

    by_id = {candidate.item_id: candidate for candidate in candidates}
    scored: list[
        tuple[tuple[int, int, int, int], TagCandidate, str]
    ] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate_id = str(row.get("candidate_id") or "")
        candidate = by_id.get(candidate_id)
        if candidate is None or candidate_id in seen:
            continue
        seen.add(candidate_id)
        scores = (
            _score(row.get("policy_domain_match")),
            _score(row.get("authority_institution_match")),
            _score(row.get("companion_artifact_match")),
            _score(row.get("committee_function_match")),
        )
        scored.append((scores, candidate, str(row.get("reason") or "")))

    # An incomplete scorecard is not silently treated as a low score: the
    # missing candidate might have been the best structural precedent.
    if seen != set(by_id):
        return (
            None,
            "후보 전체를 평가한 점수표가 아니어서 자동 선택을 중단했습니다.",
            0.0,
        )

    eligible = [
        entry
        for entry in scored
        if entry[0][0] >= 2  # same or directly adjacent policy domain
        and entry[0][1] >= 2  # same authority or institution type
        and entry[0][2] >= 2  # genuinely paired plan/research structure
        and entry[0][3] >= 2  # standing policy/advisory committee
    ]
    if not eligible:
        return (
            None,
            "금액을 숨긴 구조 점수표에서 도메인·소관·동반 계획·"
            "위원회 기능을 모두 충족한 선례가 없습니다.",
            0.0,
        )

    eligible.sort(
        key=lambda entry: (
            -entry[0][0],
            -entry[0][1],
            -entry[0][2],
            -entry[0][3],
            entry[1].item_id,
        )
    )
    top_scores, selected, model_reason = eligible[0]
    if len(eligible) > 1 and eligible[1][0] == top_scores:
        return (
            None,
            "최상위 후보들의 구조 점수가 동률이어서 임베딩 순위나 "
            "금액으로 임의 타결하지 않았습니다.",
            round(sum(top_scores) / 12, 2),
        )

    reason = (
        "후보 수치와 임베딩 순위를 숨긴 구조 점수표에서 "
        f"도메인 {top_scores[0]}/3, 소관·기관 {top_scores[1]}/3, "
        f"동반 계획 {top_scores[2]}/3, 위원회 기능 {top_scores[3]}/3으로 "
        f"{selected.bill_no}을 선택했습니다."
    )
    if model_reason:
        reason += f" {model_reason[:500]}"
    return selected, reason, round(sum(top_scores) / 12, 2)


def _select_committee_companion_precedent(
    event: AtomicEvent,
    source_text: str,
    candidates: list[TagCandidate],
    *,
    refresh: bool,
) -> tuple[TagCandidate | None, str, float, bool]:
    candidate_payloads = [
        _committee_companion_scorecard_candidate_payload(candidate)
        for candidate in sorted(candidates, key=lambda value: value.item_id)
    ]
    payload = {
        "version": COMMITTEE_COMPANION_SCORECARD_VERSION,
        "model": GEMINI_MODEL,
        "event": asdict(event),
        "source_text": source_text,
        "candidates": candidate_payloads,
    }
    prompt = _COMMITTEE_COMPANION_SCORECARD_PROMPT + str(
        {
            "event": asdict(event),
            "source_text": source_text,
            "candidates": candidate_payloads,
        }
    )
    result, cache_hit = get_or_create_json(
        "committee_companion_scorecard",
        payload,
        lambda: gemini_json(prompt, temperature=0.0),
        refresh=refresh,
    )
    selected, reason, confidence = (
        _choose_committee_companion_scorecard_candidate(candidates, result)
    )
    return selected, reason, confidence, cache_hit


_TARGET_RELATION_SCORES = {
    "same_named_entity": 3,
    "legal_parent_child": 3,
    "same_entity_class": 2,
    "functional_association": 1,
    "broad_domain": 1,
    "none": 0,
}


def _target_relation_score(value: Any) -> int:
    return _TARGET_RELATION_SCORES.get(str(value or "").strip().lower(), 0)


def _research_mechanism_score(candidate: TagCandidate) -> int:
    """Score formula transferability from structured TAG, not model opinion."""
    if positive_amount(candidate) is None:
        return 0
    roles = {
        str(variable.get("type") or "").lower()
        for variable in candidate.variables
    }
    has_unit_cost = bool(
        roles
        & {
            "unit_cost",
            "unit_price",
            "cost_per_case",
            "service_cost",
        }
    )
    has_period = bool(
        roles
        & {
            "period",
            "frequency",
            "cycle",
            "interval",
        }
    )
    if has_unit_cost and has_period:
        return 3
    if candidate.formula or candidate.variables:
        return 2
    return 1


def _choose_research_scorecard_candidate(
    candidates: list[TagCandidate],
    result: Any,
) -> tuple[TagCandidate | None, str, float]:
    """Choose deterministically from a model-produced semantic scorecard."""
    parsed = result if isinstance(result, dict) else {}
    rows = parsed.get("scores")
    if not isinstance(rows, list):
        return None, "계획 선례 의미 점수표를 생성하지 못했습니다.", 0.0
    by_id = {candidate.item_id: candidate for candidate in candidates}
    ranked: list[tuple[tuple[int, int, int, int], TagCandidate, str]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate_id = str(row.get("candidate_id") or "")
        candidate = by_id.get(candidate_id)
        if candidate is None or candidate_id in seen:
            continue
        seen.add(candidate_id)
        scores = (
            _research_mechanism_score(candidate),
            _target_relation_score(row.get("target_relation_type")),
            _score(row.get("artifact_purpose_match")),
            _score(row.get("domain_match")),
        )
        # A merely related policy document is not a transferable cost formula.
        if scores[0] < 2:
            continue
        ranked.append((scores, candidate, str(row.get("reason") or "")))
    if not ranked:
        return (
            None,
            "금액을 숨긴 의미 점수표에서 산식 구조가 준용 가능한 선례가 없습니다.",
            0.0,
        )
    ranked.sort(
        key=lambda value: (
            -value[0][0],
            -value[0][1],
            -value[0][2],
            -value[0][3],
            -value[1].similarity,
            value[1].item_id,
        )
    )
    scores, candidate, model_reason = ranked[0]
    if scores[1] < 2:
        return (
            None,
            "금액을 숨긴 의미 점수표에서 산식은 호환되지만 대상기관·대상집단 "
            "관계가 기능적 연관 수준에 그쳐 자동 준용하지 않았습니다.",
            round(sum(scores) / 12, 2),
        )
    reason = (
        "후보 금액을 숨긴 의미 점수표에서 "
        f"산식 {scores[0]}/3, 직접 대상 {scores[1]}/3, "
        f"산출물 목적 {scores[2]}/3, 도메인 {scores[3]}/3으로 "
        f"{candidate.bill_no}을 결정적으로 선택했습니다."
    )
    if model_reason:
        reason += f" {model_reason}"
    confidence = round(sum(scores) / 12, 2)
    return candidate, reason, confidence


def _select_research_precedent(
    event: AtomicEvent,
    source_text: str,
    candidates: list[TagCandidate],
    *,
    refresh: bool,
) -> tuple[TagCandidate | None, str, float, bool]:
    candidate_payloads = [
        _research_scorecard_candidate_payload(candidate)
        for candidate in candidates
    ]
    direct = research_direct_prompt(
        LLM_PROFILE,
        event=asdict(event),
        source_text=source_text,
        candidates=candidate_payloads,
    )
    if direct:
        prompt, window = direct
        window_ids = {
            str(candidate.get("candidate_id") or "")
            for candidate in window
        }
        direct_payload = {
            "version": f"{RESEARCH_SCORECARD_VERSION}:solar-direct-v2",
            "model": GEMINI_MODEL,
            "event": asdict(event),
            "source_text": source_text,
            "candidates": window,
        }
        result, cache_hit = get_or_create_json(
            "research_precedent_scorecard",
            direct_payload,
            lambda: gemini_json(prompt, temperature=0.0),
            refresh=refresh,
        )
        result = result if isinstance(result, dict) else {}
        candidate_id = str(result.get("candidate_id") or "")
        selected = next(
            (
                candidate
                for candidate in candidates
                if candidate.item_id == candidate_id
                and candidate_id in window_ids
            ),
            None,
        )
        relation = _target_relation_score(result.get("target_relation_type"))
        purpose = _score(result.get("artifact_purpose_match"))
        domain = _score(result.get("domain_match"))
        mechanism = (
            _research_mechanism_score(selected)
            if selected is not None
            else 0
        )
        try:
            model_confidence = max(
                0.0,
                min(1.0, float(result.get("confidence") or 0)),
            )
        except (TypeError, ValueError):
            model_confidence = 0.0
        if (
            selected is None
            or mechanism < 2
            or relation < 2
            or purpose < 2
            or model_confidence < 0.65
        ):
            return (
                None,
                "Solar 소형 의미 reranker에서 후보 ID·산식 호환성·직접 "
                "대상 관계·산출물 목적·신뢰도를 동시에 만족하는 계획 "
                "선례를 확정하지 못했습니다.",
                min(model_confidence, round((mechanism + relation + purpose + domain) / 12, 2)),
                cache_hit,
            )
        reason = (
            "후보 금액을 숨긴 상위 8건의 소형 의미 reranker에서 "
            f"산식 {mechanism}/3, 직접 대상 {relation}/3, "
            f"산출물 목적 {purpose}/3, 도메인 {domain}/3으로 "
            f"{selected.bill_no}을 선택했습니다."
        )
        model_reason = str(result.get("reason") or "")[:500]
        if model_reason:
            reason += f" {model_reason}"
        evidence_confidence = round(
            (mechanism + relation + purpose + domain) / 12,
            2,
        )
        return (
            selected,
            reason,
            min(model_confidence, max(0.65, evidence_confidence)),
            cache_hit,
        )
    payload = {
        "version": RESEARCH_SCORECARD_VERSION,
        "model": GEMINI_MODEL,
        "event": asdict(event),
        "source_text": source_text,
        "candidates": candidate_payloads,
    }
    prompt = _RESEARCH_SCORECARD_PROMPT + str(
        {
            "event": asdict(event),
            "source_text": source_text,
            "candidates": candidate_payloads,
        }
    )
    result, cache_hit = get_or_create_json(
        "research_precedent_scorecard",
        payload,
        lambda: gemini_json(prompt, temperature=0.0),
        refresh=refresh,
    )
    selected, reason, confidence = _choose_research_scorecard_candidate(
        candidates,
        result,
    )
    return selected, reason, confidence, cache_hit


def _resolve_returned_candidate(
    candidates: list[TagCandidate],
    returned_id: str,
) -> tuple[TagCandidate | None, bool]:
    """Resolve an exact item ID or one unambiguous shortened provider ID."""
    exact = next(
        (candidate for candidate in candidates if candidate.item_id == returned_id),
        None,
    )
    if exact is not None:
        return exact, False
    if not returned_id:
        return None, False
    shortened_matches = [
        candidate
        for candidate in candidates
        if candidate.item_id.startswith(f"{returned_id}::")
    ]
    if len(shortened_matches) == 1:
        return shortened_matches[0], True
    return None, False


def select_precedent(
    event: AtomicEvent,
    source_text: str,
    candidates: list[TagCandidate],
    *,
    refresh: bool = False,
) -> tuple[TagCandidate | None, str, float, bool]:
    usable = usable_candidates(event, source_text, candidates)
    if not usable:
        return None, "산식·변수·규모 조건을 만족하는 완결 선례가 없습니다.", 0.0, False
    target_companion_periods = _periods_in_text(source_text)
    period_aligned = [
        candidate
        for candidate in usable
        if target_companion_periods.intersection(
            _companion_research_periods(candidate)
        )
    ]
    period_gate_reason = ""
    if period_aligned:
        usable = period_aligned
        period_gate_reason = (
            "동일 의안에 함께 규정된 계획의 주기가 "
            f"{sorted(target_companion_periods)}년으로 일치하는 완결 산식 "
            "선례만 의미 재랭킹했습니다. "
        )
    typed = _typed_committee_precedent(event, source_text, usable)
    if typed is not None:
        return (
            typed,
            "지원위원회·지원협의회의 전체 운영비 사건에서 수당만 또는 지원단만 "
            "계상한 항목을 제외하고, 같은 전체 운영 범위 후보 중 의미 점수 "
            f"우위가 명확한 {typed.bill_no}을 선택했습니다.",
            0.9,
            False,
        )
    if event.event_type == EventType.RESEARCH_PLAN.value:
        return _select_research_precedent(
            event,
            source_text,
            usable,
            refresh=refresh,
        )
    if event.event_type == EventType.COMMITTEE.value and period_aligned:
        selected, reason, confidence, cache_hit = (
            _select_committee_companion_precedent(
                event,
                source_text,
                usable,
                refresh=refresh,
            )
        )
        return (
            selected,
            period_gate_reason + reason,
            confidence,
            cache_hit,
        )
    payload = {
        "selection_version": SELECTION_VERSION,
        "model": GEMINI_MODEL,
        "event": asdict(event),
        "source_text": source_text,
        "candidates": [_candidate_payload(candidate) for candidate in usable],
    }
    prompt = (
        _PROMPT
        + str(
            {
                "event": asdict(event),
                "source_text": source_text,
                "candidates": payload["candidates"],
            }
        )
    )
    result, cache_hit = get_or_create_json(
        "precedent_selection",
        payload,
        lambda: gemini_json(prompt, temperature=0.0),
        refresh=refresh,
    )
    result = result if isinstance(result, dict) else {}
    selected_id = str(result.get("candidate_id") or "")
    selected, expanded_short_id = _resolve_returned_candidate(
        usable,
        selected_id,
    )
    reason = str(result.get("reason") or "")
    if selected is not None and period_gate_reason:
        reason = period_gate_reason + reason
    if selected is not None and expanded_short_id:
        reason = (
            f"{reason} / 공급자가 항목 접미사를 생략한 후보 ID를 반환했으며, "
            "동일 기본 ID 후보가 하나뿐임을 확인해 전체 항목 ID로 복원했습니다."
        ).strip(" /")
    try:
        confidence = max(0.0, min(1.0, float(result.get("confidence") or 0)))
    except (TypeError, ValueError):
        confidence = 0.0
    if selected is None:
        # A failed or malformed reranker response must not silently select a
        # case.  The pipeline will request human evidence.
        return None, reason or "의미 reranker가 준용 가능한 선례를 선택하지 못했습니다.", confidence, cache_hit
    return selected, reason, confidence, cache_hit
