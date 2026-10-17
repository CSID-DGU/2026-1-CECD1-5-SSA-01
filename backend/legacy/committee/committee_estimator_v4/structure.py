from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from backend.committee_estimator_v3.pipeline import _CommitteeTarget, _actor
from backend.estimator_v2.types import AtomicEvent

from .types import CommitteeRelation, FormulaPlan


_BODY = r"(?:위원회|심의회|협의회|참여회의)"
_VERB = (
    r"(?:를|을)?(?:둔다|두어야한다|설치한다|설치하여야한다|"
    r"구성한다|구성하여야한다|둘수있다)"
)
_NAME = rf"([\uac00-\ud7a3A-Za-z0-9ㆍ·]{{2,60}}?{_BODY})"
_INTRODUCER = (
    r"(?:심의하기위하여|검토하기위하여|처리하기위하여|지원하기위하여|"
    r"위하여|사항을심의하는|사무의처리를위하여|소속으로|"
    r"지방자치단체는|특별시에|광역시에|도에|시에|다만,)"
)
_INTRODUCED_NAME = re.compile(
    rf"(?={_INTRODUCER}{_NAME}(?:\([^)]{{0,100}}\))?{_VERB})"
)
_TITLE_ENTITY = re.compile(rf"([\uac00-\ud7a3A-Za-z0-9ㆍ·]{{2,80}}?{_BODY})")
_GENERIC_NAMES = {
    "위원회",
    "심의회",
    "협의회",
    "실무위원회",
    "분과위원회",
    "소위원회",
    "전문위원회",
    "실무협의회",
    "참여회의",
}
_SUBORDINATE_NAMES = {
    "실무위원회",
    "분과위원회",
    "소위원회",
    "전문위원회",
    "실무협의회",
}
_STRUCTURAL_GENERIC_TITLE = re.compile(
    r"^(?:(?:위원회|심의회|협의회)(?:의)?"
    r"(?:기능|구성|운영|회의|위원장등의직무|위원장|간사|수당등|수당|"
    r"운영세칙|관계기관등에대한협조요청)?|"
    r"실무위원회|분과위원회|소위원회|전문위원회|실무협의회|"
    r"위원장등의직무|위원장|회의|간사|수당등|수당|운영세칙|"
    r"관계기관등에대한협조요청)$"
)
_SUPPORT_ORGANIZATION = re.compile(
    r"(실무지원단|지원단|사무국|사무처|사무기구)"
    r"(?:을|를)?(?:둔다|설치한다|둘수있다|설치할수있다)"
)
_HEAVY_STAFF = re.compile(
    # `국회 소관 상임위원회` 같은 보고대상 명칭은 대상 위원회의
    # 상근 인력 근거가 아니므로 `상임위원회`를 제외한다.
    r"상임위원(?!회)|상근위원|정무직공무원|별도정원|"
    r"(?:사무국|사무처).{0,40}(?:직원|정원|인력)"
)
_EVENT_DRIVEN = re.compile(
    r"(?:선출|지명|추천|임명).{0,30}(?:때마다|할때마다)|"
    r"(?:때마다|할때마다).{0,30}(?:구성|소집|개최)"
)
_MEMBERSHIP = re.compile(
    r"\d+(?:명|인)(?:이상)?(?:\d+(?:명|인))?(?:이하|이내)?의?(?:위원)?으로구성|"
    r"\d+(?:명|인)(?:이상|이하|이내)?의?[가-힣A-Za-z0-9ㆍ·]{0,30}위원으로구성|"
    r"(?:위원장|\d+명).{0,40}\d+(?:명|인)(?:이하|이내)|"
    rf"\d+(?:명|인)(?:이상|이하|이내)?의?[가-힣A-Za-z0-9ㆍ·]{{2,60}}{_BODY}{_VERB}"
)
_SPECIFIC_COMPOSITION_REFERENCE = re.compile(
    rf"{_BODY}(?:의)?구성및운영[^.。]{{0,100}}준용|"
    rf"{_BODY}에관한사항[^.。]{{0,100}}준용"
)
_VAGUE_ENTITY_PREFIX = re.compile(
    r"^(?:각각에소속되는|각각|해당|관련|이조에서의)"
)
_INTERNAL_PERSONNEL_GOVERNANCE = re.compile(
    r"(?:직원|소속공무원).{0,40}징계(?:처분)?.{0,30}(?:심의|의결)"
)
_PARLIAMENTARY_GOVERNANCE = re.compile(
    r"본회의|국회의장|교섭단체|국회사무처|입법조사관"
)
_EMBEDDED_SUPPORT_ORGANIZATION = re.compile(
    r"(?:사무처|본부|부|청|원)에(?:실무)?지원단을둔다"
)


@dataclass(frozen=True)
class CommitteeNode:
    name: str
    definition_index: int
    article_refs: tuple[str, ...]
    texts: tuple[str, ...]
    change_type: str
    aliases: tuple[str, ...]
    relations: tuple[CommitteeRelation, ...]
    event: AtomicEvent

    @property
    def context(self) -> str:
        return " ".join(self.texts)

    def as_v3_target(self) -> _CommitteeTarget:
        return _CommitteeTarget(
            name=self.name,
            article_refs=self.article_refs,
            texts=self.texts,
            change_type=self.change_type,
            event=self.event,
        )


def _compact(value: str) -> str:
    compact = re.sub(r"\s+", "", value or "")
    return re.sub(r"-\d+-", "", compact)


def _article_title(article_ref: str) -> str:
    match = re.search(r"\(([^()]*)\)", article_ref or "")
    return _compact(match.group(1) if match else "")


def _clean_name(value: str) -> str:
    value = _compact(value)
    value = re.sub(r"^\d+(?:명|인)(?:이내|이하|이상)?의?", "", value)
    prefixes = (
        "심의하기위하여",
        "검토하기위하여",
        "처리하기위하여",
        "지원하기위하여",
        "사항을심의하는",
        "사무의처리를위하여",
        "지방자치단체는",
        "소속하에",
        "소속으로",
        "특별시에",
        "광역시에",
        # 법률이 동일 조문 안에서 중앙 본위원회와 선택적 지역위원회를
        # 함께 두는 경우, 설치조건 문구가 기구명에 붙어 들어오지 않게 한다.
        # 특정 위원회명이 아니라 법령의 일반적인 연결어를 제거하는 규칙이다.
        "조례로정하는바에따라",
        "위하여",
    )
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if prefix in value:
                suffix = value.rsplit(prefix, 1)[-1]
                if re.search(rf"{_BODY}$", suffix):
                    value = suffix
                    changed = True
                    break
    # 법률 문장은 "각 선출기관에 X위원회를 둔다"처럼 설치 장소를
    # 기구명 앞에 붙인다.  기관·부처를 나타내는 명사 뒤의 처소격
    # 조사까지를 제거하되, 뒤에 완전한 기구명이 남을 때만 적용한다.
    value = re.sub(
        rf"^.*(?:기관|지방자치단체|위원회|국회|정부|부|청)에(?=(?:\d+(?:명|인)(?:이상|이하|이내)?의?)?[가-힣A-Za-z0-9ㆍ·]{{2,60}}{_BODY}$)",
        "",
        value,
    )
    value = re.sub(r"^\d+(?:명|인)(?:이내|이하|이상)?의?", "", value)
    return value


def _is_concrete_name(value: str) -> bool:
    """법률상 식별 가능한 기구명만 반환한다.

    "각각에 소속되는 위원회"는 설치 서술은 있지만 하나의 기구명이
    아니므로 독립 비용사건을 만들지 않는다.
    """
    return bool(
        value
        and value not in _GENERIC_NAMES
        and not _VAGUE_ENTITY_PREFIX.search(value)
    )


def _title_entity(article: dict[str, Any]) -> str | None:
    match = _TITLE_ENTITY.search(_article_title(str(article.get("no") or "")))
    if not match:
        return None
    value = _clean_name(match.group(1))
    return value if _is_concrete_name(value) else None


def _established_entities(article: dict[str, Any]) -> list[str]:
    text = _compact(str(article.get("text") or ""))
    values: list[str] = []
    title_entity = _title_entity(article)
    if title_entity and re.search(
        re.escape(title_entity) + rf"(?:\([^)]{{0,100}}\))?{_VERB}",
        text,
    ):
        values.append(title_entity)
    for match in _INTRODUCED_NAME.finditer(text):
        value = _clean_name(match.group(1))
        if _is_concrete_name(value):
            values.append(value)
        elif value in _SUBORDINATE_NAMES:
            values.append(value)
    # Titles sometimes hold the full legal name while the operative sentence
    # uses a short alias such as "지원위원회".  A structural title plus an
    # establishment predicate is sufficient, but a mere cross-reference is not.
    if title_entity and title_entity not in values and re.search(_VERB, text):
        aliases = _aliases(text, title_entity)
        if any(re.search(re.escape(alias) + _VERB, text) for alias in aliases):
            values.append(title_entity)
    unique = list(dict.fromkeys(values))
    if title_entity:
        unique = [
            title_entity
            if (
                (
                    value.endswith(title_entity)
                    and re.search(
                        r"(?:에|소속으로)$",
                        value[:-len(title_entity)],
                    )
                )
                or value.replace("에", "", 1) == title_entity
            )
            else value
            for value in unique
        ]
        unique = list(dict.fromkeys(unique))
    # 제목의 본위원회와 같은 접미사를 가진 선택적 지역위원회가 한 조문에
    # 함께 있으면, 더 긴 이름이라는 이유로 본위원회를 지우면 안 된다.
    # 재량 설치기구는 자동 비용사건으로 승격하지 않고 제목의 의무 설치
    # 본위원회를 유지한다. 특정 기관명이 아닌 의무성·조문 구조 규칙이다.
    if title_entity in unique:
        unique = [
            value
            for value in unique
            if not (
                value != title_entity
                and value.endswith(title_entity)
                and re.search(
                    re.escape(value)
                    + r"(?:\([^)]{0,100}\))?(?:를|을)?둘수있다",
                    text,
                )
            )
        ]

    # 제목의 약칭과 본문의 정식명이 같이 잡히면 더 긴 정식명만 유지한다.
    # 단, 위에서 보존한 제목의 법정 기구명은 약칭으로 취급하지 않는다.
    return [
        value
        for value in unique
        if not any(
            value != title_entity
            and value != other
            and len(value) < len(other)
            and other.endswith(value)
            for other in unique
        )
    ]


def _aliases(text: str, name: str) -> tuple[str, ...]:
    compact = _compact(text)
    aliases = {name}
    pattern = re.compile(
        re.escape(name) + r"\(이하[\"“”]?([^\"“”()]{2,30})[\"“”]?라한다\)"
    )
    match = pattern.search(compact)
    if match and re.search(rf"{_BODY}$", match.group(1)):
        aliases.add(match.group(1))
    return tuple(sorted(aliases, key=len, reverse=True))


def _is_generic_related(article: dict[str, Any]) -> bool:
    title = _article_title(str(article.get("no") or ""))
    # A standalone title such as "위원장", "수당 등", or "소위원회" is
    # itself an explicit governance relation when it immediately follows the
    # committee definition. Requiring the full committee name again would
    # drop normal multi-article legislation.
    return bool(_STRUCTURAL_GENERIC_TITLE.match(title))


def _subordinate_suffix(value: str) -> str | None:
    return next(
        (suffix for suffix in _SUBORDINATE_NAMES if value.endswith(suffix)),
        None,
    )


def _is_subordinate_root(
    article: dict[str, Any],
    name: str,
    article_entities: list[str],
) -> bool:
    """하위기구를 독립 비용사건으로 중복 승격하지 않는다."""
    suffix = _subordinate_suffix(name)
    if suffix is None:
        return False
    title = _article_title(str(article.get("no") or ""))
    if title in _SUBORDINATE_NAMES:
        return True
    return any(
        other != name and _subordinate_suffix(other) is None
        for other in article_entities
    )


def _is_internal_personnel_governance(article: dict[str, Any]) -> bool:
    """신설기관 내부 직원 징계만을 위한 기구는 독립 비용사건이 아니다."""
    return bool(
        _INTERNAL_PERSONNEL_GOVERNANCE.search(
            _compact(str(article.get("text") or ""))
        )
    )


def _is_distributed_installation(definition: str, name: str) -> bool:
    """설치 주체·범위와 기구명을 같은 설치절 안에서 확인한다.

    정책 대상이나 위원 자격 설명에 `지방자치단체`가 나오는 것만으로는
    복수 설치가 아니다.  지방자치단체마다/별로/에 설치한다는 범위가
    기구명과 설치 서술어 앞에 직접 연결되어야 한다.
    """
    scope = (
        r"(?:(?:인구\d+만이상의)|각|모든)?"
        r"(?:지방자치단체|시ㆍ도|시도)(?:마다|별로|는|은|에)"
    )
    return bool(re.search(
        scope + r".{0,180}" + re.escape(name)
        + rf"(?:\([^)]{{0,100}}\))?{_VERB}",
        definition,
    ))


def _related_articles(
    articles: list[dict[str, Any]],
    definition_index: int,
    name: str,
) -> list[dict[str, Any]]:
    definition = articles[definition_index]
    aliases = _aliases(str(definition.get("text") or ""), name)
    rows = [definition]
    for index in range(definition_index + 1, len(articles)):
        article = articles[index]
        definitions = [
            value for value in _established_entities(article)
            if value not in _SUBORDINATE_NAMES
        ]
        if definitions:
            break
        compact = _compact(f"{article.get('no', '')} {article.get('text', '')}")
        if any(alias in compact for alias in aliases) or _is_generic_related(article):
            rows.append(article)
            continue
        # Do not cross an unrelated policy article.  This is the key v4
        # boundary: later staff, council, and audit provisions cannot leak in.
        break
    return rows


def _relations(
    name: str,
    articles: list[dict[str, Any]],
) -> tuple[CommitteeRelation, ...]:
    values: list[CommitteeRelation] = []
    seen: set[tuple[str, str]] = set()
    for article in articles:
        article_ref = str(article.get("no") or "")
        compact = _compact(str(article.get("text") or ""))
        for subordinate in _SUBORDINATE_NAMES:
            key = ("subordinate_committee", subordinate)
            match = re.search(
                re.escape(subordinate) + _VERB,
                compact,
            )
            if key in seen or match is None:
                continue
            local = compact[max(0, match.start() - 40):match.end() + 320]
            following = compact[match.start():match.end() + 320]
            mandatory = not bool(
                re.search(re.escape(subordinate) + r"(?:를|을)?둘수있다", local)
            )
            # 선택적 하위기구는 단순 존재만으로 비용을 더하지 않는다.
            # 같은 국소 문맥에 인원·구성 근거가 있을 때만 계산 구성요소다.
            quantified_subordinate = bool(re.search(
                r"\d+(?:명|인)(?:이상|이하|이내)?의?"
                + re.escape(subordinate),
                local,
            ))
            cost_bearing = (
                mandatory
                or quantified_subordinate
                or bool(_MEMBERSHIP.search(following))
            )
            seen.add(key)
            values.append(CommitteeRelation(
                relation_type="subordinate_committee",
                name=subordinate,
                article_ref=article_ref,
                source_text=f"{name}의 하위기구로 {subordinate}를 두는 조문",
                mandatory=mandatory,
                cost_bearing=cost_bearing,
            ))
        for match in _SUPPORT_ORGANIZATION.finditer(compact):
            key = ("support_organization", match.group(1))
            if key in seen:
                continue
            seen.add(key)
            values.append(CommitteeRelation(
                relation_type="support_organization",
                name=match.group(1),
                article_ref=article_ref,
                source_text=match.group(0),
                mandatory="수있다" not in match.group(0),
                cost_bearing=True,
            ))
    return tuple(values)


def extract_committee_nodes(articles: list[dict[str, Any]]) -> list[CommitteeNode]:
    definitions: list[tuple[int, str]] = []
    for index, article in enumerate(articles):
        article_entities = _established_entities(article)
        for name in article_entities:
            if name in _SUBORDINATE_NAMES:
                continue
            if _is_subordinate_root(article, name, article_entities):
                continue
            if _is_internal_personnel_governance(article):
                continue
            definitions.append((index, name))

    nodes: list[CommitteeNode] = []
    seen: set[tuple[int, str]] = set()
    for index, name in definitions:
        if (index, name) in seen:
            continue
        seen.add((index, name))
        related = _related_articles(articles, index, name)
        texts = tuple(str(value.get("text") or "") for value in related)
        refs = tuple(str(value.get("no") or "") for value in related)
        context = " ".join(texts)
        compact_definition = _compact(texts[0])
        obligation = (
            "discretionary"
            if re.search(re.escape(name) + r".{0,100}둘수있다", compact_definition)
            else "mandatory"
        )
        event = AtomicEvent(
            id=f"COMMITTEE-V4-{len(nodes) + 1:03d}",
            segment_ids=[],
            article_refs=list(refs),
            quotes=list(texts),
            actor=_actor(context),
            action="설치 및 운영",
            object=name,
            bearer="state",
            event_type="committee_operation",
            obligation=obligation,
            cost_mechanism="internal_administration",
            additionality="explicit_new_or_expanded",
            recurrence_text="",
            explanation="설치 서술어와 원문 인용으로 근거링된 v4 위원회 사건",
            grounded=True,
        )
        nodes.append(CommitteeNode(
            name=name,
            definition_index=index,
            article_refs=refs,
            texts=texts,
            change_type=str(articles[index].get("change_type") or ""),
            aliases=_aliases(texts[0], name),
            relations=_relations(name, related),
            event=event,
        ))
    return nodes


def select_formula_plan(node: CommitteeNode) -> FormulaPlan:
    compact = _compact(node.context)
    definition = _compact(node.texts[0] if node.texts else node.context)
    relation_types = {
        value.relation_type
        for value in node.relations
        if value.relation_type != "subordinate_committee" or value.cost_bearing
    }

    if _EVENT_DRIVEN.search(definition):
        return FormulaPlan(
            family="event_driven_committee",
            formula="연도별 구성 건수 × 건당 순증 유급위원 × 건당 회의 횟수 × 1인 1회당 수당",
            components=("구성 건수", "건당 유급위원", "건당 회의 횟수", "수당 단가"),
            selection_basis="선출·지명·추천 사건마다 구성되는 비정기 위원회",
            requires_human_input=True,
        )
    if _is_distributed_installation(definition, node.name):
        return FormulaPlan(
            family="multi_instance_operating_baseline",
            formula="기관 유형별 미설치 기관 수 × 동일 유형의 기관별 평균 운영비",
            components=("기관 유형", "미설치 기관 수", "기관별 평균 운영비"),
            selection_basis="복수 지방자치단체에 의무적으로 반복 설치되는 구조",
            requires_human_input=True,
        )
    if _HEAVY_STAFF.search(compact) or (
        node.name.endswith("특별위원회")
        and _PARLIAMENTARY_GOVERNANCE.search(compact)
    ):
        return FormulaPlan(
            family="staffed_committee_operation",
            formula=(
                "인건비 + 기관부담금 + 기본경비 + 자산취득비 + 사업비 + "
                "위원회 회의비 + 종료 산출물(종합보고서 등)"
            ),
            components=(
                "인건비", "기관부담금", "기본경비", "자산취득비",
                "사업비", "회의비", "종료 산출물",
            ),
            selection_basis=(
                "상근직·사무조직이 명시되거나 제도유형상 상근 지원조직이 "
                "수반되는 위원회"
            ),
            requires_human_input=True,
        )
    if relation_types == {"subordinate_committee", "support_organization"}:
        return FormulaPlan(
            family="committee_support_bundle",
            formula=(
                "본위원회(유급위원 × 회의 횟수 × 수당) + "
                "하위위원회별(유급위원 × 회의 횟수 × 수당) + "
                "지원조직 연간 운영비"
            ),
            components=("본위원회 회의비", "하위위원회 회의비", "지원조직 운영비"),
            selection_basis="한 조문에 본위원회와 하위위원회·지원조직이 관계로 명시됨",
            requires_human_input=True,
        )
    if "subordinate_committee" in relation_types:
        return FormulaPlan(
            family="compound_committee_allowance",
            formula=(
                "본위원회(유급위원 × 회의 횟수 × 수당) + "
                "하위기구별(유급위원 × 회의 횟수 × 수당)"
            ),
            components=("본위원회 회의비", "하위기구별 회의비"),
            selection_basis="본위원회와 소위원회·분과위원회·실무협의회가 관계로 명시됨",
            requires_human_input=True,
        )
    if "support_organization" in relation_types:
        if _EMBEDDED_SUPPORT_ORGANIZATION.search(compact):
            return FormulaPlan(
                family="committee_support_operation",
                formula=(
                    "본위원회 회의비 + 지원조직 인건비 + 기관부담금 + "
                    "기본경비 + 사업비 + 자산취득비"
                ),
                components=(
                    "본위원회 회의비", "지원조직 인건비", "기관부담금",
                    "기본경비", "사업비", "자산취득비",
                ),
                selection_basis=(
                    "위원회와 별도로 기존 행정기관 안에 지원조직을 두는 구조"
                ),
                requires_human_input=True,
            )
        return FormulaPlan(
            family="analog_flat_operating_budget",
            formula="기능과 지원구조가 동일한 유사기관의 연간 운영예산",
            components=("동일 기능·지원구조의 유사기관", "연간 운영예산", "기준연도"),
            selection_basis=(
                "지원조직의 정원·세부비용은 없으므로 동일 지원구조의 "
                "기관 전체 운영예산을 준용"
            ),
            requires_human_input=True,
        )
    if _SPECIFIC_COMPOSITION_REFERENCE.search(compact) or _MEMBERSHIP.search(compact):
        return FormulaPlan(
            family="meeting_allowance",
            formula="순증 수당 지급대상 × 연간 회의 횟수 × 1인 1회당 수당",
            components=("순증 수당 지급대상", "연간 회의 횟수", "1인 1회당 수당"),
            selection_basis="조문이 위원 구성을 정하거나 특정 법령의 구성·운영을 준용함",
            requires_human_input=False,
        )
    return FormulaPlan(
        family="analog_flat_operating_budget",
        formula="기능과 운영방식이 동일한 유사기관의 연간 운영예산",
        components=("동일 기능의 유사기관", "연간 운영예산", "기준연도"),
        selection_basis="조문에 위원 수·회의 횟수가 없고 구성·운영이 하위규정에 위임됨",
        requires_human_input=True,
    )
