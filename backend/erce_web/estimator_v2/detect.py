from __future__ import annotations

import re
import unicodedata
from typing import Any

from ..analyzer_v2 import GEMINI_MODEL, LLM_PROFILE, gemini_json
from ..llm_profiles import normalize_response as normalize_profile_response
from .cache import get_or_create_json
from .types import AtomicEvent, EventType, Segment


PROMPT_VERSION = "atomic-events-v2"
ANNEX_PROMPT_VERSION = "atomic-events-v3"
CHUNK_VERSION = "article-boundary-v1"
STAFF_DESIGNATION_ROUTING_VERSION = "staff-designation-routing-v1"
# Solar Pro2 can reject a whole long-form statute before returning JSON.
# Keep each request comfortably below the provider context window.  This is
# measured on the exact prompt text, not on bill names or cost keywords.
MAX_EVENT_PROMPT_CHARS = 30_000
SCHEMA_RECOVERY_PROMPT_CHARS = 12_000
EMPTY_RECOVERY_PROMPT_CHARS = 6_000
_PARAGRAPH_MARKER_RE = re.compile(r"([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳])")
_REVISION_START_RE = re.compile(
    r"(?:일부|전부)\s*를?\s*다음\s*과\s*같이\s*개정\s*한다[.\u3002]?"
)
_ADDENDUM_START_RE = re.compile(r"(?m)^\s*부\s*칙(?:\s|$)")
_ANNEX_REF_RE = re.compile(
    r"(별\s*표|별\s*지)\s*(?:제\s*)?(\d+(?:\s*의\s*\d+)?)"
)
_ANNEX_CHANGE_RE = re.compile(
    r"(?:신설|삭제|개정|전부개정|일부개정|"
    r"(?:다음|별지)\s*과\s*같이\s*한다|"
    r"[\"“][^\"”]{1,120}[\"”]\s*(?:으)?로\s*한다)"
)
_MAIN_ARTICLE_HEADER_RE = re.compile(
    r"(?m)^[ \t]*("
    r"제\s*\d+\s*조(?:\s*의\s*\d+)?"
    r"\s*\([^)\n]{1,100}\)"
    r")"
)
_MAIN_ARTICLE_KEY_RE = re.compile(
    r"제\s*(\d+)\s*조(?:\s*의\s*(\d+))?"
)
_EXPLICIT_SUPPORT_OFFICE_RE = re.compile(
    r"사무(?:를|의)?처리.{0,80}"
    r"(사무처|사무국|사무기구|지원단)"
    r"(?:를|을)?둔다"
)
_ALLOWED_EVENT_TYPES = {item.value for item in EventType}
_ALLOWED_BEARERS = {"state", "local", "public_institution", "private", "unclear"}
_ALLOWED_OBLIGATIONS = {"mandatory", "discretionary", "declarative", "unclear"}
_ALLOWED_MECHANISMS = {
    "organization_change",
    "external_contract",
    "staffing",
    "transfer",
    "construction",
    "tax_reduction",
    "internal_administration",
    "unknown",
}
_ALLOWED_ADDITIONALITY = {
    "explicit_new_or_expanded",
    "possibly_incremental",
    "existing_or_unchanged",
    "unknown",
}


def _failure_recovery_limit(prompt_chars: int) -> int | None:
    """Return a smaller request limit after a provider-level failure.

    A failed large request is not evidence that the bill has no cost events.
    Retry the same article-bounded input at progressively smaller sizes, while
    still failing closed when even the smallest supported request fails.
    """
    if prompt_chars > SCHEMA_RECOVERY_PROMPT_CHARS:
        return SCHEMA_RECOVERY_PROMPT_CHARS
    if prompt_chars > EMPTY_RECOVERY_PROMPT_CHARS:
        return EMPTY_RECOVERY_PROMPT_CHARS
    return None


_DETECT_PROMPT = """당신은 법안의 '추가 공공재정 비용사건'을 구조화하는 분석가다.
아래 입력은 조문을 항 단위로 분리한 segment 목록이다.

목표:
- 산식이나 숫자를 만들지 말고, 비용 발생 행위를 원자적 사건으로 나눈다.
- 주체나 행위가 다르면 반드시 별도 사건으로 만든다.
- 예를 들어 중앙행정기관의 정기 계획 수립과 개별 기관의 연간 계획 제출은 별도 사건이다.
- 위원회 설치·구성·회의처럼 하나의 위원회 운영비를 설명하는 segment들은 한 사건으로 묶고
  supporting segment id를 함께 넣는다.
- 단순 목적·정의는 제외한다.
- 보고·제출·인가·등기·감사·평가·지도감독도 후보로는 낼 수 있지만 event_type은
  administrative로 분류한다. 이것들이 실제 추가재정소요인지는 후속 게이트가 판단한다.
- 공공기관·행정기관·법원·청·사무처 같은 조직의 신설·승격·분리·통합은
  organization_change 사건 하나로 만든다. 조문에 없는 인력·시설비를 미리 추측하여
  personnel과 facility_system으로 중복 생성하지 마라. 후속 조직 엔진이 비용항목을 분해한다.

각 사건 필드:
- segment_ids: 근거가 있는 segment id 목록
- article_refs: 근거 조문 번호 목록
- quotes: 입력에서 그대로 복사한 핵심 문장. 최소 1개. 문장을 새로 쓰지 마라.
- actor: 행위를 수행하는 주체
- action: 실제 행위
- object: 비용이 발생하는 실체 또는 대상
- bearer: 비용 부담 주체. state | local | public_institution | private | unclear
- event_type:
  organization_change | committee_operation | research_plan | personnel | subsidy |
  facility_system | tax_revenue | administrative | other
- obligation: mandatory | discretionary | declarative | unclear
- cost_mechanism:
  organization_change | external_contract | staffing | transfer | construction | tax_reduction |
  internal_administration | unknown
- additionality:
  explicit_new_or_expanded | possibly_incremental | existing_or_unchanged | unknown
- recurrence_text: 조문에 있는 "매년", "5년마다" 같은 표현. 없으면 빈 문자열
- explanation: 비용 가능성을 설명하는 한 문장

중요:
- 제정안도 기존 제도를 통합·재규정할 수 있으므로 모든 행위를 무조건 신규라고 하지 마라.
- 입력에 없는 숫자와 사실을 만들지 마라.
- JSON만 반환한다.

출력:
{"events":[{"segment_ids":["S001"],"article_refs":["제1조"],"quotes":["..."],
"actor":"...","action":"...","object":"...","bearer":"state",
"event_type":"research_plan","obligation":"mandatory",
"cost_mechanism":"external_contract","additionality":"possibly_incremental",
"recurrence_text":"5년마다","explanation":"..."}]}

segments:
"""

_ANNEX_GUIDANCE = """
추가 지침:
- 입력에 별표·별지의 신설·개정·삭제 segment가 있으면 조문과 똑같이 분석한다.
- 별표에서 조직, 정원, 급여표, 지원 대상 등이 바뀌면 그 변경 행위를
  비용사건 후보로 낸다.
"""


def _compact(value: str) -> str:
    # Assembly PDFs frequently insert page numbers in the middle of a word
    # (e.g. "따 - 14 - 른") and use visually equivalent punctuation.  Remove
    # layout noise before quote grounding; letters and digits still have to be
    # an exact substring, so this does not turn a paraphrase into evidence.
    normalised = unicodedata.normalize("NFKC", value or "")
    normalised = re.sub(r"[-―–—]\s*\d+\s*[-―–—]", "", normalised)
    return re.sub(r"[^0-9A-Za-z가-힣]", "", normalised)


def segment_articles(articles: list[dict[str, Any]]) -> list[Segment]:
    segments: list[Segment] = []
    sequence = 1
    for article in articles:
        article_ref = str(article.get("no") or "")
        text = re.sub(r"\s+", " ", str(article.get("text") or "")).strip()
        if not text:
            continue
        matches = list(_PARAGRAPH_MARKER_RE.finditer(text))
        blocks: list[str] = []
        if not matches:
            blocks = [text]
        else:
            prefix = text[: matches[0].start()].strip()
            for index, match in enumerate(matches):
                end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
                block = text[match.start():end].strip()
                if index == 0 and prefix:
                    block = f"{prefix} {block}"
                blocks.append(block)
        for block in blocks:
            segments.append(
                Segment(
                    id=f"S{sequence:03d}",
                    article_ref=article_ref,
                    text=block[:1800],
                    change_type=str(article.get("change_type") or ""),
                )
            )
            sequence += 1
    return segments


def _render_segments(segments: list[Segment]) -> str:
    return "\n".join(
        f"[{segment.id} | {segment.article_ref} | {segment.change_type}]\n"
        f"{segment.text}"
        for segment in segments
    )


def _chunk_segments(
    segments: list[Segment],
    *,
    max_prompt_chars: int = MAX_EVENT_PROMPT_CHARS,
    prompt_prefix_chars: int = len(_DETECT_PROMPT),
) -> list[list[Segment]]:
    """Split long statutes without cutting an article when avoidable.

    Chunking is a transport constraint only. Every segment appears exactly
    once and the original order is preserved. Consecutive paragraphs from one
    article stay together unless that single article itself exceeds the
    request budget.
    """
    budget = max(1, max_prompt_chars - prompt_prefix_chars)
    article_runs: list[list[Segment]] = []
    for segment in segments:
        if (
            article_runs
            and article_runs[-1][0].article_ref == segment.article_ref
        ):
            article_runs[-1].append(segment)
        else:
            article_runs.append([segment])

    chunks: list[list[Segment]] = []
    current: list[Segment] = []
    current_size = 0
    for run in article_runs:
        run_size = len(_render_segments(run))
        if run_size > budget:
            if current:
                chunks.append(current)
                current = []
                current_size = 0
            for segment in run:
                segment_size = len(_render_segments([segment]))
                if current and current_size + 1 + segment_size > budget:
                    chunks.append(current)
                    current = []
                    current_size = 0
                current.append(segment)
                current_size += segment_size + int(current_size > 0)
            continue
        if current and current_size + 1 + run_size > budget:
            chunks.append(current)
            current = []
            current_size = 0
        current.extend(run)
        current_size += run_size + int(current_size > 0)
    if current:
        chunks.append(current)
    return chunks


def _needs_schema_recovery(
    payload: Any,
    chunk: list[Segment],
    *,
    prompt_prefix_chars: int,
) -> bool:
    """Return whether a large response collapsed outside the required schema.

    A top-level event is a recoverable provider deviation for small inputs.
    A formally valid ``events`` array can fail in the same way when its only
    event claims dozens of segments across many articles.  Both shapes are
    unsafe for a large request because the model may have merged unrelated
    fiscal events or silently ignored the rest. Rechunk based only on response
    cardinality and request size—never on bill words, amounts, or the answer.
    """
    is_top_level_event = (
        isinstance(payload, dict)
        and not isinstance(payload.get("events"), list)
        and bool(payload.get("event_type"))
        and bool(payload.get("segment_ids"))
    )
    rows = payload.get("events") if isinstance(payload, dict) else None
    is_collapsed_collection = False
    if isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict):
        segment_map = {segment.id: segment for segment in chunk}
        referenced_ids = {
            str(value)
            for value in rows[0].get("segment_ids") or []
            if str(value) in segment_map
        }
        referenced_articles = {
            segment_map[segment_id].article_ref
            for segment_id in referenced_ids
        }
        is_collapsed_collection = (
            len(referenced_ids) >= 32
            and len(referenced_articles) >= 8
        )
    if not (is_top_level_event or is_collapsed_collection):
        return False
    prompt_chars = prompt_prefix_chars + len(_render_segments(chunk))
    return prompt_chars > EMPTY_RECOVERY_PROMPT_CHARS


def _needs_empty_recovery(
    payload: Any,
    chunk: list[Segment],
    *,
    prompt_prefix_chars: int,
) -> bool:
    """Retry a suspiciously broad, empty extraction at finer granularity.

    Empty is a valid result for a small group of articles. On a broad request
    it is not enough evidence that every article was considered. The retry is
    triggered only by response cardinality and transport size.
    """
    is_empty_collection = (
        isinstance(payload, dict)
        and isinstance(payload.get("events"), list)
        and not payload["events"]
    )
    if not is_empty_collection:
        return False
    prompt_chars = prompt_prefix_chars + len(_render_segments(chunk))
    return prompt_chars > EMPTY_RECOVERY_PROMPT_CHARS


def extract_annex_revision_articles(text: str) -> list[dict[str, str]]:
    """Extract changed annex/table blocks as grounded pseudo-articles.

    Some amendment bills create an organization or change headcount only in
    ``별표``/``별지``.  The ordinary article splitter intentionally ignores
    appendices, so those bills otherwise reach the LLM with no cost-bearing
    segment at all.  This parser reads only the operative revision body—not
    the proposal summary—and only blocks containing an amendment verb.
    """
    revision = _REVISION_START_RE.search(text or "")
    if not revision:
        return []
    body = (text or "")[revision.end():]
    addendum = _ADDENDUM_START_RE.search(body)
    if addendum:
        body = body[:addendum.start()]

    matches = list(_ANNEX_REF_RE.finditer(body))
    articles: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        block = re.sub(r"\s+", " ", body[match.start():end]).strip()
        if not block or not _ANNEX_CHANGE_RE.search(block[:500]):
            continue
        kind = re.sub(r"\s+", "", match.group(1))
        number = re.sub(r"\s+", "", match.group(2))
        label = f"{kind}{number}"
        compact = _compact(block)
        key = (label, compact)
        if key in seen:
            continue
        seen.add(key)
        change_type = (
            "신설"
            if "신설" in block
            else "삭제"
            if "삭제" in block and "신설" not in block
            else "개정"
        )
        articles.append(
            {
                "no": label,
                "text": block[:1500],
                "change_type": change_type,
                "source": "annex_revision",
            }
        )
    return articles


def extract_revision_body_articles(text: str) -> list[dict[str, str]]:
    """Recover titled articles skipped inside one batch amendment block.

    Assembly amendment PDFs sometimes introduce a whole range with one
    instruction (for example, ``제21조부터 제36조까지를 신설한다``).  The
    generic splitter can then keep the first article but skip later article
    headings because those headings do not repeat ``다음과 같이 신설한다``.
    Scan only the operative revision body and only line-leading, titled
    ``제N조(제목)`` headings.  This avoids proposal summaries and bare
    cross-references such as ``제9조를 준용한다``.
    """
    revision = _REVISION_START_RE.search(text or "")
    if not revision:
        return []
    body = (text or "")[revision.end():]
    addendum = _ADDENDUM_START_RE.search(body)
    if addendum:
        body = body[:addendum.start()]

    matches = list(_MAIN_ARTICLE_HEADER_RE.finditer(body))
    articles: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        block = re.sub(r"\s+", " ", body[match.start():end]).strip()
        if len(_compact(block)) < 10:
            continue
        label = re.sub(r"\s+", "", match.group(1))
        key = (label, _compact(block))
        if key in seen:
            continue
        seen.add(key)
        articles.append(
            {
                "no": label,
                "text": block[:4_000],
                "change_type": "개정본문",
                "source": "revision_body",
            }
        )
    return articles


def _main_article_key(article: dict[str, Any]) -> tuple[int, int] | None:
    match = _MAIN_ARTICLE_KEY_RE.search(str(article.get("no") or ""))
    if not match:
        return None
    return int(match.group(1)), int(match.group(2) or 0)


def merge_revision_body_articles(
    articles: list[dict[str, Any]],
    recovered_articles: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Add genuinely missing operative articles without duplicating good parses."""
    recovered_by_key = {
        key: article
        for article in recovered_articles
        if (key := _main_article_key(article)) is not None
    }
    if not recovered_by_key:
        return articles

    merged: list[dict[str, Any]] = []
    consumed: set[tuple[int, int]] = set()
    for article in articles:
        key = _main_article_key(article)
        recovered = recovered_by_key.get(key) if key is not None else None
        if recovered is None:
            merged.append(article)
            continue
        # Keep the richer operative block while preserving an existing,
        # specific change type when the generic parser already found it.
        existing_text = str(article.get("text") or "")
        recovered_text = str(recovered.get("text") or "")
        if len(_compact(recovered_text)) > len(_compact(existing_text)):
            merged.append(
                {
                    **article,
                    **recovered,
                    "change_type": (
                        str(article.get("change_type") or "")
                        or str(recovered.get("change_type") or "")
                    ),
                }
            )
        else:
            merged.append(article)
        consumed.add(key)

    merged.extend(
        article
        for key, article in recovered_by_key.items()
        if key not in consumed
    )
    return merged


def merge_annex_revision_articles(
    articles: list[dict[str, Any]],
    annex_articles: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Merge duplicate appendix parses while preserving amendment provenance.

    The generic article splitter can already emit a ``별표`` block. Dropping
    the separately extracted annex record in that case also drops its
    ``source=annex_revision`` marker, so the detector silently falls back to
    the ordinary-article prompt. Prefer annex metadata for an exact duplicate
    and append only genuinely new blocks.
    """
    annex_by_key = {
        (
            str(article.get("no") or ""),
            str(article.get("text") or ""),
        ): article
        for article in annex_articles
    }
    merged: list[dict[str, Any]] = []
    consumed: set[tuple[str, str]] = set()
    for article in articles:
        key = (
            str(article.get("no") or ""),
            str(article.get("text") or ""),
        )
        annex = annex_by_key.get(key)
        if annex is None:
            merged.append(article)
            continue
        merged.append({**article, **annex})
        consumed.add(key)
    merged.extend(
        article
        for key, article in annex_by_key.items()
        if key not in consumed
    )
    return merged


def _event_is_grounded(row: dict[str, Any], segment_map: dict[str, Segment]) -> bool:
    segment_ids = [str(value) for value in row.get("segment_ids") or []]
    source = " ".join(
        segment_map[segment_id].text
        for segment_id in segment_ids
        if segment_id in segment_map
    )
    if not source:
        return False
    compact_source = _compact(source)
    quotes = [str(value).strip() for value in row.get("quotes") or [] if str(value).strip()]
    return bool(quotes) and all(_compact(quote) in compact_source for quote in quotes)


def _normalise_staff_designation_events(
    events: list[AtomicEvent],
) -> list[AtomicEvent]:
    """Correct a role-designation event that the LLM labelled as a committee.

    A paragraph can discuss governance work while its fiscal trigger is a
    person being designated from the institution's existing staff.  Such an
    event must enter the organization/staffing channel; otherwise a generic
    meeting-allowance precedent can be selected.  Require both a role name and
    source-side designation language so genuine committee operations remain in
    the committee channel.
    """
    role_pattern = re.compile(r"담당관|전담인력|전문인력|전담담당자")
    designation_pattern = re.compile(
        r"소속\s*직원.{0,100}(?:지정|임명|배치|채용)|"
        r"(?:담당관|전담인력|전문인력).{0,70}(?:지정|임명|배치|채용)"
    )
    for event in events:
        if event.event_type != EventType.COMMITTEE.value:
            continue
        object_text = _compact(event.object)
        source_text = _compact(" ".join(event.quotes))
        if not role_pattern.search(object_text) or not designation_pattern.search(
            source_text
        ):
            continue
        event.event_type = EventType.PERSONNEL.value
        event.cost_mechanism = "staffing"
        event.explanation = (
            f"{event.explanation} 담당관·전담인력 지정 사건으로 조직·인력 비용 채널에 라우팅."
        ).strip()
    return events


def _canonical_key(event: AtomicEvent) -> tuple[str, str, str, str]:
    action_key = _compact(event.action) if event.event_type == EventType.ADMINISTRATIVE.value else ""
    return (
        event.event_type,
        _compact(event.actor),
        _compact(event.object),
        action_key,
    )


_GENERIC_ORGANIZATION_OBJECTS = {
    "기관",
    "위원회",
    "센터",
    "조직",
    "법원",
    "지방법원",
    "고등법원",
    "지원",
}


def _same_named_annex_organization(
    left: AtomicEvent,
    right: AtomicEvent,
    segment_map: dict[str, Segment],
) -> bool:
    """Detect one organization repeated across several amended annex tables.

    Court jurisdiction, office location and organization tables can each add
    the same named body.  A model may emit one event per table even though the
    fiscal event is one creation or promotion.  Merge only grounded
    organization events whose evidence is entirely in amended annexes and
    whose specific organization name is contained in the other object.  This
    does not use a similarity score or a bill-specific name.
    """
    if (
        left.event_type != EventType.ORGANIZATION.value
        or right.event_type != EventType.ORGANIZATION.value
        or not left.grounded
        or not right.grounded
    ):
        return False
    segment_ids = [*left.segment_ids, *right.segment_ids]
    if not segment_ids or any(
        not segment_map.get(segment_id)
        or not segment_map[segment_id].article_ref.startswith(("별표", "별지"))
        for segment_id in segment_ids
    ):
        return False
    left_object = _compact(left.object)
    right_object = _compact(right.object)
    shorter, longer = sorted(
        (left_object, right_object),
        key=lambda value: (len(value), value),
    )
    return (
        len(shorter) >= 5
        and shorter not in _GENERIC_ORGANIZATION_OBJECTS
        and shorter in longer
    )


def _organization_event_priority(event: AtomicEvent) -> tuple[int, int, int]:
    action = _compact(event.action)
    operative_action = bool(
        re.search(r"신설|설치|승격|폐지|삭제|분리|통합", action)
    )
    return (
        int(event.cost_mechanism == "organization_change"),
        int(operative_action),
        -len(_compact(event.object)),
    )


def _merge_related_annex_organization_events(
    events: list[AtomicEvent],
    segment_map: dict[str, Segment],
) -> list[AtomicEvent]:
    result: list[AtomicEvent] = []
    for event in events:
        match_index = next(
            (
                index
                for index, current in enumerate(result)
                if _same_named_annex_organization(
                    current,
                    event,
                    segment_map,
                )
            ),
            None,
        )
        if match_index is None:
            result.append(event)
            continue
        current = result[match_index]
        primary, secondary = sorted(
            (current, event),
            key=_organization_event_priority,
            reverse=True,
        )
        primary.segment_ids = list(
            dict.fromkeys([*primary.segment_ids, *secondary.segment_ids])
        )
        primary.article_refs = list(
            dict.fromkeys([*primary.article_refs, *secondary.article_refs])
        )
        primary.quotes = list(
            dict.fromkeys([*primary.quotes, *secondary.quotes])
        )
        primary.grounded = primary.grounded and secondary.grounded
        result[match_index] = primary
    return result


def _merge_events(
    events: list[AtomicEvent],
    segments: list[Segment],
) -> list[AtomicEvent]:
    segment_map = {segment.id: segment for segment in segments}
    merged: dict[tuple[str, str, str, str], AtomicEvent] = {}
    for event in events:
        key = _canonical_key(event)
        current = merged.get(key)
        if current is None:
            merged[key] = event
            continue
        current.segment_ids = list(
            dict.fromkeys([*current.segment_ids, *event.segment_ids])
        )
        current.article_refs = list(
            dict.fromkeys([*current.article_refs, *event.article_refs])
        )
        current.quotes = list(
            dict.fromkeys([*current.quotes, *event.quotes])
        )
        current.grounded = current.grounded and event.grounded
    result = _merge_related_annex_organization_events(
        list(merged.values()),
        segment_map,
    )
    for index, event in enumerate(result, 1):
        event.id = f"E{index:03d}"
    return result


def _parse_events(payload: Any, segments: list[Segment]) -> list[AtomicEvent]:
    rows = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    segment_map = {segment.id: segment for segment in segments}
    parsed: list[AtomicEvent] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        segment_ids = [
            str(value)
            for value in row.get("segment_ids") or []
            if str(value) in segment_map
        ]
        if not segment_ids:
            continue
        event_type = str(row.get("event_type") or EventType.OTHER.value)
        if event_type not in _ALLOWED_EVENT_TYPES:
            event_type = EventType.OTHER.value
        bearer = str(row.get("bearer") or "unclear")
        if bearer not in _ALLOWED_BEARERS:
            bearer = "unclear"
        obligation = str(row.get("obligation") or "unclear")
        if obligation not in _ALLOWED_OBLIGATIONS:
            obligation = "unclear"
        mechanism = str(row.get("cost_mechanism") or "unknown")
        if mechanism not in _ALLOWED_MECHANISMS:
            mechanism = "unknown"
        additionality = str(row.get("additionality") or "unknown")
        if additionality not in _ALLOWED_ADDITIONALITY:
            additionality = "unknown"
        # A statutory fund is an account/transfer mechanism, not a staffed
        # organization merely because the clause says it is "installed".
        # Preserve a genuine fund office when the same grounded passage names
        # staff or an organizational unit; otherwise route the event to the
        # evidence-required generic channel instead of inventing payroll.
        fund_context = _compact(
            " ".join(
                [
                    str(row.get("object") or ""),
                    str(row.get("action") or ""),
                    str(row.get("explanation") or ""),
                    *[str(value) for value in row.get("quotes") or []],
                    *[segment_map[value].text for value in segment_ids],
                ]
            )
        )
        if (
            event_type == EventType.ORGANIZATION.value
            and "기금" in fund_context
            and not re.search(
                r"사무처(?!리)|사무국|지원단|전담조직|전담부서|센터|"
                r"기관(?:을|를)(?:신설|설치)|"
                r"직원|인력|정원|공무원|채용|증원",
                fund_context,
            )
        ):
            event_type = EventType.OTHER.value
            mechanism = "transfer"
        article_refs = [
            str(value)
            for value in row.get("article_refs") or []
            if str(value).strip()
        ] or list(dict.fromkeys(segment_map[value].article_ref for value in segment_ids))
        parsed.append(
            AtomicEvent(
                id=f"E{index + 1:03d}",
                segment_ids=segment_ids,
                article_refs=article_refs,
                quotes=[
                    str(value).strip()
                    for value in row.get("quotes") or []
                    if str(value).strip()
                ],
                actor=str(row.get("actor") or "").strip(),
                action=str(row.get("action") or "").strip(),
                object=str(row.get("object") or "").strip(),
                bearer=bearer,
                event_type=event_type,
                obligation=obligation,
                cost_mechanism=mechanism,
                additionality=additionality,
                recurrence_text=str(row.get("recurrence_text") or "").strip(),
                explanation=str(row.get("explanation") or "").strip(),
                grounded=_event_is_grounded(row, segment_map),
            )
        )

    return _merge_events(parsed, segments)


def _augment_explicit_support_office_events(
    events: list[AtomicEvent],
    segments: list[Segment],
) -> list[AtomicEvent]:
    """Recover a separately costed office hidden inside a committee event.

    Models often group every supporting paragraph into one committee event.
    A statutory office is different: its staff costs need their own scale and
    must not be mistaken for committee-member allowances.  Add an event only
    when the source segment explicitly says that an office is established and
    no organization event already covers that segment.
    """
    result = list(events)
    for segment in segments:
        compact = _compact(segment.text)
        match = _EXPLICIT_SUPPORT_OFFICE_RE.search(compact)
        if not match:
            continue
        if any(
            event.event_type == EventType.ORGANIZATION.value
            and segment.id in event.segment_ids
            for event in result
        ):
            continue
        committee = next(
            (
                event
                for event in result
                if event.event_type == EventType.COMMITTEE.value
                and segment.id in event.segment_ids
            ),
            None,
        )
        owner_match = re.search(
            r"([가-힣A-Za-z0-9ㆍ·]{2,50}위원회)의?사무",
            compact,
        )
        owner = (
            committee.object
            if committee is not None
            else owner_match.group(1)
            if owner_match
            else "위원회"
        )
        office = match.group(1)
        result.append(
            AtomicEvent(
                id="",
                segment_ids=[segment.id],
                article_refs=[segment.article_ref],
                quotes=[segment.text],
                actor=owner,
                action=f"{office} 설치",
                object=f"{owner} {office}",
                bearer=committee.bearer if committee is not None else "unclear",
                event_type=EventType.ORGANIZATION.value,
                obligation="mandatory",
                cost_mechanism="organization_change",
                additionality="explicit_new_or_expanded",
                recurrence_text="",
                explanation=(
                    f"위원회 운영과 구분되는 {office}의 명시적 설치 조문"
                ),
                grounded=True,
            )
        )
    for index, event in enumerate(result, 1):
        event.id = f"E{index:03d}"
    return result


def detect_atomic_events(
    articles: list[dict[str, Any]],
    *,
    refresh: bool = False,
) -> tuple[list[AtomicEvent], list[Segment], bool, str]:
    segments = segment_articles(articles)
    has_annex_revision = any(
        str(article.get("source") or "") == "annex_revision"
        for article in articles
    )
    active_prompt_version = (
        ANNEX_PROMPT_VERSION if has_annex_revision else PROMPT_VERSION
    )
    prompt_prefix = _DETECT_PROMPT + (
        _ANNEX_GUIDANCE if has_annex_revision else ""
    )
    chunks = _chunk_segments(
        segments,
        prompt_prefix_chars=len(prompt_prefix),
    )
    chunked = len(chunks) > 1
    if chunked:
        active_prompt_version = f"{active_prompt_version}+{CHUNK_VERSION}"

    parsed_events: list[AtomicEvent] = []
    cache_hits: list[bool] = []

    def detect_chunk(
        chunk: list[Segment],
        *,
        chunk_index: int,
        chunk_count: int,
        chunk_path: tuple[int, ...] = (),
    ) -> None:
        segment_payload = [
            {
                "id": segment.id,
                "article_ref": segment.article_ref,
                "change_type": segment.change_type,
                "text": segment.text,
            }
            for segment in chunk
        ]
        prompt = prompt_prefix + _render_segments(chunk)
        key_payload: dict[str, Any] = {
            "prompt_version": active_prompt_version,
            "model": GEMINI_MODEL,
            "segments": segment_payload,
        }
        if chunked:
            key_payload.update(
                {
                    "chunk_index": chunk_index,
                    "chunk_count": chunk_count,
                }
            )
        if chunk_path:
            key_payload.update(
                {
                    "schema_recovery": "response-shape-v1",
                    "chunk_path": list(chunk_path),
                }
            )
        payload, cache_hit = get_or_create_json(
            "llm_events",
            key_payload,
            lambda prompt=prompt: gemini_json(prompt, temperature=0.0),
            refresh=refresh,
        )
        if payload is None:
            recovery_limit = _failure_recovery_limit(len(prompt))
            if recovery_limit is not None:
                subchunks = _chunk_segments(
                    chunk,
                    max_prompt_chars=recovery_limit,
                    prompt_prefix_chars=len(prompt_prefix),
                )
                if len(subchunks) > 1:
                    for sub_index, subchunk in enumerate(subchunks):
                        detect_chunk(
                            subchunk,
                            chunk_index=chunk_index,
                            chunk_count=chunk_count,
                            chunk_path=(*chunk_path, sub_index),
                        )
                    return
            raise RuntimeError(
                "LLM 비용사건 추출 실패"
                f" ({chunk_index + 1}/{chunk_count} 묶음). "
                "부분 결과를 0원으로 처리하지 않습니다."
            )
        if _needs_schema_recovery(
            payload,
            chunk,
            prompt_prefix_chars=len(prompt_prefix),
        ):
            prompt_chars = len(prompt_prefix) + len(_render_segments(chunk))
            recovery_limit = (
                SCHEMA_RECOVERY_PROMPT_CHARS
                if prompt_chars > SCHEMA_RECOVERY_PROMPT_CHARS * 2
                else EMPTY_RECOVERY_PROMPT_CHARS
            )
            subchunks = _chunk_segments(
                chunk,
                max_prompt_chars=recovery_limit,
                prompt_prefix_chars=len(prompt_prefix),
            )
            if len(subchunks) > 1:
                # The rejected parent cache remains useful as evidence that
                # this exact request shape must be subdivided. Only child
                # requests spend additional API calls.
                for sub_index, subchunk in enumerate(subchunks):
                    detect_chunk(
                        subchunk,
                        chunk_index=chunk_index,
                        chunk_count=chunk_count,
                        chunk_path=(*chunk_path, sub_index),
                    )
                return
        if _needs_empty_recovery(
            payload,
            chunk,
            prompt_prefix_chars=len(prompt_prefix),
        ):
            subchunks = _chunk_segments(
                chunk,
                max_prompt_chars=EMPTY_RECOVERY_PROMPT_CHARS,
                prompt_prefix_chars=len(prompt_prefix),
            )
            if len(subchunks) > 1:
                for sub_index, subchunk in enumerate(subchunks):
                    detect_chunk(
                        subchunk,
                        chunk_index=chunk_index,
                        chunk_count=chunk_count,
                        chunk_path=(*chunk_path, sub_index),
                    )
                return
        # Provider profiles also normalise cached responses. This keeps the
        # raw model cache reusable when only deterministic adapter rules
        # improve.
        payload = normalize_profile_response(LLM_PROFILE, prompt, payload)
        parsed_events.extend(_parse_events(payload, chunk))
        cache_hits.append(cache_hit)

    for chunk_index, chunk in enumerate(chunks):
        detect_chunk(
            chunk,
            chunk_index=chunk_index,
            chunk_count=len(chunks),
        )

    events = _merge_events(parsed_events, segments)
    events = _normalise_staff_designation_events(events)
    return (
        _augment_explicit_support_office_events(
            events,
            segments,
        ),
        segments,
        bool(cache_hits) and all(cache_hits),
        f"{active_prompt_version}+{STAFF_DESIGNATION_ROUTING_VERSION}",
    )
