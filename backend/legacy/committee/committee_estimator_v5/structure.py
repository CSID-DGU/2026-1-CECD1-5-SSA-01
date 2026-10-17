from __future__ import annotations

from dataclasses import replace
import re
from typing import Any

from backend.committee_estimator_v3.pipeline import _actor
from backend.legacy.committee.committee_estimator_v4.structure import (
    extract_committee_nodes,
    select_formula_plan as select_v4_formula_plan,
)

from .types import CommitteeEventV5, ComponentFormulaPlan, CostComponent


_BODY = r"(?:위원회|심의회|협의회|참여회의)"
_NAME = rf"([가-힣A-Za-z0-9ㆍ·]{{2,80}}?{_BODY})"
_CREATE = r"(?:를|을)?(?:둔다|두어야한다|설치한다|설치하여야한다|구성한다|구성하여야한다|둘수있다)"
_SUBORDINATE = ("실무위원회", "분과위원회", "소위원회", "전문위원회", "실무협의회")
_SUPPORT = ("실무지원단", "지원단", "사무국", "사무처", "사무기구")
_GENERIC_GOVERNANCE_TITLES = {
    "위원회의기능", "위원회의구성", "위원회의구성등", "위원장", "위원장의직무",
    "회의", "간사", "수당", "수당등", "운영세칙", "관계기관등에대한협조요청",
    *_SUBORDINATE,
}
_MEMBERSHIP_CHANGE = re.compile(
    r"(?:위원|위원장|부위원장).{0,100}(?:증원|확대|개편)|"
    r"(?:증원|확대|개편).{0,100}(?:위원|위원장|부위원장)|"
    r"“[^”]{0,80}\d+(?:명|인)[^”]{0,80}”을?“[^”]{0,80}\d+(?:명|인)"
)
_EVENT_DRIVEN = re.compile(
    r"(?:선출|지명|추천|임명).{0,30}(?:때마다|할때마다)|"
    r"(?:때마다|할때마다).{0,30}(?:구성|소집|개최)"
)
_STANDING_STAFF = re.compile(
    # `국회 소관 상임위원회`는 국회의 상설 위원회 명칭이지 대상 기구의
    # 상임위원·상근인력 근거가 아니다. `상임위원회`의 `위원`을 잡지 않는다.
    r"상임(?:위원(?!회)|으로|인위원(?!회))|상근위원|정무직공무원|별도정원|"
    r"(?:사무국|사무처|사무기구).{0,50}(?:직원|정원|인력)"
)
_STANDING_MEMBER = re.compile(
    r"(?:위원장|부위원장|위원)[^.。]{0,100}상임(?:으로|인위원(?!회)|위원(?!회))|"
    r"상임위원(?!회)[^.。]{0,80}(?:둔다|임명|구성)"
)
_SUPPORT_STAFF = re.compile(
    r"전문위원(?!회)|(?:사무국|사무처|사무기구|지원단).{0,80}(?:직원|정원|인력)"
)
_CONTINUOUS_CASEWORK = re.compile(
    r"고충처리|고충민원|옴부즈만|직권조사|민원조사|시정권고"
)


def _compact(value: str) -> str:
    value = re.sub(r"\s+", "", value or "")
    return re.sub(r"-\d+-", "", value)


def _title(article: dict[str, Any]) -> str:
    match = re.search(r"\(([^()]*)\)", str(article.get("no") or ""))
    return _compact(match.group(1) if match else "")


def _same_name(left: str, right: str) -> bool:
    left = _compact(left)
    right = _compact(right)
    return bool(left and right and (left in right or right in left))


def _extended_context(
    articles: list[dict[str, Any]],
    definition_index: int,
    base_refs: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Include detailed subordinate governance without crossing a new root.

    v4 deliberately stopped at every new body definition.  That protected
    boundaries but also dropped a following `분과위원회` article belonging to
    the current committee.  v5 treats a generic subordinate title as a
    relation and only stops at another independently named root.
    """
    selected = list(articles[definition_index:definition_index + len(base_refs)])
    cursor = definition_index + len(selected)
    while cursor < len(articles):
        article = articles[cursor]
        title = _title(article)
        if (
            title in _GENERIC_GOVERNANCE_TITLES
            or any(name in title for name in _SUPPORT)
        ):
            selected.append(article)
            cursor += 1
            continue
        break
    refs = tuple(str(value.get("no") or "") for value in selected)
    texts = tuple(str(value.get("text") or "") for value in selected)
    return refs, texts


def _subordinate_bodies(
    refs: tuple[str, ...],
    texts: tuple[str, ...],
    root_aliases: tuple[str, ...] = (),
) -> tuple[str, ...]:
    found: list[str] = []
    for ref, text in zip(refs, texts):
        compact = _compact(text)
        title = _title({"no": ref})
        for name in _SUBORDINATE:
            if _is_root_designation(name, root_aliases):
                continue
            if name not in compact:
                continue
            local = compact[compact.find(name):]
            detailed = (
                title == name
                and bool(re.search(
                    r"\d+(?:명|인).{0,50}(?:구성|위원)|"
                    r"위원회의?위원으로구성|"
                    r"위원장.{0,30}(?:맡는다|선출|임명|소집)|"
                    r"재적위원.{0,50}(?:개의|의결)",
                    local,
                ))
            )
            mandatory = bool(re.search(
                re.escape(name)
                + r"(?:\([^)]{0,100}\))?(?:를|을)?(?:둔다|설치한다)",
                compact,
            ))
            quantified = bool(re.search(r"\d+(?:명|인).{0,30}" + re.escape(name), compact))
            if mandatory or quantified or detailed:
                found.append(name)
    return tuple(dict.fromkeys(found))


def _optional_subordinate_bodies(
    refs: tuple[str, ...],
    texts: tuple[str, ...],
    required: tuple[str, ...],
    root_aliases: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Return explicitly authorized, but not necessarily operated, bodies.

    `둘 수 있다` is a real formula hypothesis, not a guaranteed cost.  Keeping
    it as an optional component preserves recall without silently charging it.
    """
    compact = _compact(" ".join(texts))
    found = [
        name for name in _SUBORDINATE
        if name not in required
        and not _is_root_designation(name, root_aliases)
        and re.search(
            re.escape(name)
            + r"(?:\([^)]{0,100}\))?(?:를|을)?(?:둘수있(?:다|고|으며)|설치할수있(?:다|고|으며))",
            compact,
        )
    ]
    return tuple(dict.fromkeys(found))


def _is_root_designation(name: str, root_aliases: tuple[str, ...]) -> bool:
    """Whether a generic body suffix is the root body's own legal name."""
    target = _compact(name)
    return any(
        (alias_compact == target)
        or (len(alias_compact) > len(target) and alias_compact.endswith(target))
        for alias_compact in (_compact(alias) for alias in root_aliases)
    )


def _support_organizations(texts: tuple[str, ...]) -> tuple[str, ...]:
    compact = _compact(" ".join(texts))
    found = [
        name
        for name in _SUPPORT
        if re.search(
            re.escape(name)
            + r"(?:\([^)]{0,100}\))?(?:을|를)?(?:둔다|설치한다|둘수있(?:다|고|으며)|설치할수있(?:다|고|으며))",
            compact,
        )
    ]
    # `실무지원단` also contains the generic suffix `지원단`.  They are one
    # legal organization, not two cost components; retain the longest formal
    # designation when names overlap.
    return tuple(
        name for name in found
        if not any(name != other and name in other for other in found)
    )


def _distributed_scope(text: str, name: str) -> bool:
    compact = _compact(text)
    # The location phrase must be attached to the creation of this body.
    # This accepts `시ㆍ도소방본부에 X위원회를 둔다` but not a later mention
    # of local-government members in one national committee.
    scope = (
        r"(?:각|모든)?(?:"
        r"지방자치단체(?:마다|별로|에|는|은)|"
        r"(?:시ㆍ도|시도)(?:(?:소방)?본부|교육청|지방청|기관)?(?:마다|별로|에|는|은)|"
        r"특별시ㆍ광역시ㆍ도(?:마다|별로|에|는|은)"
        r")"
    )
    if re.search(
        scope + r".{0,100}" + re.escape(_compact(name))
        + rf"(?:\([^)]{{0,100}}\))?{_CREATE}",
        compact,
    ):
        return True
    # 법률은 `각 지방자치단체마다` 대신 복수 단체장의 소속기관으로
    # 각각 설치한다고 표현하기도 한다.
    local_executives = (
        r"(?:특별시장|광역시장|특별자치시장|도지사|특별자치도지사|"
        r"시ㆍ도지사|시도지사|시장|군수|구청장)"
    )
    separators = r"(?:ㆍ|·|,|및|이나|나|또는)"
    executive_list = (
        local_executives
        # A single `통합특별시장 소속` is one body.  This branch is only for
        # an explicit list such as `시장ㆍ군수ㆍ구청장 소속으로`, which
        # denotes installation under each listed local executive.
        + rf"(?:{separators}{local_executives})+"
        + r"(?:\([^)]{0,100}\))?"
    )
    return bool(re.search(
        executive_list + r"소속으로.{0,80}" + re.escape(_compact(name))
        + rf"(?:\([^)]{{0,100}}\))?{_CREATE}",
        compact,
    ))


def _rename_pairs(raw_text: str) -> list[tuple[str, str]]:
    compact = _compact(raw_text)
    pairs = re.findall(
        rf"[“\"]([^”“\"]{{2,80}}{_BODY})[”\"](?:을|를)"
        rf"[“\"]([^”“\"]{{2,80}}{_BODY})[”\"]로",
        compact,
    )
    return list(dict.fromkeys(pairs))


def _amendment_events(
    raw_text: str,
    articles: list[dict[str, Any]],
) -> list[CommitteeEventV5]:
    compact_raw = _compact(raw_text)
    events: list[CommitteeEventV5] = []
    for old_name, new_name in _rename_pairs(raw_text):
        related = [
            article for article in articles
            if old_name in _compact(str(article.get("text") or ""))
            or new_name in _compact(str(article.get("text") or ""))
            or (
                str(article.get("change_type") or "") == "개정"
                and _MEMBERSHIP_CHANGE.search(_compact(str(article.get("text") or "")))
            )
        ]
        proposal_window = compact_raw[: compact_raw.find("법률제") if "법률제" in compact_raw else 3000]
        changed = bool(
            _MEMBERSHIP_CHANGE.search(" ".join(_compact(str(a.get("text") or "")) for a in related))
            or _MEMBERSHIP_CHANGE.search(proposal_window)
        )
        if not changed:
            continue
        refs = tuple(str(value.get("no") or "") for value in related)
        texts = tuple(str(value.get("text") or "") for value in related)
        events.append(CommitteeEventV5(
            name=new_name,
            article_refs=refs,
            texts=texts or (proposal_window,),
            change_kind="membership_expansion_or_reorganization",
            actor=_actor(" ".join(texts)),
            multiplicity="single",
            source_kind="amendment_command",
        ))
    return events


def _standing_member_amendment_events(
    raw_text: str,
    articles: list[dict[str, Any]],
) -> list[CommitteeEventV5]:
    """Recover an existing committee whose paid standing seats are replaced.

    Partial-amendment clauses often contain only `2인은` and omit the legal
    body's name.  The proposal reason supplies that missing entity grounding.
    This is deliberately limited to an explicit standing-member replacement or
    exclusion statement; a mere mention of a committee is not enough.
    """
    compact = _compact(raw_text)
    proposal_end = compact.find("법률제")
    proposal = compact[: proposal_end if proposal_end > 0 else 3500]
    if not (
        "상임위원" in proposal
        and re.search(r"배제|새로임명|신규로?임명|겸직.{0,50}(?:금지|배제|해소)", proposal)
    ):
        return []

    matches = re.findall(
        rf"(?:현재|현행){_NAME}(?:\([^)]{{0,100}}\))?의상임위원",
        proposal,
    )
    names = []
    for raw_name in matches:
        name = re.sub(r"^(?:현재|현행)", "", raw_name)
        if name and name not in names:
            names.append(name)
    if not names:
        return []

    related = [
        article for article in articles
        if (
            "상임" in _compact(str(article.get("text") or ""))
            or "위원회의구성" in _title(article)
        )
    ]
    refs = tuple(str(value.get("no") or "") for value in related)
    texts = tuple(str(value.get("text") or "") for value in related)
    return [
        CommitteeEventV5(
            name=name,
            article_refs=refs,
            texts=texts + (proposal,),
            change_kind="standing_member_replacement",
            actor=_actor(" ".join(texts) + " " + proposal),
            multiplicity="single",
            has_standing_staff=True,
            has_standing_members=True,
            source_kind="proposal_reason_and_amendment_command",
        )
        for name in names
    ]


def _scope_expansion_events(articles: list[dict[str, Any]]) -> list[CommitteeEventV5]:
    events: list[CommitteeEventV5] = []
    for article in articles:
        text = _compact(str(article.get("text") or ""))
        pairs = re.findall(
            rf"[“\"]([^”“\"]{{2,100}}{_BODY})를?구성하여[”\"]를"
            rf"[“\"]([^”“\"]{{2,120}}{_BODY})를?구성하여[”\"]로",
            text,
        )
        for old_name, new_name in pairs:
            if "지역별" not in new_name or "지역별" in old_name:
                continue
            # A quoted replacement can contain the complete actor list before
            # the body name, e.g. `산업별 선도기업 ... 산업별 X협의회`.
            # The final scope marker belongs to the legal body; earlier ones
            # describe its members.  Keep the suffix after that final marker.
            scope_markers = list(re.finditer(r"[가-힣]{1,12}별", old_name))
            base = (
                old_name[scope_markers[-1].end():]
                if scope_markers
                else old_name
            )
            name = "지역별" + base
            events.append(CommitteeEventV5(
                name=name,
                article_refs=(str(article.get("no") or ""),),
                texts=(str(article.get("text") or ""),),
                change_kind="scope_expansion",
                actor=_actor(str(article.get("text") or "")),
                multiplicity="multi_instance",
                source_kind="amendment_command",
            ))
    return events


def _creation_linked_to_parent(
    text: str,
    aliases: tuple[str, ...],
    child_name: str,
) -> bool:
    compact = _compact(text)
    child = _compact(child_name)
    child_match = re.search(
        re.escape(child) + rf"(?:\([^)]{{0,100}}\))?{_CREATE}", compact
    )
    if child_match is None:
        return False
    return any(
        (position := compact.find(_compact(alias))) >= 0
        and position < child_match.start()
        for alias in aliases
    )


def _proposal_explicitly_incremental(proposal: str, name: str) -> bool:
    compact = _compact(proposal)
    target = _compact(name)
    position = compact.find(target)
    if position < 0:
        return False
    local = compact[max(0, position - 100): position + len(target) + 120]
    return bool(re.search(r"신설|새로|도입|확대|증원|개편|변경", local))


def _collapse_full_revision_clusters(
    raw_text: str,
    articles: list[dict[str, Any]],
    nodes: list[Any],
    events: list[CommitteeEventV5],
) -> list[CommitteeEventV5]:
    """Turn a full-revision restatement into one incremental relation graph.

    A full revision repeats existing `둔다` clauses.  They are not new costs by
    themselves.  When one root committee explicitly creates multiple child
    bodies and a secretariat, v5 keeps the root and models only that relation
    bundle; repeated standalone bodies without incremental proposal evidence
    are not promoted to cost events.
    """
    compact_raw = _compact(raw_text)
    if "전부개정법률안" not in compact_raw[:1200]:
        return events
    proposal_end = compact_raw.find("법률제")
    proposal = compact_raw[:proposal_end if proposal_end > 0 else 4000]
    event_by_name = {event.name: event for event in events}
    candidates: list[tuple[int, str, tuple[str, ...], tuple[str, ...], list[dict[str, Any]]]] = []

    for node in nodes:
        parent = event_by_name.get(node.name)
        if parent is None:
            continue
        aliases = node.aliases
        children: list[str] = []
        supports: list[str] = []
        related: list[dict[str, Any]] = []
        for article in articles:
            text = str(article.get("text") or "")
            found_here = False
            for subordinate in _SUBORDINATE:
                if _is_root_designation(subordinate, aliases):
                    continue
                if _creation_linked_to_parent(text, aliases, subordinate):
                    children.append(subordinate)
                    found_here = True
            for child in events:
                if child.name == parent.name:
                    continue
                if _creation_linked_to_parent(text, aliases, child.name):
                    children.append(child.name)
                    found_here = True
            for support in _SUPPORT:
                if _creation_linked_to_parent(text, aliases, support):
                    supports.append(support)
                    found_here = True
            if found_here:
                related.append(article)
        children_tuple = tuple(dict.fromkeys(children))
        supports_tuple = tuple(dict.fromkeys(supports))
        if len(children_tuple) >= 2 and supports_tuple:
            candidates.append((
                len(children_tuple) + len(supports_tuple),
                parent.name,
                children_tuple,
                supports_tuple,
                related,
            ))

    if not candidates:
        return events
    _, parent_name, children, supports, related = max(candidates)
    parent = event_by_name[parent_name]
    refs = tuple(dict.fromkeys(
        [*parent.article_refs, *(str(row.get("no") or "") for row in related)]
    ))
    texts = tuple(dict.fromkeys(
        [*parent.texts, *(str(row.get("text") or "") for row in related)]
    ))
    clustered = replace(
        parent,
        article_refs=refs,
        texts=texts,
        change_kind="full_revision_reorganization",
        subordinate_bodies=children,
        optional_subordinate_bodies=(),
        support_organizations=supports,
        has_support_staff=True,
        # Existing parent staffing is a baseline/delta question, not a new
        # full payroll merely because the full text repeats its composition.
        has_standing_staff=False,
        has_standing_members=False,
        whole_operating_baseline=False,
        source_kind="full_revision_relation_graph",
    )

    output = [clustered]
    child_keys = {_compact(name) for name in children}
    for event in events:
        if event.name == parent_name or _compact(event.name) in child_keys:
            continue
        if _proposal_explicitly_incremental(proposal, event.name):
            output.append(event)
    return output


def extract_committee_events(
    raw_text: str,
    articles: list[dict[str, Any]],
) -> list[CommitteeEventV5]:
    events: list[CommitteeEventV5] = []
    nodes = extract_committee_nodes(articles)
    for node in nodes:
        legacy_plan = select_v4_formula_plan(node)
        refs, texts = _extended_context(
            articles,
            node.definition_index,
            node.article_refs,
        )
        context = " ".join(texts)
        required_subordinates = _subordinate_bodies(refs, texts, node.aliases)
        support_organizations = _support_organizations(texts)
        has_standing_members = bool(_STANDING_MEMBER.search(_compact(context)))
        events.append(CommitteeEventV5(
            name=node.name,
            article_refs=refs,
            texts=texts,
            change_kind="establishment",
            actor=node.event.actor,
            multiplicity=(
                "multi_instance"
                if _distributed_scope(texts[0] if texts else "", node.name)
                else "single"
            ),
            subordinate_bodies=required_subordinates,
            optional_subordinate_bodies=_optional_subordinate_bodies(
                refs, texts, required_subordinates, node.aliases,
            ),
            support_organizations=support_organizations,
            has_support_staff=bool(_SUPPORT_STAFF.search(_compact(context))),
            has_standing_staff=(
                bool(_STANDING_STAFF.search(_compact(context)))
                or legacy_plan.family == "staffed_committee_operation"
            ),
            has_standing_members=has_standing_members,
            whole_operating_baseline=(
                bool(support_organizations)
                and legacy_plan.family == "analog_flat_operating_budget"
                and not bool(_SUPPORT_STAFF.search(_compact(context)))
                and not has_standing_members
            ),
        ))

    additions = (
        _amendment_events(raw_text, articles)
        + _standing_member_amendment_events(raw_text, articles)
        + _scope_expansion_events(articles)
    )
    for addition in additions:
        if any(_same_name(addition.name, event.name) for event in events):
            continue
        events.append(addition)
    return _collapse_full_revision_clusters(raw_text, articles, nodes, events)


def _component(
    kind: str,
    formula: str,
    operands: tuple[str, ...],
    basis: str,
    *,
    required: bool = True,
) -> CostComponent:
    return CostComponent(
        kind=kind,
        formula=formula,
        operands=operands,
        basis=basis,
        required=required,
    )


def plan_committee_cost(event: CommitteeEventV5) -> ComponentFormulaPlan:
    compact = _compact(event.context)
    if event.change_kind == "full_revision_reorganization":
        components = (
            _component(
                "subordinate_operating_baseline",
                "기능·구성이 동일한 하위기구 군의 연간 운영비",
                ("하위기구 구조", "동일 구조 선례", "연간 운영비"),
                "전부개정이 재서술한 기존 본체는 제외하고 새로 연결된 하위기구의 운영비만 증분 계상",
            ),
            _component(
                "support_operating_baseline",
                "직무·구성이 동일한 사무조직의 연간 운영비",
                ("사무조직 구조", "동일 구조 선례", "연간 운영비"),
                "본위원회와 별도로 신설되는 사무조직의 인력·기본경비·사업비 묶음",
            ),
        )
        return ComponentFormulaPlan(
            family="reorganized_committee_support_bundle",
            formula=" + ".join(component.formula for component in components),
            components=components,
            selection_basis="전부개정의 기존 본체 재서술과 신규 하위기구·사무조직을 분리",
            evidence_alternatives=(
                "same_subordinate_body_cluster",
                "same_support_office_structure",
            ),
        )
    if event.change_kind == "standing_member_replacement":
        components = (
            _component(
                "standing_member_compensation",
                "순증 신규 상임위원 × 1인당 보수·수당·기관부담금",
                ("순증 신규 상임위원", "1인당 보수·수당", "기관부담금"),
                "기존 겸직자를 비겸직 상임위원으로 대체하면 순증 인건비가 발생",
            ),
            _component(
                "workspace_operating_expense",
                "순증 사무공간 면적 × 임차료·관리비 단가",
                ("순증 사무공간 면적", "임차료·관리비 단가"),
                "상근 직위의 신규 전용 업무공간",
            ),
            _component(
                "facility_setup",
                "순증 사무공간의 일회성 시설공사비",
                ("시설공사 범위", "시설공사 단가"),
                "신규 상근자의 공간 조성은 초년도 일회성 비용 후보",
                required=False,
            ),
            _component(
                "asset_acquisition",
                "순증 인원 × 1인당 자산취득비",
                ("순증 인원", "1인당 자산취득비"),
                "신규 상근자의 업무장비는 초년도 일회성 비용 후보",
                required=False,
            ),
        )
        return ComponentFormulaPlan(
            family="standing_member_replacement",
            formula=" + ".join(component.formula for component in components),
            components=components,
            selection_basis="기존 겸직 상임위원을 신규 비겸직 상임위원으로 대체하는 구성 변경",
            evidence_alternatives=("same_grade_public_compensation", "workspace_standard"),
        )
    if event.change_kind == "membership_expansion_or_reorganization":
        component = _component(
            "activity_allowance_bundle",
            "순증 수당 지급대상 × Σ(활동별 연간 횟수 × 활동별 단가)",
            ("순증 수당 지급대상", "활동별 연간 횟수", "활동별 단가"),
            "위원 정수·구성이 바뀌는 기존 위원회는 기존 운영활동별 순증 비용을 계산",
        )
        return ComponentFormulaPlan(
            family="multi_activity_meeting_allowance",
            formula=component.formula,
            components=(component,),
            selection_basis="기존 위원회의 명칭·위원 구성을 개편하는 개정 명령",
            evidence_alternatives=("same_institution_operating_history",),
        )

    if _EVENT_DRIVEN.search(compact):
        component = _component(
            "event_driven_meeting_allowance",
            "연도별 구성 건수 × 건당 순증 유급위원 × 건당 회의 횟수 × 수당",
            ("구성 건수", "건당 유급위원", "건당 회의 횟수", "수당"),
            "선출·추천 사건마다 다시 구성되는 비정기 위원회",
        )
        return ComponentFormulaPlan(
            family="event_driven_committee",
            formula=component.formula,
            components=(component,),
            selection_basis=component.basis,
        )

    if event.whole_operating_baseline:
        component = _component(
            "whole_operating_baseline",
            "기능과 지원구조가 동일한 유사기관의 연간 운영예산",
            ("동일 기능·지원구조의 유사기관", "연간 운영예산", "기준연도"),
            "지원조직 세부 정원은 없고 동일한 기관 전체 운영 선례가 필요한 구조",
        )
        return ComponentFormulaPlan(
            family="analog_flat_operating_budget",
            formula=component.formula,
            components=(component,),
            selection_basis=component.basis,
            evidence_alternatives=("structurally_identical_whole_budget_precedent",),
        )

    if event.multiplicity == "multi_instance" and _CONTINUOUS_CASEWORK.search(
        compact + _compact(event.name)
    ):
        component = _component(
            "multi_instance_operating_baseline",
            "대상 기관 수 × 동일 기능 기관별 연간 운영비",
            ("대상 기관 수", "동일 기능 기관별 연간 운영비"),
            "회의 개최 자체가 아니라 상시 민원·고충 사건 처리가 주된 법정 업무인 복수기관",
        )
        return ComponentFormulaPlan(
            family="multi_instance_operating_baseline",
            formula=component.formula,
            components=(component,),
            selection_basis=component.basis,
            evidence_alternatives=("same_institution_operating_history",),
        )

    if (
        event.has_standing_staff
        and not event.has_standing_members
        and not event.support_organizations
    ):
        components = (
            _component(
                "staff_compensation",
                "직급별 순증 인원 × 1인당 보수·기관부담금",
                ("직급별 순증 인원", "직급별 1인당 보수", "기관부담금"),
                "상근 지원조직이 수반되는 상설 위원회",
            ),
            _component(
                "basic_operating_expense",
                "보수액 × 기본경비 비율",
                ("보수액", "기본경비 비율"),
                "별도 상근인력의 기관 운영경비",
            ),
            _component(
                "asset_acquisition",
                "신규 인원 × 1인당 자산취득비",
                ("신규 인원", "1인당 자산취득비"),
                "신규 지원인력의 초년도 업무장비",
            ),
            _component(
                "business_expense",
                "유사 상설위원회의 연간 사업비",
                ("동일 기능의 상설위원회", "연간 사업비"),
                "법률상 지속적 조사·정책 업무 수행",
            ),
        )
        return ComponentFormulaPlan(
            family="staffed_committee_operation",
            formula=" + ".join(component.formula for component in components),
            components=components,
            selection_basis="상근인력을 갖는 상설 위원회의 전체 운영비용",
            evidence_alternatives=("same_staffed_committee", "decomposed_operands"),
        )
    components: list[CostComponent] = []
    if event.has_standing_members:
        components.append(_component(
            "standing_member_compensation",
            "순증 상임위원 × 1인당 보수·수당·기관부담금",
            ("순증 상임위원", "1인당 보수·수당", "기관부담금"),
            "법률이 비겸직 상임직을 명시함",
        ))
    main_formula = "순증 수당 지급대상 × 연간 회의 횟수 × 1인 1회당 수당"
    main_operands = ("순증 수당 지급대상", "연간 회의 횟수", "1인 1회당 수당")
    if event.multiplicity == "multi_instance":
        main_formula = "설치기관 수 × " + main_formula
        main_operands = ("설치기관 수",) + main_operands
    components.append(_component(
        "main_meeting_allowance",
        main_formula,
        main_operands,
        "심의·협의기구의 기본 직접비는 유급위원 회의참석 비용",
    ))

    if event.subordinate_bodies:
        components.append(_component(
            "subordinate_meeting_allowance",
            "하위기구 수 × 하위기구 유급위원 × 연간 회의 횟수 × 수당",
            ("하위기구 수", "하위기구 유급위원", "하위기구 회의 횟수", "수당"),
            (
                "별도 조문에서 구성·소집·의결 구조가 확인되는 하위기구"
                + (
                    "; 재량적 하위기구는 실제 운영 여부 확인 후 수량에 추가"
                    if event.optional_subordinate_bodies else ""
                )
            ),
        ))
    for optional_name in (
        event.optional_subordinate_bodies if not event.subordinate_bodies else ()
    ):
        components.append(_component(
            "subordinate_meeting_allowance",
            "하위기구 수 × 하위기구 유급위원 × 연간 회의 횟수 × 수당",
            ("하위기구 운영 여부", "하위기구 유급위원", "하위기구 회의 횟수", "수당"),
            f"{optional_name}를 둘 수 있는 재량규정이므로 실제 운영 여부를 확인한 뒤만 계상",
            required=False,
        ))
    if event.support_organizations:
        components.append(_component(
            "support_staff_compensation",
            "지원인력 순증 인원 × 1인당 보수·기관부담금",
            ("지원인력 순증 인원", "1인당 보수", "기관부담금"),
            (
                "사무조직과 전문위원·직원·정원이 함께 명시됨"
                if event.has_support_staff
                else "별도 사무조직의 신설은 순증 지원인력 여부를 반드시 확인해야 함"
            ),
        ))
        components.append(_component(
            "support_operating_expense",
            "지원조직 기본경비 + 사업비 + 자산취득비",
            ("기본경비", "사업비", "자산취득비"),
            "위원회와 별도의 지원조직 설치 근거가 명시됨",
        ))

    if event.has_standing_members and event.support_organizations:
        family = "staffed_committee_support_bundle"
    elif event.has_standing_staff:
        family = "staffed_committee_operation"
    elif event.support_organizations and event.subordinate_bodies:
        family = "committee_support_bundle"
    elif event.support_organizations:
        family = "committee_support_operation"
    elif event.subordinate_bodies:
        family = "compound_committee_allowance"
    elif event.multiplicity == "multi_instance":
        family = "multi_instance_meeting_allowance"
    else:
        family = "meeting_allowance"

    return ComponentFormulaPlan(
        family=family,
        formula=" + ".join(component.formula for component in components),
        components=tuple(components),
        selection_basis="비용 발생 구조를 독립 구성요소로 분해한 뒤 합산",
        evidence_alternatives=(
            "decomposed_operands",
            "structurally_identical_whole_budget_precedent",
        ),
        requires_human_input=True,
    )
