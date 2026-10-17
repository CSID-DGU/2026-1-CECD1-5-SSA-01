"""Solar Pro2 profile for the evidence-first estimator.

This profile changes only how the model is instructed to interpret an already
fixed candidate set. It never sees an official target amount and cannot add or
edit candidates, formulas, or operand values.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any


PROFILE_ID = "solar_pro2_evidence_v3"

_BASE = """당신은 비용추계 파이프라인의 한 단계만 수행한다.
반드시 사용자 메시지에 지정된 JSON 스키마 하나만 반환하라.
설명문, 마크다운, 코드펜스는 출력하지 마라.
입력에 있는 ID는 한 글자도 생략하거나 바꾸지 말고 정확히 복사하라.
정답 금액을 추정하거나 후보에 없는 숫자·사실을 만들지 마라.
판단 전 출력이 입력 근거와 JSON 스키마를 모두 만족하는지 자체 점검하라."""

_EVENTS = """이번 단계는 비용사건 추출이다.
- 모든 법률행위를 나열하지 말고 추가 공공재정이 생길 수 있는 사건만 반환한다.
- 목적·정의·명칭·관할구역·준용·보고절차만 있는 조항은 비용사건으로 만들지 않는다.
- 일반 정책·자문·심의위원회는 committee_operation이다. 이를 organization_change나 subsidy로 분류하지 않는다.
- 일반 위원회의 설치·구성·회의·수당 조항은 committee_operation 사건 하나로 합치고 중복 생성하지 않는다.
- 위원회 설치가 의무이면 수당 조항이 "지급할 수 있다"여도 통상 운영비 사건의 obligation은 mandatory로 유지한다.
- 조직 신설·승격은 organization_change 하나로만 반환하며 인력·시설 사건을 별도로 만들지 않는다.
- 국회 상임위원회·특별위원회는 회의수당 위원회가 아니라 사무조직·인력 비용을 수반하는
  입법위원회 사건임을 explanation에 명시한다.
- 기존 직원 중 담당관을 지정하는 조항은 신규 조직을 지어내지 말고 지정 사건 하나로 반환한다.
- quotes는 핵심 근거 1~3개만 해당 segment 원문에서 글자까지 그대로 복사하고,
  segment_ids와 article_refs도 정확히 대응시킨다. 원문을 요약하거나 OCR 글자를 고치지 않는다.
- 동일 object의 사건을 여러 개 만들었는지 마지막에 확인해 하나로 합친다."""

_FORMULA = """이번 단계는 산식 선례 선택이다.
- 후보 금액의 크기는 보지 말고 비용사건 범위와 곱셈·합산 구조가 같은 선례 하나를 고른다.
- 대상 규모가 후보와 다르더라도 다음 계산 단계에서 비율 조정 가능한 경우 그 이유만으로 탈락시키지 않는다.
- 구조적으로 쓸 수 있는 후보가 있으면 빈 ID를 반환하지 않는다.
- candidate_id는 선택한 후보의 전체 item_id를 접미사까지 정확히 복사한다."""

_VARIABLE = """이번 단계는 하나의 변수 근거 선택이다.
- 후보에 이미 존재하는 값 하나만 선택하며 숫자를 수정하거나 평균을 만들지 않는다.
- count는 수당 지급대상, unit_price는 동일 비용 구성과 기준시점, frequency는 실제 기능과 개최 성격을 비교한다.
- 정책·계획 심의위원회에는 사건 발생량에 따라 열리는 심사·분쟁·인허가 위원회의 실적 횟수를 고르지 않는다.
- 사건처리 위원회에는 정기 정책위원회의 분기별 횟수를 고르지 않는다.
- 역할·단위·기능이 맞는 후보가 있으면 빈 ID를 반환하지 않는다.
- option_id는 선택한 후보의 전체 ID를 정확히 복사한다."""

_ORG_STRUCTURE = """이번 단계는 조직 구조 선례 선택이다.
- 신설·승격·분리, 상위기관, 인사체계, 상설성, 기존 조직 차감 구조를 비교한다.
- 대상 인원과 선례 인원이 다르더라도 별도 HITL 인원으로 비례 계산하므로 규모 차이만으로 탈락시키지 않는다.
- 같은 법형식과 인사체계의 선례가 있으면 빈 bill_no를 반환하지 않는다.
- bill_no는 후보에 표시된 의안번호를 정확히 복사한다."""

_ORG_VALUE = """이번 단계는 조직 인력비 값 선례 후보군 선택이다.
- 신설·승격 모양이 달라도 같은 상위기관·예산·인사·보수 체계이면 조건부 후보군에 포함한다.
- 대상 순증 인원은 외부 HITL 값으로 주어지므로 후보 인원과 다르다는 이유로 제외하지 않는다.
- 기존 직원 중 담당관 지정도 사용자가 순증 인원을 입력했다면 같은 기관계열의 완결 인력비 선례를 포함한다.
- 입법위원회의 의원 수와 사무처 직원 수를 혼동하지 않는다.
- compatible_bill_nos는 후보에 있는 의안번호만 정확히 복사한다."""

_DEDICATED_STAFF_VALUE = """이번 단계는 전담인력 HITL 값 선례의 단일 reranking이다.
- 사용자가 대상 순증 인원을 별도로 입력했으므로 후보 인원 수는 선택 기준이 아니다.
- 후보 금액이나 임베딩 순위가 아니라 다음 순서로 가장 가까운 후보 하나만 고른다:
  1) 동일 고용·예산·보수 체계(공공기관 직원/국가공무원/지방공무원 등)
  2) 동일 기관 유형과 감독 부처
  3) 동일 업무 도메인과 직무 성격
- 완결 비용항목과 수명주기는 코드가 이미 검증했다.
- 여러 후보를 복사하지 말고 bill_no 하나만 반환한다.
- 이유는 두 문장 이내로 쓴다.
JSON만 반환한다:
{"bill_no":"의안번호","reason":"의미 호환 근거","confidence":0.0}"""

_RESEARCH = """이번 단계는 계획·연구 선례 점수표 작성이다.
모든 candidate_id에 대해 빠짐없이 한 행씩 반환하고 ID를 정확히 복사한다.
기관 관계, 산출물 목적, 세부 도메인을 독립적으로 평가하며 금액은 고려하지 않는다."""

_RESEARCH_DIRECT = """이번 단계는 계획·연구 선례의 소형 semantic reranking이다.
- 후보 금액은 제공되지 않으며 고려하지 않는다.
- 먼저 대상기관·대상집단의 법적 관계를 비교하고, 그다음 계획 산출물의 목적과
  세부 정책 도메인을 비교한다.
- 같은 부처나 넓은 보건 분야라는 이유보다, 대상기관의 상위·하위·소속 관계를
  더 강한 근거로 본다.
- 임베딩 순위는 recall 순서일 뿐 정답 순서가 아니다.
- 후보 중 하나만 반환하며 이유는 두 문장 이내로 쓴다.
JSON만 반환한다:
{"candidate_id":"정확한 ID","target_relation_type":"none",
"artifact_purpose_match":0,"domain_match":0,
"reason":"의미 관계 근거","confidence":0.0}"""

_PRIOR_SCOPE = """이번 단계는 과거 동일 법률 선례의 추계 범위 판정이다.
대상 사건과 실질적으로 같은 사건만 연결하고, 단지 법률명이 같다는 이유로 다른 조문을 연결하지 않는다."""


def system_instruction(prompt: str) -> str:
    """Return the task-specific Solar system instruction for one prompt."""
    if "추가 공공재정 비용사건" in prompt:
        task = _EVENTS
    elif "전담인력 HITL 값 선례의 단일 reranking" in prompt:
        task = _DEDICATED_STAFF_VALUE
    elif "계획·연구 선례의 소형 semantic reranking" in prompt:
        task = _RESEARCH_DIRECT
    elif "값 선례 후보군" in prompt:
        task = _ORG_VALUE
    elif "공공조직 신설·승격 비용추계 선례" in prompt:
        task = _ORG_STRUCTURE
    elif "빈 변수값을 채울 공식 선례" in prompt:
        task = _VARIABLE
    elif "계획·연구 비용 선례의 의미 적합성" in prompt:
        task = _RESEARCH
    elif "비용추계 선례를 선택하는 reranker" in prompt:
        task = _FORMULA
    elif "추계 가능 범위" in prompt:
        task = _PRIOR_SCOPE
    else:
        task = ""
    return f"{_BASE}\n{task}".strip()


def dedicated_staff_value_prompt(
    *,
    target_events: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> str | None:
    """Build a compact direct-rerank prompt only for dedicated-staff events."""
    target_blob = _compact(
        " ".join(
            str(event.get(field) or "")
            for event in target_events
            for field in ("action", "object", "explanation")
        )
    )
    if not (
        re.search(r"담당관|전담인력|전문인력|전담담당자", target_blob)
        and re.search(r"지정|임명|배치|채용|둔다", target_blob)
    ):
        return None

    compact_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        components = candidate.get("components")
        compact_candidates.append(
            {
                "bill_no": candidate.get("bill_no"),
                "bill_name": candidate.get("bill_name"),
                "precedent_context": str(
                    candidate.get("precedent_context") or ""
                )[:1_200],
                "components": components if isinstance(components, list) else [],
            }
        )
    body = {
        "target_events": target_events,
        "candidates": compact_candidates,
    }
    return (
        "전담인력 HITL 값 선례의 단일 reranking이다.\n"
        "대상 정답 금액과 후보 금액은 제공되지 않는다.\n"
        "입력 후보 중 의미적으로 가장 가까운 한 건만 고른다.\n"
        + json.dumps(body, ensure_ascii=False)
    )


def research_direct_prompt(
    *,
    event: dict[str, Any],
    source_text: str,
    candidates: list[dict[str, Any]],
    limit: int = 8,
) -> tuple[str, list[dict[str, Any]]]:
    """Build a compact second-stage rerank window for Solar Pro2."""
    window = candidates[:limit]
    body = {
        "event": event,
        "source_text": source_text,
        "candidates": window,
    }
    prompt = (
        "계획·연구 선례의 소형 semantic reranking이다.\n"
        "후보 금액은 제공되지 않는다. 대상기관·대상집단의 직접 관계를 "
        "우선하고, 계획·조사 산출물의 목적과 세부 도메인을 각각 평가해 "
        "의미적으로 가장 가까운 하나만 선택한다.\n"
        "target_relation_type은 same_named_entity, legal_parent_child, "
        "same_entity_class, functional_association, broad_domain, none 중 "
        "하나다. 기관이 같은 부처의 정책에 참여하는 것만으로 직접 관계를 "
        "주지 마라.\n"
        "artifact_purpose_match와 domain_match는 0~3 정수다. "
        "confidence는 0~1이다.\n"
        "JSON만 반환한다: "
        '{"candidate_id":"정확한 ID","target_relation_type":"none",'
        '"artifact_purpose_match":0,"domain_match":0,'
        '"reason":"짧은 근거","confidence":0.0}\n'
        + json.dumps(body, ensure_ascii=False)
    )
    return prompt, window


def _compact(value: str) -> str:
    normalised = unicodedata.normalize("NFKC", value or "")
    normalised = re.sub(r"[-―–—]\s*\d+\s*[-―–—]", "", normalised)
    return re.sub(r"[^0-9A-Za-z가-힣]", "", normalised)


def _segment_texts(prompt: str) -> dict[str, str]:
    """Read the exact segment blocks already present in the detection prompt."""
    matches = list(
        re.finditer(
            r"(?m)^\[(S\d+)\s*\|[^\]]*\]\n",
            prompt,
        )
    )
    texts: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(prompt)
        texts[match.group(1)] = prompt[match.end():end].strip()
    return texts


def _event_source(
    event: dict[str, Any],
    segments: dict[str, str],
) -> str:
    return " ".join(
        segments.get(str(segment_id), "")
        for segment_id in event.get("segment_ids") or []
    )


def _is_ordinary_policy_committee_definition(
    event: dict[str, Any],
    segments: dict[str, str],
    all_source: str,
) -> bool:
    """Distinguish an advisory body from an independently staffed agency.

    Solar sometimes treats any statutory ``...위원회를 둔다`` clause as an
    organization creation.  Korean statutes expose a stronger legal-form
    signal: a body placed *under* an existing ministry to deliberate or advise
    is an ordinary committee, while an independent agency has organization,
    staff, or secretariat provisions.  This rule uses those legal attributes,
    not a bill name or an answer amount.
    """
    if event.get("event_type") not in {
        "organization_change",
        "committee_operation",
    }:
        return False
    target = _compact(str(event.get("object") or ""))
    if not re.search(r"(?:위원회|심의회|협의회|자문회)$", target):
        return False

    source = _compact(_event_source(event, segments))
    placed_under_existing_body = bool(
        re.search(
            r"(?:소속|산하)으로.{0,60}"
            r"(?:위원회|심의회|협의회|자문회).{0,20}"
            r"(?:둔다|설치한다)",
            source,
        )
    )
    deliberative_purpose = bool(re.search(r"심의|자문|협의|조정", source))
    independent_organization = bool(
        re.search(
            r"중앙행정기관으로|독립된국가기관|법인으로"
            r"|(?:위원회|심의회|협의회|자문회)(?:에|의)"
            r"(?:사무처|사무국|정원|소속공무원|직원)",
            all_source,
        )
    )
    return (
        placed_under_existing_body
        and deliberative_purpose
        and not independent_organization
    )


def _is_committee_supporting_event(
    event: dict[str, Any],
    segments: dict[str, str],
) -> bool:
    """Return true for a clause that belongs to the nearest named committee."""
    event_type = str(event.get("event_type") or "")
    target = _compact(str(event.get("object") or ""))
    source = _compact(_event_source(event, segments))
    if event_type == "committee_operation":
        return bool(
            target.startswith("위원회")
            or target in {"위원장및부위원장", "소위원회"}
            or re.search(r"위원회.{0,30}(?:구성|회의|소집)", source)
        )
    return bool(
        event_type == "subsidy"
        and re.search(r"위원회.{0,40}(?:수당|여비)", source)
    )


def _merge_ordinary_committee_events(
    events: list[dict[str, Any]],
    segments: dict[str, str],
) -> list[dict[str, Any]]:
    """Enforce one fiscal event for one ordinary policy committee."""
    segment_order = {segment_id: index for index, segment_id in enumerate(segments)}
    all_source = _compact(" ".join(segments.values()))

    def first_order(event: dict[str, Any]) -> int:
        positions = [
            segment_order[str(segment_id)]
            for segment_id in event.get("segment_ids") or []
            if str(segment_id) in segment_order
        ]
        return min(positions) if positions else len(segment_order)

    base_indexes = [
        index
        for index, event in enumerate(events)
        if _is_ordinary_policy_committee_definition(
            event,
            segments,
            all_source,
        )
    ]
    if not base_indexes:
        return events

    consumed: set[int] = set()
    ordered_bases = sorted(base_indexes, key=lambda index: first_order(events[index]))
    for position, base_index in enumerate(ordered_bases):
        base = events[base_index]
        lower = first_order(base)
        upper = (
            first_order(events[ordered_bases[position + 1]])
            if position + 1 < len(ordered_bases)
            else len(segment_order)
        )
        base["event_type"] = "committee_operation"
        base["cost_mechanism"] = "internal_administration"
        base["action"] = "설치 및 운영"

        for candidate_index, candidate in enumerate(events):
            if candidate_index == base_index or candidate_index in base_indexes:
                continue
            candidate_order = first_order(candidate)
            if not (lower < candidate_order < upper):
                continue
            if not _is_committee_supporting_event(candidate, segments):
                continue
            for field in ("segment_ids", "article_refs", "quotes"):
                base[field] = list(
                    dict.fromkeys(
                        [
                            *(base.get(field) or []),
                            *(candidate.get(field) or []),
                        ]
                    )
                )
            consumed.add(candidate_index)
    return [
        event
        for index, event in enumerate(events)
        if index not in consumed
    ]


def _normalise_event_payload(prompt: str, payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    if isinstance(payload.get("events"), list):
        events = payload["events"]
    elif payload.get("event_type") and payload.get("segment_ids"):
        # Solar occasionally follows the event schema but omits the outer
        # collection even though the user prompt requires it.
        events = [payload]
    else:
        return payload

    segments = _segment_texts(prompt)
    normalised_events: list[dict[str, Any]] = []
    for raw in events:
        if not isinstance(raw, dict):
            continue
        event = dict(raw)
        segment_ids = [
            str(value)
            for value in event.get("segment_ids") or []
            if str(value) in segments
        ]
        source = " ".join(segments[value] for value in segment_ids)
        compact_source = _compact(source)
        quotes = [
            str(value).strip()
            for value in event.get("quotes") or []
            if str(value).strip()
            and _compact(str(value)) in compact_source
        ]
        event["segment_ids"] = segment_ids
        event["quotes"] = quotes
        normalised_events.append(event)

    normalised_events = _merge_ordinary_committee_events(
        normalised_events,
        segments,
    )

    # Solar tends to turn every amended jurisdiction table into a separate
    # organization. Jurisdiction rows are supporting clauses, not additional
    # staffed institutions. Merge a row that names the newly established
    # institution into that institution's event, and drop standalone
    # jurisdiction-only rows.
    primary_organizations = [
        event
        for event in normalised_events
        if event.get("event_type") == "organization_change"
        and "관할구역" not in _compact(str(event.get("object") or ""))
    ]
    retained: list[dict[str, Any]] = []
    for event in normalised_events:
        if (
            event.get("event_type") != "organization_change"
            or "관할구역" not in _compact(str(event.get("object") or ""))
        ):
            retained.append(event)
            continue
        event_object = _compact(str(event.get("object") or "")).replace("관할구역", "")
        matching = next(
            (
                primary
                for primary in primary_organizations
                if _compact(str(primary.get("object") or "")) in event_object
                or event_object in _compact(str(primary.get("object") or ""))
            ),
            None,
        )
        if matching is None:
            continue
        matching["segment_ids"] = list(
            dict.fromkeys(
                [
                    *(matching.get("segment_ids") or []),
                    *(event.get("segment_ids") or []),
                ]
            )
        )
        matching["article_refs"] = list(
            dict.fromkeys(
                [
                    *(matching.get("article_refs") or []),
                    *(event.get("article_refs") or []),
                ]
            )
        )
        matching["quotes"] = list(
            dict.fromkeys(
                [
                    *(matching.get("quotes") or []),
                    *(event.get("quotes") or []),
                ]
            )
        )
    return {"events": retained}


def normalize_response(prompt: str, payload: object) -> object:
    """Repair provider-shape deviations without inventing evidence."""
    if "추가 공공재정 비용사건" in prompt:
        return _normalise_event_payload(prompt, payload)
    return payload


def use_unique_prequalified_organization_value(
    *,
    candidate_count: int,
    target_organization_form: str,
) -> bool:
    """Skip a redundant Solar judgment after deterministic compatibility gates.

    The common engine has already required a complete value case, an explicit
    staff denominator, lifecycle compatibility, and—where identifiable—the
    same statutory organization form.  Solar Pro2 has occasionally rejected
    the sole remaining legislative-committee case by confusing elected
    committee members with the separately supplied HITL staff denominator.
    With one prequalified case there is no ranking decision left for the LLM.

    Unknown organization forms remain model-reviewed because their hard gate
    is not specific enough to establish compatibility on its own.
    """
    return candidate_count == 1 and target_organization_form != "unknown"
