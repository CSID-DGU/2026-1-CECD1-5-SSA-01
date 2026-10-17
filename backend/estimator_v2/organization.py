from __future__ import annotations

import glob
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..analyzer_v2 import (
    GEMINI_MODEL,
    LLM_PROFILE,
    OPENAI_EMBED_MODEL,
    embed_batch,
    gemini_json,
)
from ..estimator import tag_db
from ..llm_profiles import (
    dedicated_staff_value_prompt,
    use_unique_prequalified_organization_value,
)
from .cache import get_or_create_json, stable_hash
from .retrieval import _amount_rows
from .types import (
    AtomicEvent,
    EstimateRow,
    EventType,
    Recurrence,
    RowStatus,
    Segment,
    TagCandidate,
)


ORGANIZATION_RETRIEVAL_VERSION = "organization-semantic-cases-v4"
ORGANIZATION_STRUCTURE_SELECTION_VERSION = "organization-structure-v5"
ORGANIZATION_VALUE_SELECTION_VERSION = "organization-value-v13"
ORGANIZATION_SELECTION_VERSION = (
    f"{ORGANIZATION_STRUCTURE_SELECTION_VERSION}+{ORGANIZATION_VALUE_SELECTION_VERSION}"
)
_GENERATED = Path("backend/generated")
_COMPLETE_COMPONENTS = {"personnel", "employer_contribution", "basic_expense", "asset"}
_FIXED_COMPONENTS = {"operating_expense"}
_VALUE_COMPONENTS = _COMPLETE_COMPONENTS | _FIXED_COMPONENTS
_ORGANIZATION_RECALL_K = 20
_AGGREGATE_ITEM_PATTERN = re.compile(
    r"^(?:총계|합계|소계|계|총추가재정소요|추가재정소요총계|총재정소요)$"
)


@dataclass
class OrganizationCase:
    bill_no: str
    bill_name: str
    propose_date: str
    context: str
    items: list[tuple[str, TagCandidate]]
    similarity: float = 0.0

    def components(self) -> list[str]:
        return sorted({component for component, _ in self.items})


@dataclass
class StaffCostBundleCase:
    """One precedent row that already bundles all per-person staff costs.

    Some NABO TAG rows keep salary, employer contributions, basic expenses and
    first-year assets in one coherent item instead of four separate items.
    Those rows used to be invisible to the complete-organization case channel.
    Keeping the row intact is safer than scaling four unrelated precedents.
    """

    item: TagCandidate
    propose_date: str
    context: str
    staff_count: int
    personnel_system: str
    organization_form: str
    similarity: float = 0.0


def _normalise(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _is_aggregate_item(item: TagCandidate) -> bool:
    """Reject table summary rows before component normalisation.

    TAG occasionally contains both detailed cost rows and the source table's
    total row.  A total is evidence about the case, not another independently
    scalable cost component.
    """
    return bool(_AGGREGATE_ITEM_PATTERN.fullmatch(_normalise(item.item_name)))


def _component(item: TagCandidate) -> str:
    """Normalise a TAG item into an organization cost component.

    This is schema normalisation of precedent-side cost labels.  It never
    compares Korean words with the target bill and therefore cannot make a
    precedent look similar merely through target/precedent token overlap.
    """
    if _is_aggregate_item(item):
        return ""
    name = _normalise(item.item_name)
    blob = _normalise(f"{item.item_name} {item.category} {item.formula}")
    # The item label/category expresses the primary cost component.  Formula
    # text often mentions nested parts (e.g. an "인건비" item includes employer
    # contributions), which must not overwrite the primary classification.
    if "기본경비" in name or ("기본경비" in blob and item.category != "인건비"):
        return "basic_expense"
    if (
        "일반관리비" in name
        and re.search(r"인건비.{0,80}(?:비율|비중|%)", blob)
    ):
        return "basic_expense"
    if "자산취득" in name:
        return "asset"
    if any(term in name for term in ("임차료", "관리비", "건축비", "건립비", "시설비", "공사비", "증축비")):
        return "facility"
    if "기관부담" in name:
        return "employer_contribution"
    if item.category == "인건비" or any(term in name for term in ("인건비", "보수", "급여")):
        return "personnel"
    if name in {"사업비", "위원회운영비", "운영경비"}:
        return "operating_expense"
    # Some extracted TAG rows have weak/blank item names.  Formula semantics are
    # a fallback only after the primary label has failed.
    if "자산취득" in blob:
        return "asset"
    if "기관부담" in blob:
        return "employer_contribution"
    return ""


def _is_fixed_operating_precedent(item: TagCandidate) -> bool:
    """Accept only a per-organization operating series, not a generic project budget.

    A staff-scaled personnel series cannot be copied before the target net staff
    count is known.  A precedent explicitly based on the average operating
    expense of comparable committees is different: its denominator is one
    committee, so the intact yearly series is transferable to another
    legislative committee without inventing a staff count.
    """
    if _component(item) != "operating_expense":
        return False
    evidence = _normalise(
        " ".join(
            [
                item.formula,
                *[
                    str(variable.get("name") or "")
                    for variable in item.variables
                ],
                *[
                    str(variable.get("source_text") or "")
                    for variable in item.variables
                ],
            ]
        )
    )
    has_comparable_average = bool(
        re.search(
            r"(?:상임위원회|위원회).{0,80}운영경비.{0,40}평균"
            r"|운영경비.{0,40}평균",
            evidence,
        )
    )
    return has_comparable_average and _has_positive_amount(item)


@lru_cache(maxsize=1)
def _cost_estimate_contexts() -> dict[str, str]:
    """Load local precedent narratives used only for semantic case retrieval."""
    chunks: dict[str, dict[int, str]] = defaultdict(dict)
    for path in glob.glob(str(_GENERATED / "**/chunks.jsonl"), recursive=True):
        try:
            lines = Path(path).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get("documentType") or row.get("document_type") or "") != "cost_estimate":
                continue
            bill_no = str(row.get("billNo") or row.get("bill_no") or "")
            text = str(row.get("text") or row.get("content") or "").strip()
            if not bill_no or not text:
                continue
            try:
                index = int(row.get("chunkIndex") or row.get("chunk_index") or 0)
            except (TypeError, ValueError):
                index = 0
            # The same document exists in several generated datasets.  Keep the
            # richest copy per position instead of duplicating its evidence.
            current = chunks[bill_no].get(index, "")
            if len(text) > len(current):
                chunks[bill_no][index] = text
    return {
        bill_no: "\n".join(text for _, text in sorted(by_index.items()))[:8_000]
        for bill_no, by_index in chunks.items()
    }


def _has_positive_amount(item: TagCandidate) -> bool:
    return any(
        row.get("amount_thousand") is not None and int(row.get("amount_thousand") or 0) > 0
        for row in item.amounts
    )


_STAFF_BUNDLE_ROLE_PATTERNS = {
    "salary": re.compile(r"보수|급여|인건비"),
    "employer_contribution": re.compile(r"기관부담"),
    "basic_expense": re.compile(r"기본경비"),
    "asset": re.compile(r"자산취득"),
}


def _staff_bundle_roles(item: TagCandidate) -> set[str]:
    names = " ".join(str(variable.get("name") or "") for variable in item.variables)
    return {
        role
        for role, pattern in _STAFF_BUNDLE_ROLE_PATTERNS.items()
        if pattern.search(names)
    }


def _single_staff_denominator(item: TagCandidate) -> int | None:
    values: set[int] = set()
    for variable in item.variables:
        if variable.get("type") != "target_count":
            continue
        if str(variable.get("unit") or "") != "명":
            continue
        try:
            value = int(round(float(variable.get("value"))))
        except (TypeError, ValueError):
            continue
        if value > 0:
            values.add(value)
    return next(iter(values)) if len(values) == 1 else None


def _coherent_bundle_series(item: TagCandidate, years: int) -> list[int] | None:
    """Return a total series only when the item has one amount per year.

    A few TAG items contain detail rows and a total row under the same item id.
    Summing or overwriting those rows would reproduce the historical double
    counting bug, so ambiguous series are rejected.
    """
    by_offset: dict[int, list[int]] = defaultdict(list)
    for row in item.amounts:
        if row.get("year_offset") is None:
            continue
        try:
            offset = int(row["year_offset"])
            amount = int(row.get("amount_thousand") or 0)
        except (TypeError, ValueError):
            continue
        if 0 <= offset < years:
            by_offset[offset].append(amount)
    if any(len(by_offset.get(offset, [])) != 1 for offset in range(years)):
        return None
    series = [by_offset[offset][0] for offset in range(years)]
    return series if any(value > 0 for value in series) else None


def _personnel_system(text: str) -> str:
    """Classify the statutory pay/budget system, not surface topic similarity."""
    # ``국회예산정책처`` appears in nearly every official cost-estimate
    # narrative as the document author.  It must not turn an unrelated public
    # institution into a legislative personnel system.
    compact = _normalise(text).replace("국회예산정책처", "")
    if re.search(r"지방자치단체|특별지방자치단체|지방의회|지방공무원|자치구|시·군의원", compact):
        return "local_government"
    if re.search(r"법원|대법원|법관|판사|사법부|사법행정", compact):
        return "judicial"
    if re.search(r"국회법|국회사무처|국회의원|입법조사관|전문위원", compact):
        return "legislative"
    if re.search(r"헌법재판", compact):
        return "constitutional_court"
    if re.search(r"공사|공단|공공기관|출연기관|재단", compact):
        return "public_institution"
    if re.search(r"중앙행정기관|국무총리|정부조직|장관|위원회", compact):
        return "central_government"
    return "unknown"


def _organization_form(text: str) -> str:
    compact = _normalise(text)
    if (
        re.search(r"국회|국회의원|입법", compact)
        and re.search(r"상임위원회|특별위원회|법제위원회", compact)
    ):
        return "legislative_committee"
    if "특별지방자치단체" in compact:
        return "special_local_government"
    if re.search(r"고등법원|지방법원|가정법원|법원지원", compact):
        return "court"
    if re.search(r"지방공사|지방공단|지방직영기업", compact):
        return "local_public_enterprise"
    if re.search(r"공사|공단|공공기관|출연기관|재단", compact):
        return "public_institution"
    if re.search(r"사무처|사무국|사무기구|지원단", compact):
        return "support_office"
    return "unknown"


def _court_transition(text: str) -> str:
    """Return the statutory court-level transition without using region names.

    A city/county court becoming a branch and a branch becoming a district
    court both contain the broad words ``법원`` and ``신설`` but have different
    staffing structures. Preserve that hierarchy before semantic ranking.
    """
    compact = _normalise(text)
    if not re.search(r"고등법원|지방법원|가정법원|지원|시법원|군법원", compact):
        return ""

    # Explicit promotion language is the strongest source-side evidence.
    if re.search(
        r"[가-힣]{2,12}지원(?:을|를)?.{0,80}"
        r"(?:[가-힣]{2,12}지방법원.{0,30}승격|승격.{0,30}[가-힣]{2,12}지방법원)",
        compact,
    ):
        return "branch_to_district"

    # Some official reports describe the same transition as a new district
    # court plus abolition of the same-named branch.
    if (
        re.search(
            r"([가-힣]{2,12})지방법원.{0,100}(?:신설|설치).{0,220}"
            r"(?:현행|현)?(?:[가-힣]{2,12}지방법원소속)?\1지원.{0,80}폐지",
            compact,
        )
        or re.search(
            r"(?:현행|현)?(?:[가-힣]{2,12}지방법원소속)?([가-힣]{2,12})지원"
            r".{0,80}폐지.{0,220}\1지방법원.{0,100}(?:신설|설치)",
            compact,
        )
    ):
        return "branch_to_district"

    if (
        re.search(
            r"([가-힣]{2,12})(?:시|군)법원.{0,100}폐지.{0,220}"
            r"\1지원.{0,100}(?:신설|설치)",
            compact,
        )
        or re.search(
            r"([가-힣]{2,12})지원.{0,100}(?:신설|설치).{0,220}"
            r"\1(?:시|군)법원.{0,100}폐지",
            compact,
        )
    ):
        return "local_court_to_branch"

    if re.search(r"고등법원.{0,100}(?:신설|설치)", compact):
        return "new_high_court"
    if re.search(r"지방법원.{0,100}(?:신설|설치)", compact):
        return "new_district_court"
    if re.search(r"(?:가정법원|[가-힣]{2,12}지원).{0,100}(?:신설|설치)", compact):
        return "new_branch_or_family_court"
    return ""


def _prefer_same_court_transition(
    target_text: str,
    cases: list[OrganizationCase],
) -> list[OrganizationCase]:
    """Keep the same court hierarchy transition when such precedents exist."""
    target_transition = _court_transition(target_text)
    if not target_transition:
        return cases
    same_transition = [
        case
        for case in cases
        if _court_transition(f"{case.bill_name}\n{case.context}") == target_transition
    ]
    return same_transition or cases


def _case_organization_form(case: OrganizationCase) -> str:
    """Classify a precedent by its priced subject before its full narrative.

    Companion-bill reports can mention several related organizations.  The
    repeated subject in the actual cost-item labels is the less contaminated
    signal for deciding whether the priced case is a committee, support office,
    court, or another organization form.
    """
    item_labels = _normalise(
        " ".join(item.item_name for _, item in case.items if item.item_name)
    )
    context_form = _organization_form(case.context)
    if (
        context_form == "legislative_committee"
        and re.search(r"사무처|사무국|사무기구|지원단", item_labels)
    ):
        return "support_office"
    return context_form


def _bundle_organization_form(
    item: TagCandidate,
    context: str,
) -> str:
    """Classify a bundled row from its priced subject before its narrative."""
    priced_form = _organization_form(item.item_name)
    return (
        priced_form
        if priced_form != "unknown"
        else _organization_form(context)
    )


def _case_personnel_system_from_priced_subject(
    case: OrganizationCase,
) -> str:
    """Classify the employer from priced personnel evidence, not boilerplate."""
    personnel_parts: list[str] = []
    for component, item in case.items:
        if component != "personnel":
            continue
        personnel_parts.extend(
            [
                item.item_name,
                item.formula,
                *[
                    str(variable.get("name") or "")
                    for variable in item.variables
                ],
                *[
                    str(variable.get("source_text") or "")
                    for variable in item.variables
                ],
            ]
        )
    evidence = _normalise(
        f"{case.bill_name}\n{case.context[:2_000]}\n{' '.join(personnel_parts)}"
    ).replace("국회예산정책처", "")

    if re.search(r"법원|대법원|법관|판사|사법부|사법행정", evidence):
        return "judicial"
    if re.search(r"헌법재판소|헌법재판관", evidence):
        return "constitutional_court"
    if re.search(r"국회법|국회사무처|입법조사관|전문위원", evidence):
        return "legislative"
    if re.search(r"지방자치단체|지방의회|지방공무원|시·군의원", evidence):
        return "local_government"
    if re.search(
        r"공공기관|공단|출연기관|재단"
        r"|(?:한국|지방|농수산식품유통)[가-힣]{0,24}공사"
        r"|정규직|직원평균보수",
        evidence,
    ):
        return "public_institution"
    if re.search(
        r"중앙행정기관|국무총리|정부조직|장관|국가인권위원회"
        r"|고위공직자범죄수사처|국가공무원|공무원임금",
        evidence,
    ):
        return "central_government"
    return "unknown"


def _is_creation_context(text: str, form: str) -> bool:
    compact = _normalise(text)
    anchors = {
        "legislative_committee": r"상임위원회|특별위원회|법제위원회",
        "special_local_government": r"특별지방자치단체|메가시티",
        "court": r"고등법원|지방법원|가정법원|법원지원",
        "local_public_enterprise": r"지방공사|지방공단|지방직영기업",
        "public_institution": r"공사|공단|공공기관|출연기관|재단",
        "support_office": r"사무처|사무국|사무기구|지원단",
    }
    anchor = anchors.get(form)
    if not anchor:
        return False
    return bool(
        re.search(rf"(?:{anchor}).{{0,120}}(?:설치|설립|신설|둔다)", compact)
        or re.search(rf"(?:설치|설립|신설).{{0,120}}(?:{anchor})", compact)
    )


@lru_cache(maxsize=1)
def _all_typed_structure_cases() -> tuple[tuple[str, OrganizationCase], ...]:
    """Index organization-form evidence independently from priced completeness."""
    data = tag_db._load()
    formulas = tag_db._formula_by_item()
    amounts = _amount_rows()
    contexts = _cost_estimate_contexts()
    grouped: dict[str, list[tuple[str, TagCandidate]]] = defaultdict(list)
    metadata: dict[str, tuple[str, str]] = {}

    for item_id, meta in data["items"].items():
        bill_no = str(meta.get("bill_no") or "")
        if not bill_no:
            continue
        item = TagCandidate(
            item_id=item_id,
            bill_no=bill_no,
            bill_name=str(meta.get("bill_name") or ""),
            item_name=str(meta.get("name") or ""),
            category=str(meta.get("category") or ""),
            family=str(meta.get("family") or ""),
            similarity=0.0,
            variables=data["vars"].get(item_id, []),
            amounts=amounts.get(item_id, []),
            formula=formulas.get(item_id, ""),
        )
        component = _component(item)
        grouped[bill_no].append((component, item))
        metadata[bill_no] = (
            item.bill_name,
            str(meta.get("propose_date") or ""),
        )

    cases: list[tuple[str, OrganizationCase]] = []
    for bill_no, items in grouped.items():
        context = contexts.get(bill_no, "")
        provisional = OrganizationCase(
            bill_no=bill_no,
            bill_name=metadata[bill_no][0],
            propose_date=metadata[bill_no][1],
            context=context,
            items=items,
        )
        form = _case_organization_form(provisional)
        if form == "unknown" or not _is_creation_context(context, form):
            continue
        bill_name, propose_date = metadata[bill_no]
        cases.append(
            (
                form,
                OrganizationCase(
                    bill_no=bill_no,
                    bill_name=bill_name,
                    propose_date=propose_date,
                    context=context,
                    items=items,
                ),
            )
        )
    return tuple(cases)


def select_typed_structure_case(
    target_context: str,
    *,
    exclude_bill_nos: set[str],
    cutoff_date: str | None,
) -> tuple[OrganizationCase | None, str, float]:
    """Use an exact legal organization form only when it yields one precedent."""
    form = _organization_form(target_context)
    if form == "unknown" or not _is_creation_context(target_context, form):
        return None, "대상 조문에서 확정적인 조직 법형식을 추출하지 못했습니다.", 0.0
    excluded = {str(value) for value in exclude_bill_nos if value}
    candidates = [
        case
        for candidate_form, case in _all_typed_structure_cases()
        if candidate_form == form
        and case.bill_no not in excluded
        and not (
            cutoff_date
            and case.propose_date
            and case.propose_date > cutoff_date
        )
    ]
    if len(candidates) != 1:
        return (
            None,
            f"같은 조직 법형식({form})의 신설 선례가 {len(candidates)}건이므로 "
            "법형식만으로 임의 선택하지 않았습니다.",
            0.0,
        )
    selected = candidates[0]
    return (
        selected,
        f"금액과 명칭 유사도가 아니라 같은 조직 법형식({form})과 신설 행위가 "
        f"확인되는 유일한 선례 {selected.bill_no}을 구조 근거로 선택했습니다.",
        0.9,
    )


@lru_cache(maxsize=1)
def _all_staff_cost_bundles() -> tuple[StaffCostBundleCase, ...]:
    """Index coherent compound staff-cost rows from every TAG bill."""
    data = tag_db._load()
    formulas = tag_db._formula_by_item()
    amounts = _amount_rows()
    contexts = _cost_estimate_contexts()
    bundles: list[StaffCostBundleCase] = []
    required_roles = set(_STAFF_BUNDLE_ROLE_PATTERNS)

    for item_id, meta in data["items"].items():
        item = TagCandidate(
            item_id=item_id,
            bill_no=str(meta.get("bill_no") or ""),
            bill_name=str(meta.get("bill_name") or ""),
            item_name=str(meta.get("name") or ""),
            category=str(meta.get("category") or ""),
            family=str(meta.get("family") or ""),
            similarity=0.0,
            variables=data["vars"].get(item_id, []),
            amounts=amounts.get(item_id, []),
            formula=formulas.get(item_id, ""),
        )
        staff_count = _single_staff_denominator(item)
        if not staff_count or _staff_bundle_roles(item) != required_roles:
            continue
        if _coherent_bundle_series(item, 5) is None:
            continue
        context = contexts.get(item.bill_no, "")
        if not context:
            continue
        system = _personnel_system(
            f"{item.bill_name}\n{item.item_name}\n{context[:4_000]}"
        )
        if system == "unknown":
            continue
        bundles.append(
            StaffCostBundleCase(
                item=item,
                propose_date=str(meta.get("propose_date") or ""),
                context=context,
                staff_count=staff_count,
                personnel_system=system,
                organization_form=_bundle_organization_form(item, context),
            )
        )
    return tuple(
        sorted(
            bundles,
            key=lambda bundle: (
                bundle.propose_date,
                bundle.item.bill_no,
                bundle.item.item_id,
            ),
        )
    )


def select_staff_cost_bundle(
    query: str,
    target_context: str,
    *,
    exclude_bill_nos: set[str],
    cutoff_date: str | None,
    years: int,
    refresh: bool = False,
) -> tuple[StaffCostBundleCase | None, str, float]:
    """Choose one coherent bundle after a hard personnel-system gate.

    The gate is deterministic and amount-blind.  Embeddings rank multiple
    candidates only inside the same pay/budget system.  Legal form is a strong
    preference, not a hard value gate: structure selection already decides the
    target's legal form, while a complete per-person payroll bundle can be
    transferred across forms that share the same statutory pay/budget system.
    When embeddings are unavailable and more than one compatible bundle
    remains, the engine asks for evidence instead of falling back to Korean
    token overlap.
    """
    target_system = _personnel_system(target_context)
    target_form = _organization_form(target_context)
    excluded = {str(value) for value in exclude_bill_nos if value}
    compatible = [
        bundle
        for bundle in _all_staff_cost_bundles()
        if bundle.item.bill_no not in excluded
        and bundle.personnel_system == target_system
        and not (
            cutoff_date
            and bundle.propose_date
            and bundle.propose_date > cutoff_date
        )
        and _coherent_bundle_series(bundle.item, years) is not None
    ]
    cross_form_fallback = False
    if target_form != "unknown":
        same_form = [
            bundle
            for bundle in compatible
            if bundle.organization_form == target_form
        ]
        if same_form:
            compatible = same_form
        elif compatible:
            cross_form_fallback = True
    if not compatible:
        return (
            None,
            f"대상 인사·예산 체계({target_system})와 같은 완결 인력비 묶음 선례가 없습니다.",
            0.0,
        )
    if len(compatible) == 1:
        selected = compatible[0]
        selected.item.similarity = 1.0
        form_basis = (
            f"같은 조직 법형식({target_form})"
            if not cross_form_fallback and target_form != "unknown"
            else "같은 법형식 선례가 없어 구조는 별도 선례로 판단하고"
        )
        return (
            selected,
            f"같은 인사·예산 체계({target_system})와 {form_basis}, "
            "보수·기관부담금·기본경비·"
            f"자산취득비와 인원 분모가 한 행에 완결된 유일한 선례 "
            f"{selected.item.bill_no}을 선택했습니다.",
            0.82 if cross_form_fallback else 0.9,
        )

    query_vector = _query_embedding(query, refresh=refresh)
    embeddings = tag_db._load_embeddings()
    if not query_vector:
        return (
            None,
            f"같은 인사·예산 체계({target_system})의 완결 선례가 {len(compatible)}건이나 "
            "의미 임베딩을 사용할 수 없어 임의 선택하지 않았습니다.",
            0.0,
        )
    scored: list[StaffCostBundleCase] = []
    for bundle in compatible:
        vector = embeddings.get(bundle.item.item_id)
        if not vector:
            continue
        similarity = tag_db._cosine(query_vector, vector)
        scored.append(
            StaffCostBundleCase(
                item=bundle.item,
                propose_date=bundle.propose_date,
                context=bundle.context,
                staff_count=bundle.staff_count,
                personnel_system=bundle.personnel_system,
                organization_form=bundle.organization_form,
                similarity=similarity,
            )
        )
    if not scored:
        return (
            None,
            "호환 선례는 있지만 캐시된 의미 벡터가 없어 임의 선택하지 않았습니다.",
            0.0,
        )
    scored.sort(
        key=lambda bundle: (
            -bundle.similarity,
            bundle.propose_date,
            bundle.item.bill_no,
        )
    )
    selected = scored[0]
    selected.item.similarity = selected.similarity
    form_basis = (
        f"같은 법형식({target_form}) 후보"
        if not cross_form_fallback and target_form != "unknown"
        else "같은 법형식이 없어 구조 선례와 분리한 값 후보"
    )
    return (
        selected,
        f"같은 인사·예산 체계({target_system})의 {form_basis} 안에서 "
        "금액을 보지 않고 "
        f"의미유사도 {selected.similarity:.4f}가 가장 높은 "
        f"{selected.item.bill_no}을 선택했습니다.",
        min(
            0.9 if cross_form_fallback else 0.95,
            max(0.65, selected.similarity),
        ),
    )


@lru_cache(maxsize=1)
def _all_complete_cases() -> tuple[OrganizationCase, ...]:
    data = tag_db._load()
    formulas = tag_db._formula_by_item()
    amounts = _amount_rows()
    contexts = _cost_estimate_contexts()
    grouped: dict[str, list[tuple[str, TagCandidate]]] = defaultdict(list)
    metadata: dict[str, tuple[str, str, str]] = {}

    for item_id, meta in data["items"].items():
        bill_no = str(meta.get("bill_no") or "")
        if not bill_no:
            continue
        item = TagCandidate(
            item_id=item_id,
            bill_no=bill_no,
            bill_name=str(meta.get("bill_name") or ""),
            item_name=str(meta.get("name") or ""),
            category=str(meta.get("category") or ""),
            family=str(meta.get("family") or ""),
            similarity=0.0,
            variables=data["vars"].get(item_id, []),
            amounts=amounts.get(item_id, []),
            formula=formulas.get(item_id, ""),
        )
        component = _component(item)
        if not component or not _has_positive_amount(item):
            continue
        grouped[bill_no].append((component, item))
        metadata[bill_no] = (
            item.bill_name,
            str(meta.get("propose_date") or ""),
            contexts.get(bill_no, ""),
        )

    cases: list[OrganizationCase] = []
    for bill_no, items in grouped.items():
        components = {component for component, _ in items}
        # An organization precedent must expose a personnel base and at least
        # three core components.  Committee totals or one-off staff items do
        # not enter this channel merely because their labels contain "설치".
        if "personnel" not in components or len(components & _COMPLETE_COMPONENTS) < 3:
            continue
        bill_name, propose_date, context = metadata[bill_no]
        if not context:
            continue
        cases.append(
            OrganizationCase(
                bill_no=bill_no,
                bill_name=bill_name,
                propose_date=propose_date,
                context=context,
                items=items,
            )
        )
    return tuple(sorted(cases, key=lambda case: (case.propose_date, case.bill_no)))


def _case_embedding_text(case: OrganizationCase) -> str:
    item_structure = "\n".join(
        f"{component}: {item.item_name} / {item.formula}"
        for component, item in case.items
    )
    # Korean text can consume several tokens per visible character.  A 5,000
    # character case occasionally exceeded the per-input embedding limit even
    # though an ordinary short connectivity probe succeeded.  Structural
    # labels carry most of the retrieval signal, so keep each input
    # conservatively below the ceiling.
    return f"{case.bill_name}\n{case.context[:1_400]}\n비용항목 구조:\n{item_structure}"[:2_000]


def _case_embeddings(cases: list[OrganizationCase], *, refresh: bool) -> dict[str, list[float]]:
    texts = {case.bill_no: _case_embedding_text(case) for case in cases}

    def producer() -> dict[str, list[float]] | None:
        bill_nos = list(texts)
        # The embedding endpoint also caps aggregate tokens per request.
        # Chunking prevents a large precedent pool from failing as one giant
        # batch and then retrying every document individually.
        vectors: list[list[float] | None] = []
        for start in range(0, len(bill_nos), 16):
            batch_bill_nos = bill_nos[start:start + 16]
            vectors.extend(embed_batch([texts[bill_no] for bill_no in batch_bill_nos]))
        result = {
            bill_no: vector
            for bill_no, vector in zip(bill_nos, vectors)
            if isinstance(vector, list) and vector
        }
        return result or None

    value, _ = get_or_create_json(
        "organization_case_embeddings",
        {
            "version": ORGANIZATION_RETRIEVAL_VERSION,
            "model": OPENAI_EMBED_MODEL,
            "texts": {bill_no: stable_hash(text) for bill_no, text in texts.items()},
        },
        producer,
        refresh=refresh,
    )
    return value if isinstance(value, dict) else {}


def _query_embedding(query: str, *, refresh: bool) -> list[float] | None:
    def producer() -> list[float] | None:
        vectors = embed_batch([query[:2_000]])
        return vectors[0] if vectors and isinstance(vectors[0], list) else None

    value, _ = get_or_create_json(
        "organization_query_embeddings",
        {
            "version": ORGANIZATION_RETRIEVAL_VERSION,
            "model": OPENAI_EMBED_MODEL,
            "query": query,
        },
        producer,
        refresh=refresh,
    )
    return value if isinstance(value, list) else None


def search_organization_cases(
    query: str,
    *,
    exclude_bill_nos: set[str],
    cutoff_date: str | None,
    refresh: bool = False,
    k: int = _ORGANIZATION_RECALL_K,
) -> list[OrganizationCase]:
    """Retrieve complete organization cases with embedding similarity only.

    Unlike generic TAG retrieval, the same governing law is allowed here:
    another institution established under the same organization statute is
    often the strongest structural precedent.  Exact target bills and future
    cases remain excluded.
    """
    excluded = {str(value) for value in exclude_bill_nos if value}
    cases = [
        case
        for case in _all_complete_cases()
        if case.bill_no not in excluded
        and not (cutoff_date and case.propose_date and case.propose_date > cutoff_date)
    ]
    if not cases:
        return []
    query_vector = _query_embedding(query, refresh=refresh)
    embeddings = _case_embeddings(cases, refresh=refresh)
    if not query_vector or not embeddings:
        return []

    scored: list[OrganizationCase] = []
    for case in cases:
        vector = embeddings.get(case.bill_no)
        if not vector:
            continue
        scored.append(
            OrganizationCase(
                bill_no=case.bill_no,
                bill_name=case.bill_name,
                propose_date=case.propose_date,
                context=case.context,
                items=case.items,
                similarity=round(tag_db._cosine(query_vector, vector), 4),
            )
        )
    scored.sort(key=lambda case: (-case.similarity, case.bill_no))
    return scored[:k]


_SELECTION_PROMPT = """당신은 공공조직 신설·승격 비용추계 선례를 고르는 심사자다.
대상 법안의 정답 금액은 제공되지 않는다. 후보 금액의 크기가 아니라 다음 구조만 비교해
준용할 공식 선례를 정확히 하나 고른다.

우선순위:
1. 조직 변화가 완전 신설인지, 기존 하위조직의 승격인지, 분리·이관인지
2. 상설 조직인지 한시 조직인지가 같은지. 상설 조직에 활동기간이 정해진 한시 선례를 고르지 마라.
3. 같은 상위기관·인사체계에 속하는지, 기관의 기능과 조직 단계가 같은지
4. 목표 규모를 정하는 기준이 인구·업무량·유사기관 중 무엇인지
5. 기존 인력·전입·재배치·기존 시설을 차감하는 추가성 구조가 같은지
6. 인건비·기관부담금·기본경비·자산취득비 항목이 한 사례 안에서 완결되는지

금지:
- 법률명이나 지역명 한 단어가 겹친다는 이유로 고르지 마라.
- 후보 금액을 평균·중앙값으로 섞지 마라.
- 기관 단계가 다른 고등법원/지방법원/지원 사례를 동일하게 취급하지 마라.
- 모든 후보가 부적합하면 bill_no를 빈 문자열로 반환하라.

JSON만 반환한다:
{"bill_no":"의안번호","reason":"구조 선택 근거","confidence":0.0}
"""


_VALUE_SELECTION_PROMPT = """당신은 공공조직 비용추계의 '값 선례 후보군'을 분류하는 심사자다.
대상 정답 금액은 제공되지 않으며 후보 금액이 정답에 가까운지는 절대 판단 기준이 아니다.
후보의 한 비용항목 안에 있는 산식·변수·연도별 계열은 그대로 묶어서 사용한다.

당신의 역할은 최종 1위를 정하는 것이 아니라 다음 계층에서 가장 가까운 호환 후보군만 반환하는 것이다.
1. 대상과 같은 상위기관·예산·인사·보수 체계의 후보가 하나라도 있으면 그 후보들만 포함한다.
2. 1이 전혀 없을 때만 같은 공무원·보수체계와 비슷한 직급·직무 구성의 후보를 포함한다.
3. 상설/한시 수명주기, 5개년 계열, 인원 분모가 호환되지 않는 후보는 제외한다.
4. 후보군 안의 최종 순위는 코드가 의미유사도와 제안일로 결정하므로 당신은 순위를 정하지 않는다.
5. 대상 조문이 '기존 직원 중 지정'처럼 순증 인원을 확정하지 않는 경우에도, 같은
   인사·보수 체계의 인력비 선례는 **사용자가 순증 인원을 확인했을 때 적용할 조건부
   값 선례**로 포함한다. 후보 선택은 신규채용을 가정하는 행위가 아니며, 대상 순증
   인원은 별도의 HITL 입력으로 남는다.

금지:
- 일반 국가공무원이라는 이유만으로 같은 상위기관의 직접 선례와 한 후보군에 섞지 마라.
- 신설·승격·분리 같은 조직변경 모양은 구조 선례의 기준이지 값 선례의 유일한 기준이 아니다.
- 후보 금액의 평균·중앙값을 만들거나 여러 의안의 변수를 한 항목 안에서 섞지 마라.
- 모든 후보가 부적합하면 compatible_bill_nos를 빈 배열로 반환하라.

JSON만 반환한다:
{"compatible_bill_nos":["의안번호"],"reason":"호환 후보군 근거","confidence":0.0}
"""


def _selection_candidate_payload(case: OrganizationCase) -> dict[str, Any]:
    return {
        "bill_no": case.bill_no,
        "bill_name": case.bill_name,
        "propose_date": case.propose_date,
        "embedding_similarity": case.similarity,
        # Broad recall prevents a relevant precedent from disappearing behind
        # an arbitrary top-8 cut.  Keep each narrative compact so the selector
        # can compare more cases without a proportional token explosion.
        "precedent_context": case.context[:2_000],
        "components": [
            {
                "component": component,
                "item_name": item.item_name,
                "formula": item.formula,
                "variables": [
                    {
                        "type": variable.get("type"),
                        "name": variable.get("name"),
                        "unit": variable.get("unit"),
                    }
                    for variable in item.variables
                ],
            }
            for component, item in case.items
        ],
    }


def select_organization_case(
    query: str,
    events: list[AtomicEvent],
    cases: list[OrganizationCase],
    *,
    refresh: bool = False,
) -> tuple[OrganizationCase | None, str, float, bool]:
    if not cases:
        return None, "완결된 조직변경 의미 선례를 검색하지 못했습니다.", 0.0, False
    target_transition = _court_transition(query)
    if (
        target_transition
        and len(cases) == 1
        and _court_transition(f"{cases[0].bill_name}\n{cases[0].context}")
        == target_transition
    ):
        selected = cases[0]
        return (
            selected,
            f"같은 법원 조직단계 전환({target_transition})과 완결 비용항목을 "
            f"가진 유일한 과거 선례 {selected.bill_no}을 구조 근거로 "
            "결정적으로 선택했습니다.",
            0.95,
            False,
        )
    candidate_payload = [_selection_candidate_payload(case) for case in cases]
    payload = {
        "version": ORGANIZATION_STRUCTURE_SELECTION_VERSION,
        "model": GEMINI_MODEL,
        "target_events": [asdict(event) for event in events],
        "target_source": query[:8_000],
        "candidates": candidate_payload,
    }
    prompt = _SELECTION_PROMPT + "\n대상:\n" + json.dumps(
        {
            "events": payload["target_events"],
            "source": payload["target_source"],
            "candidates": candidate_payload,
        },
        ensure_ascii=False,
    )
    result, cache_hit = get_or_create_json(
        "organization_case_selection",
        payload,
        lambda: gemini_json(prompt, temperature=0.0),
        refresh=refresh,
    )
    result = result if isinstance(result, dict) else {}
    selected_no = str(result.get("bill_no") or "")
    selected = next((case for case in cases if case.bill_no == selected_no), None)
    reason = str(result.get("reason") or "")
    try:
        confidence = max(0.0, min(1.0, float(result.get("confidence") or 0)))
    except (TypeError, ValueError):
        confidence = 0.0
    if selected is None or confidence < 0.65:
        return (
            None,
            reason or "조직 변화 구조가 충분히 가까운 단일 선례를 확정하지 못했습니다.",
            confidence,
            cache_hit,
        )
    return selected, reason, confidence, cache_hit


def find_organization_clusters(events: list[AtomicEvent]) -> list[list[AtomicEvent]]:
    """Find LLM events that describe two cost aspects of one organization change."""
    standalone = [
        [event]
        for event in events
        if event.grounded
        and (
            event.event_type == EventType.ORGANIZATION.value
            or _is_legislative_committee_organization_event(event)
            or _is_dedicated_staff_designation_event(event)
        )
        and event.obligation in {"mandatory", "semi_mandatory"}
        and event.additionality in {"explicit_new_or_expanded", "possibly_incremental"}
    ]
    groups: dict[tuple[tuple[str, ...], str, str], list[AtomicEvent]] = defaultdict(list)
    for event in events:
        if not event.grounded or event.obligation not in {"mandatory", "semi_mandatory"}:
            continue
        if event.additionality not in {"explicit_new_or_expanded", "possibly_incremental"}:
            continue
        if event.event_type not in {EventType.PERSONNEL.value, EventType.FACILITY_SYSTEM.value}:
            continue
        key = (tuple(sorted(event.segment_ids)), event.actor, event.bearer)
        groups[key].append(event)
    legacy_pairs = [
        group
        for group in groups.values()
        if {event.event_type for event in group}
        >= {EventType.PERSONNEL.value, EventType.FACILITY_SYSTEM.value}
    ]
    return [*standalone, *legacy_pairs]


def _is_legislative_committee_organization_event(event: AtomicEvent) -> bool:
    """Route a parliamentary organizational committee away from meeting allowances.

    The gate deliberately inspects the structured actor/object contract rather
    than searching the entire bill for the word ``위원회``.  Advisory councils
    under the National Assembly therefore remain in the ordinary committee
    channel, while a statutory standing/special committee enters the
    organization-and-staffing channel.
    """
    if event.event_type != EventType.COMMITTEE.value:
        return False
    if event.obligation not in {"mandatory", "semi_mandatory"}:
        return False
    if event.additionality not in {
        "explicit_new_or_expanded",
        "possibly_incremental",
    }:
        return False
    actor_context = _normalise(
        " ".join([event.actor, event.bearer, event.explanation])
    )
    target_object = _normalise(event.object)
    return bool(
        re.search(r"국회|국회의원|입법", actor_context)
        and re.search(r"상임위원회|특별위원회|법제위원회", target_object)
    )


def _is_dedicated_staff_designation_event(event: AtomicEvent) -> bool:
    """Route a mandatory dedicated-officer role into the staffing value channel.

    Designating an existing employee does not by itself prove a net increase.
    The channel therefore retrieves a coherent staff-cost precedent but keeps
    the target net headcount as HITL rather than turning the statutory role into
    an invented hire.  The detector occasionally labels a role's work as
    ``committee_operation`` because the surrounding paragraph contains
    governance language; the role itself must still enter the organization
    channel when the source says that an employee is designated/appointed.
    """
    if event.event_type not in {
        EventType.ADMINISTRATIVE.value,
        EventType.PERSONNEL.value,
        EventType.COMMITTEE.value,
    }:
        return False
    if event.obligation not in {"mandatory", "semi_mandatory"}:
        return False
    if event.bearer not in {"state", "local", "public_institution"}:
        return False
    target_object = _normalise(event.object)
    action = _normalise(event.action)
    source_text = _normalise(" ".join(event.quotes))
    role_match = re.search(
        r"담당관|전담인력|전문인력|전담담당자",
        target_object,
    )
    designation_match = re.search(
        r"지정|임명|배치|채용|둔다",
        action,
    ) or re.search(
        r"소속직원.{0,80}(?:지정|임명|배치|채용)|"
        r"(?:담당관|전담인력|전문인력).{0,50}(?:지정|임명|배치|채용)",
        source_text,
    )
    return bool(
        role_match
        and designation_match
    )


def _series(item: TagCandidate, years: int) -> list[int | None]:
    by_offset = {
        int(row["year_offset"]): int(row.get("amount_thousand") or 0)
        for row in item.amounts
        if row.get("year_offset") is not None and int(row["year_offset"]) >= 0
    }
    return [by_offset.get(index, 0) for index in range(years)]


def _precedent_staff_count(case: OrganizationCase) -> int | None:
    """Return the coherent personnel denominator from the selected case."""
    for component, item in case.items:
        if component != "personnel":
            continue
        for variable in item.variables:
            if variable.get("type") != "target_count":
                continue
            if str(variable.get("unit") or "") != "명":
                continue
            try:
                value = int(round(float(variable.get("value"))))
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
    return None


def _item_staff_count(
    case: OrganizationCase,
    component: str,
    item: TagCandidate,
) -> int | None:
    """Find the denominator that belongs to one value item.

    The item-local count wins.  Basic expenses often omit their denominator,
    so the same case's asset headcount is the next-best complete evidence,
    followed by the personnel count.  Counts are never taken from another bill.
    """
    for variable in item.variables:
        if variable.get("type") != "target_count" or str(variable.get("unit") or "") != "명":
            continue
        try:
            value = int(round(float(variable.get("value"))))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    if component in {"basic_expense", "employer_contribution"}:
        for fallback_component in ("asset", "personnel"):
            for candidate_component, candidate_item in case.items:
                if candidate_component != fallback_component:
                    continue
                value = _item_staff_count(case, candidate_component, candidate_item)
                if value:
                    return value
    return _precedent_staff_count(case)


_LIMITED_ORGANIZATION_PATTERN = re.compile(
    r"(?:한시(?:적|조직)?|존속\s*기간|활동\s*기간|업무\s*종료|기간\s*만료|해산)"
)


def _target_organization_is_limited(
    events: list[AtomicEvent],
    source_text: str = "",
) -> bool:
    """Classify lifecycle from the organization event only, not unrelated articles."""
    evidence = " ".join(
        [
            *[quote for event in events for quote in event.quotes],
            *[event.recurrence_text for event in events],
            *[event.explanation for event in events],
            source_text,
        ]
    )
    return bool(_LIMITED_ORGANIZATION_PATTERN.search(evidence))


def _case_is_limited(case: OrganizationCase, years: int) -> bool:
    """Require both explicit lifecycle evidence and a truncated personnel series."""
    personnel = next(
        (item for component, item in case.items if component == "personnel"),
        None,
    )
    if personnel is None:
        return False
    positive_years = sum(1 for value in _series(personnel, years) if (value or 0) > 0)
    return (
        positive_years < years
        and bool(_LIMITED_ORGANIZATION_PATTERN.search(case.context))
    )


def _eligible_organization_value_cases(
    events: list[AtomicEvent],
    cases: list[OrganizationCase],
    years: int,
    target_source_text: str = "",
) -> list[OrganizationCase]:
    target_is_limited = _target_organization_is_limited(
        events,
        target_source_text,
    )
    eligible: list[OrganizationCase] = []
    for case in cases:
        components = {component for component, _ in case.items}
        if not {"personnel", "basic_expense", "asset"}.issubset(components):
            continue
        if not _precedent_staff_count(case):
            continue
        # Copying a two-year liquidation curve into a permanent organization
        # turns years 3-5 into zero; copying a permanent five-year curve into
        # a temporary organization does the opposite. Require symmetric
        # lifecycle compatibility before any semantic ranking.
        if target_is_limited != _case_is_limited(case, years):
            continue
        eligible.append(case)
    return eligible


def _restrict_legislative_committee_value_cases(
    events: list[AtomicEvent],
    cases: list[OrganizationCase],
) -> list[OrganizationCase]:
    """Prefer the same statutory organization form over a nearby organization.

    Organizations can share one pay system while having non-transferable staff
    compositions and operating bases.  When a same-form complete precedent is
    available, keep the value search inside that legal form.  The historical
    function name remains for cache/test compatibility.
    """
    target_form = _organization_form(_cluster_context(events))
    if target_form == "unknown":
        return cases
    same_form = [
        case
        for case in cases
        if _case_organization_form(case) == target_form
    ]
    return same_form or cases


def _value_candidate_payload(case: OrganizationCase, years: int) -> dict[str, Any]:
    payload = _selection_candidate_payload(case)
    payload["limited_lifecycle"] = _case_is_limited(case, years)
    payload["value_items"] = [
        {
            "component": component,
            "item_name": item.item_name,
            "formula": item.formula,
            "variables": item.variables,
            "yearly_amount_presence": [
                value is not None and value > 0 for value in _series(item, years)
            ],
        }
        for component, item in case.items
        if component in _VALUE_COMPONENTS
    ]
    return payload


def _top_compatible_value_case(
    cases: list[OrganizationCase],
    compatible_bill_nos: list[str],
) -> OrganizationCase | None:
    compatible = {
        str(bill_no) for bill_no in compatible_bill_nos if str(bill_no)
    }
    candidates = [case for case in cases if case.bill_no in compatible]
    if not candidates:
        return None
    # Embedding similarity is deterministic from the cached vectors.  Date is
    # only a tie-breaker so a newer rate table wins when semantics are equal.
    return max(
        candidates,
        key=lambda case: (case.similarity, case.propose_date, case.bill_no),
    )


def _case_personnel_rate_basis_year(case: OrganizationCase) -> int:
    """Return the newest explicit base year attached to personnel pay evidence."""
    years: list[int] = []
    for component, item in case.items:
        if component != "personnel":
            continue
        evidence = " ".join(
            [
                item.item_name,
                item.formula,
                *[
                    str(variable.get("name") or "")
                    for variable in item.variables
                ],
                *[
                    str(variable.get("source_text") or "")
                    for variable in item.variables
                ],
            ]
        )
        for match in re.finditer(
            r"(20\d{2})년\s*기준.{0,100}(?:연봉|보수)"
            r"|(?:연봉|보수).{0,100}(20\d{2})년\s*기준",
            evidence,
        ):
            raw = match.group(1) or match.group(2)
            if raw:
                years.append(int(raw))
    return max(years, default=0)


def _latest_judicial_value_case(
    events: list[AtomicEvent],
    cases: list[OrganizationCase],
) -> OrganizationCase | None:
    """Choose the freshest prior court pay evidence independently of structure.

    Courts share one statutory personnel and pay system.  A same-transition
    case is the right formula precedent, but its old monetary series need not
    be the best value basis.  This selector remains amount-blind and uses only
    legal form, personnel system, explicit pay base year and proposal date.
    """
    target_context = _cluster_context(events)
    if (
        _organization_form(target_context) != "court"
        or _personnel_system(target_context) != "judicial"
    ):
        return None
    compatible = [
        case
        for case in cases
        if _case_organization_form(case) == "court"
        and _case_personnel_system_from_priced_subject(case) == "judicial"
    ]
    if not compatible:
        return None
    return max(
        compatible,
        key=lambda case: (
            _case_personnel_rate_basis_year(case),
            case.propose_date,
            case.similarity,
            case.bill_no,
        ),
    )


def select_organization_value_case(
    query: str,
    events: list[AtomicEvent],
    cases: list[OrganizationCase],
    *,
    years: int,
    target_source_text: str = "",
    refresh: bool = False,
) -> tuple[OrganizationCase | None, str, float, bool]:
    """Select values independently from structure, with lifecycle compatibility."""
    eligible = _eligible_organization_value_cases(
        events,
        cases,
        years,
        target_source_text,
    )
    eligible = _restrict_legislative_committee_value_cases(events, eligible)
    if not eligible:
        return None, "수명주기와 인원 분모가 호환되는 완결 값 선례가 없습니다.", 0.0, False
    judicial_value_case = _latest_judicial_value_case(events, eligible)
    if judicial_value_case is not None:
        basis_year = _case_personnel_rate_basis_year(judicial_value_case)
        return (
            judicial_value_case,
            f"구조 선례와 금액 기준을 분리했습니다. 같은 법원 인사·보수체계의 "
            f"과거 완결 선례 중 금액을 보지 않고 보수 기준연도"
            f"({basis_year or '미상'})와 제안일이 가장 최신인 "
            f"{judicial_value_case.bill_no}을 값 기준으로 선택했습니다.",
            0.85,
            False,
        )
    target_form = _organization_form(_cluster_context(events))
    if use_unique_prequalified_organization_value(
        LLM_PROFILE,
        candidate_count=len(eligible),
        target_organization_form=target_form,
    ):
        selected = eligible[0]
        return (
            selected,
            f"완결 비용항목·인원 분모·수명주기·법형식의 결정적 호환 조건을 "
            f"통과한 유일한 값 선례 {selected.bill_no}을 선택했습니다. "
            "후보가 한 건이므로 모델 재판정은 생략했습니다.",
            0.9,
            False,
        )
    candidate_payload = [_value_candidate_payload(case, years) for case in eligible]
    direct_prompt = dedicated_staff_value_prompt(
        LLM_PROFILE,
        target_events=[asdict(event) for event in events],
        candidates=[
            _selection_candidate_payload(case)
            for case in eligible
        ],
    )
    if direct_prompt:
        target_system = _personnel_system(_cluster_context(events))
        same_system = [
            case
            for case in eligible
            if _case_personnel_system_from_priced_subject(case) == target_system
        ]
        if same_system:
            selected = max(
                same_system,
                key=lambda case: (
                    case.similarity,
                    case.propose_date,
                    case.bill_no,
                ),
            )
            return (
                selected,
                f"가격 선례의 인력 항목에서 확인한 고용·보수체계 "
                f"({target_system})로 후보를 {len(same_system)}건까지 제한한 뒤, "
                f"금액을 보지 않은 캐시 의미유사도 {selected.similarity:.4f} "
                f"1위 {selected.bill_no}을 선택했습니다.",
                0.9,
                False,
            )
        direct_payload = {
            "version": f"{ORGANIZATION_VALUE_SELECTION_VERSION}:dedicated-direct-v1",
            "model": GEMINI_MODEL,
            "target_events": [asdict(event) for event in events],
            "candidates": [
                _selection_candidate_payload(case)
                for case in eligible
            ],
        }
        direct_result, cache_hit = get_or_create_json(
            "organization_value_case_selection",
            direct_payload,
            lambda: gemini_json(direct_prompt, temperature=0.0),
            refresh=refresh,
        )
        direct_result = direct_result if isinstance(direct_result, dict) else {}
        selected_no = str(direct_result.get("bill_no") or "")
        selected = next(
            (case for case in eligible if case.bill_no == selected_no),
            None,
        )
        reason = str(direct_result.get("reason") or "")[:1_000]
        try:
            confidence = max(
                0.0,
                min(1.0, float(direct_result.get("confidence") or 0)),
            )
        except (TypeError, ValueError):
            confidence = 0.0
        if selected is None or confidence < 0.65:
            return (
                None,
                reason or "전담인력과 의미적으로 호환되는 단일 값 선례를 확정하지 못했습니다.",
                confidence,
                cache_hit,
            )
        return (
            selected,
            f"{reason} 금액을 보지 않은 전담인력 단일 reranker가 "
            f"{selected.bill_no}을 선택했습니다.",
            confidence,
            cache_hit,
        )
    payload = {
        "version": ORGANIZATION_VALUE_SELECTION_VERSION,
        "model": GEMINI_MODEL,
        "target_events": [asdict(event) for event in events],
        "target_source": query[:8_000],
        "candidates": candidate_payload,
    }
    prompt = _VALUE_SELECTION_PROMPT + "\n대상:\n" + json.dumps(
        {
            "events": payload["target_events"],
            "source": payload["target_source"],
            "candidates": candidate_payload,
        },
        ensure_ascii=False,
    )
    result, cache_hit = get_or_create_json(
        "organization_value_case_selection",
        payload,
        lambda: gemini_json(prompt, temperature=0.0),
        refresh=refresh,
    )
    result = result if isinstance(result, dict) else {}
    compatible_bill_nos = result.get("compatible_bill_nos")
    compatible_bill_nos = (
        [str(value) for value in compatible_bill_nos]
        if isinstance(compatible_bill_nos, list)
        else []
    )
    selected = _top_compatible_value_case(eligible, compatible_bill_nos)
    reason = str(result.get("reason") or "")
    try:
        confidence = max(0.0, min(1.0, float(result.get("confidence") or 0)))
    except (TypeError, ValueError):
        confidence = 0.0
    if selected is None or confidence < 0.65:
        return (
            None,
            reason or "인사·보수체계와 수명주기가 호환되는 값 선례를 확정하지 못했습니다.",
            confidence,
            cache_hit,
        )
    selected_reason = (
        f"{reason} 호환 후보군 안에서 캐시된 의미유사도 "
        f"{selected.similarity:.4f}가 가장 높은 {selected.bill_no}을 "
        "결정적으로 선택했습니다."
    )
    return selected, selected_reason, confidence, cache_hit


_EXPLICIT_NET_STAFF_PATTERNS = (
    re.compile(r"(?:순증\s*인원|순증\s*인력|증원\s*인원|증원\s*인력)[^\d]{0,20}(\d+)\s*명"),
    re.compile(r"(\d+)\s*명[^\n.]{0,20}(?:순증|증원)"),
)


def _explicit_net_staff_count(legal_text: str) -> int | None:
    """Use only an explicitly stated *incremental* staff count from the bill."""
    for pattern in _EXPLICIT_NET_STAFF_PATTERNS:
        match = pattern.search(legal_text or "")
        if match:
            value = int(match.group(1))
            if value > 0:
                return value
    return None


def _scaled_series(
    item: TagCandidate,
    years: int,
    *,
    target_count: int,
    precedent_count: int,
) -> list[int | None]:
    return [
        int(round((value or 0) * target_count / precedent_count))
        for value in _series(item, years)
    ]


def _event_for_item(
    base: AtomicEvent,
    item: TagCandidate,
    component: str,
    index: int,
) -> AtomicEvent:
    event_type = {
        "personnel": EventType.PERSONNEL.value,
        "employer_contribution": EventType.PERSONNEL.value,
        "basic_expense": EventType.ADMINISTRATIVE.value,
        "asset": EventType.FACILITY_SYSTEM.value,
        "facility": EventType.FACILITY_SYSTEM.value,
        "operating_expense": EventType.ADMINISTRATIVE.value,
    }[component]
    mechanism = {
        "personnel": "staffing",
        "employer_contribution": "staffing",
        "basic_expense": "staffing",
        "asset": "construction",
        "facility": "construction",
        "operating_expense": "internal_administration",
    }[component]
    display_name = {
        "personnel": "인건비",
        "employer_contribution": "기관부담금",
        "basic_expense": "기본경비",
        "asset": "자산취득비",
        "facility": "시설비",
        "operating_expense": "운영사업비",
    }[component]
    return AtomicEvent(
        id=f"{base.id}-ORG-{index:02d}",
        segment_ids=list(base.segment_ids),
        article_refs=list(base.article_refs),
        quotes=list(base.quotes),
        actor=base.actor,
        action="조직변경 비용항목 추계",
        object=display_name,
        bearer=base.bearer,
        event_type=event_type,
        obligation=base.obligation,
        cost_mechanism=mechanism,
        additionality=base.additionality,
        recurrence_text="",
        explanation=f"선택된 조직변경 값 선례의 {display_name} 항목",
        grounded=base.grounded,
    )


def _event_for_staff_bundle(base: AtomicEvent) -> AtomicEvent:
    return AtomicEvent(
        id=f"{base.id}-ORG-STAFF-BUNDLE",
        segment_ids=list(base.segment_ids),
        article_refs=list(base.article_refs),
        quotes=list(base.quotes),
        actor=base.actor,
        action="조직변경 인력운영비 추계",
        object="보수·기관부담금·기본경비·자산취득비",
        bearer=base.bearer,
        event_type=EventType.PERSONNEL.value,
        obligation=base.obligation,
        cost_mechanism="staffing",
        additionality=base.additionality,
        recurrence_text="",
        explanation="한 선례 안에서 완결된 인력운영비 묶음",
        grounded=base.grounded,
    )


def _cluster_context(cluster: list[AtomicEvent]) -> str:
    return "\n".join(
        value
        for event in cluster
        for value in (
            *event.quotes,
            event.actor,
            event.action,
            event.object,
            event.bearer,
            event.explanation,
        )
        if value
    )


def _mapped_staff_count(
    cluster: list[AtomicEvent],
    net_staff_counts: dict[str, int] | None,
) -> int | None:
    if not net_staff_counts:
        return None
    keys = [
        *[event.id for event in cluster],
        *[article for event in cluster for article in event.article_refs],
        *[event.object for event in cluster],
    ]
    values: set[int] = set()
    for key in keys:
        try:
            value = int(net_staff_counts.get(key, 0))
        except (TypeError, ValueError):
            continue
        if value > 0:
            values.add(value)
    return next(iter(values)) if len(values) == 1 else None


_ORGANIZATION_OPERATING_BUDGET_PATTERN = re.compile(
    r"(?:운영|사무\s*처리).{0,80}(?:경비|비용).{0,100}(?:부담|분담)"
    r"|(?:경비|비용).{0,100}(?:부담|분담).{0,80}(?:운영|사무\s*처리)"
)


def _operating_budget_candidates(
    target_text: str,
    *,
    exclude_bill_nos: set[str],
    cutoff_date: str | None,
) -> list[TagCandidate]:
    """Find whole-organization operating budgets within the same legal form."""
    target_form = _organization_form(target_text)
    if target_form == "unknown":
        return []
    excluded = {str(value) for value in exclude_bill_nos if value}
    candidates: list[TagCandidate] = []
    for candidate_form, case in _all_typed_structure_cases():
        if candidate_form != target_form or case.bill_no in excluded:
            continue
        if cutoff_date and case.propose_date and case.propose_date > cutoff_date:
            continue
        for component, item in case.items:
            name = _normalise(item.item_name)
            if component in {"personnel", "employer_contribution", "basic_expense", "asset"}:
                continue
            if item.family == "committee":
                continue
            if not re.search(r"운영경비|운영예산|운영비", name):
                continue
            if _is_aggregate_item(item) or not _has_positive_amount(item):
                continue
            candidates.append(item)
    return candidates


def build_organization_operating_budget_rows(
    segments: list[Segment],
    *,
    bill_no: str | None,
    cutoff_date: str | None,
    years: int,
    annual_budgets_thousand: dict[str, int] | None = None,
) -> list[EstimateRow]:
    """Surface mandatory organization operating-cost clauses as their own HITL.

    This prevents a cost-sharing article from disappearing merely because an
    LLM focused on a later discretionary paragraph.  The row is computed only
    from a target-specific user value or one unambiguous same-form precedent.
    """
    rows: list[EstimateRow] = []
    for index, segment in enumerate(segments, start=1):
        if not _ORGANIZATION_OPERATING_BUDGET_PATTERN.search(segment.text):
            continue
        # Do not mistake a committee's shared meeting expenses for the whole
        # operating budget of a statutory organization.
        target_form = _organization_form(segment.text)
        if target_form in {"unknown", "support_office"}:
            continue
        candidates = _operating_budget_candidates(
            segment.text,
            exclude_bill_nos={bill_no} if bill_no else set(),
            cutoff_date=cutoff_date,
        )
        event = AtomicEvent(
            id=f"ORG-OPERATING-BUDGET-{index:03d}",
            segment_ids=[segment.id],
            article_refs=[segment.article_ref],
            quotes=[segment.text],
            actor="조직 운영 주체",
            action="운영 및 사무처리 경비 부담",
            object="연간 조직 운영경비",
            bearer="public",
            event_type=EventType.ADMINISTRATIVE.value,
            obligation="mandatory",
            cost_mechanism="internal_administration",
            additionality="possibly_incremental",
            recurrence_text="매년",
            explanation="조직 운영·사무처리 경비를 부담 또는 분담하는 조문",
            grounded=True,
        )
        supplied = None
        if annual_budgets_thousand:
            base_article_match = re.match(r"제\d+조(?:의\d+)?", segment.article_ref)
            base_article = (
                base_article_match.group(0)
                if base_article_match
                else segment.article_ref
            )
            for key in (segment.id, segment.article_ref, base_article, event.object):
                try:
                    value = int(annual_budgets_thousand.get(key, 0))
                except (TypeError, ValueError):
                    continue
                if value > 0:
                    supplied = value
                    break
        if supplied is not None:
            rows.append(
                EstimateRow(
                    event=event,
                    status=RowStatus.COMPUTED_REVIEW,
                    reason_codes=["TARGET_ANNUAL_OPERATING_BUDGET_APPLIED"],
                    reason=(
                        "같은 법형식의 조직 전체 운영예산 선례가 없어 대상 조직의 "
                        "연간 운영경비 입력값을 매년 적용했습니다."
                    ),
                    formula="대상 조직 연간 운영경비 × 추계연수",
                    recurrence=Recurrence(
                        "annual",
                        1,
                        "user_input",
                        "대상 조직 연간 운영경비",
                    ),
                    year_amounts_thousand=[supplied] * years,
                    selection_method=ORGANIZATION_VALUE_SELECTION_VERSION,
                    selection_reason="호환 DB 선례 부재 후 대상별 사용자 입력",
                    selection_confidence=1.0,
                    variable_evidence=[
                        {
                            "name": "대상 조직 연간 운영경비",
                            "value": supplied,
                            "unit": "천원/년",
                            "source": "user_input",
                        }
                    ],
                )
            )
            continue
        if len(candidates) == 1:
            candidate = candidates[0]
            annual = int(
                round(
                    sum(
                        int(row.get("amount_thousand") or 0)
                        for row in candidate.amounts
                        if int(row.get("amount_thousand") or 0) > 0
                    )
                    / max(
                        1,
                        sum(
                            1
                            for row in candidate.amounts
                            if int(row.get("amount_thousand") or 0) > 0
                        ),
                    )
                )
            )
            rows.append(
                EstimateRow(
                    event=event,
                    status=RowStatus.COMPUTED_REVIEW,
                    reason_codes=["SAME_FORM_OPERATING_BUDGET_TRANSFERRED"],
                    reason=(
                        "같은 조직 법형식에서 조직 전체 연간 운영비를 계상한 유일한 "
                        f"선례 {candidate.bill_no}을 준용했습니다."
                    ),
                    formula="같은 조직 법형식 선례의 연평균 운영경비",
                    recurrence=Recurrence(
                        "annual",
                        1,
                        f"TAG:{candidate.bill_no}",
                        "같은 법형식의 조직 전체 운영비",
                    ),
                    year_amounts_thousand=[annual] * years,
                    selected_candidates=[candidate],
                    selection_method=ORGANIZATION_VALUE_SELECTION_VERSION,
                    selection_reason="같은 법형식·전체 운영비 범위의 유일한 선례",
                    selection_confidence=0.8,
                    variable_evidence=[
                        {
                            "name": "선례 연평균 조직 운영경비",
                            "value": annual,
                            "unit": "천원/년",
                            "source": candidate.item_id,
                        }
                    ],
                )
            )
            continue
        rows.append(
            EstimateRow(
                event=event,
                status=RowStatus.NEEDS_USER_INPUT,
                reason_codes=["TARGET_ANNUAL_OPERATING_BUDGET_MISSING"],
                reason=(
                    "운영경비 분담 의무는 확인했지만 같은 조직 법형식의 조직 전체 "
                    f"운영예산 선례를 확정하지 못했습니다(호환 후보 {len(candidates)}건). "
                    "유사 조직 연간 예산 또는 대상 조직 연간 운영경비를 입력해야 합니다."
                ),
                formula=(
                    "유사 조직 연간 운영예산 × 대상 재정규모 ÷ 선례 재정규모 "
                    "또는 대상 연간 운영경비 직접 입력"
                ),
                recurrence=Recurrence(
                    "annual",
                    1,
                    "user_input",
                    "대상 연간 운영경비 입력 대기",
                ),
                year_amounts_thousand=[None] * years,
                selected_candidates=candidates[:3],
                selection_method=ORGANIZATION_VALUE_SELECTION_VERSION,
                selection_reason="같은 법형식·전체 운영비 호환 선례 부재",
                selection_confidence=0.0,
                variable_evidence=[
                    {
                        "name": "대상 조직 연간 운영경비",
                        "value": None,
                        "unit": "천원/년",
                        "source": "user_input",
                    }
                ],
            )
        )
    return rows


def _facility_review_event(base: AtomicEvent) -> AtomicEvent:
    return AtomicEvent(
        id=f"{base.id}-ORG-FACILITY",
        segment_ids=list(base.segment_ids),
        article_refs=list(base.article_refs),
        quotes=list(base.quotes),
        actor=base.actor,
        action="조직변경 시설 추가성 확인",
        object=f"{base.object} 시설·청사",
        bearer=base.bearer,
        event_type=EventType.FACILITY_SYSTEM.value,
        obligation=base.obligation,
        cost_mechanism="construction",
        additionality=base.additionality,
        recurrence_text="",
        explanation="조직변경에 별도 시설비가 추가되는지 확인하는 검토 항목",
        grounded=base.grounded,
    )


def build_organization_rows(
    events: list[AtomicEvent],
    legal_text: str,
    *,
    bill_no: str | None,
    cutoff_date: str | None,
    years: int,
    net_staff_count: int | None = None,
    net_staff_counts: dict[str, int] | None = None,
    staffing_scenario: str | None = None,
    segment_text_by_id: dict[str, str] | None = None,
    refresh: bool = False,
) -> tuple[list[EstimateRow], set[str], list[str]]:
    rows: list[EstimateRow] = []
    consumed: set[str] = set()
    warnings: list[str] = []
    clusters = [
        cluster
        for cluster in find_organization_clusters(events)
        if any(
            event.bearer in {"state", "local", "public_institution"}
            for event in cluster
        )
    ]
    if net_staff_count and len(clusters) != 1:
        warnings.append(
            "조직 사건이 여러 건이라 단일 순증인원 입력을 자동 배분하지 않았습니다. "
            "사건 ID·조문·조직명별 순증인원을 입력해야 합니다."
        )

    for cluster in clusters:
        consumed.update(event.id for event in cluster)
        base = next(
            (event for event in cluster if event.event_type == EventType.PERSONNEL.value),
            cluster[0],
        )
        cluster_context = _cluster_context(cluster)
        cluster_source_text = (
            " ".join(
                segment_text_by_id.get(segment_id, "")
                for segment_id in dict.fromkeys(
                    segment_id
                    for event in cluster
                    for segment_id in event.segment_ids
                )
            )
            if segment_text_by_id
            else ""
        )
        lifecycle_context = "\n".join(
            value
            for value in (cluster_context, cluster_source_text)
            if value
        )
        query = (
            legal_text[:8_000]
            + "\n구조화 사건:\n"
            + json.dumps([asdict(event) for event in cluster], ensure_ascii=False)
        )
        cases = search_organization_cases(
            query,
            exclude_bill_nos={bill_no} if bill_no else set(),
            cutoff_date=cutoff_date,
            refresh=refresh,
        )
        structure_cases = _prefer_same_court_transition(query, cases)
        dedicated_staffing = any(
            _is_dedicated_staff_designation_event(event)
            for event in cluster
        )
        if dedicated_staffing and staffing_scenario not in {
            "existing_staff",
            "new_hires",
        }:
            rows.append(
                EstimateRow(
                    event=_event_for_staff_bundle(base),
                    status=RowStatus.NEEDS_USER_INPUT,
                    reason_codes=["STAFFING_SCENARIO_REQUIRED"],
                    reason=(
                        "담당관·전담인력 지정은 기존 직원 지정인지 신규채용인지에 따라 "
                        "추가재정이 달라집니다. 기존 직원 지정 또는 신규채용 시나리오를 "
                        "선택한 뒤, 신규채용이면 대상 순증 인원을 입력해야 합니다."
                    ),
                    formula=(
                        "[기존 직원 지정] 추가 인건비 0원(별도 업무비는 별도 확인) / "
                        "[신규채용] 인건비+기관부담금+기본경비+자산취득비"
                    ),
                    year_amounts_thousand=[None] * years,
                    selection_method=ORGANIZATION_SELECTION_VERSION,
                    selection_reason="담당관 지정 비용 시나리오 선택 대기",
                    selection_confidence=1.0,
                    variable_evidence=[
                        {
                            "name": "인력운영 시나리오",
                            "value": None,
                            "unit": "existing_staff|new_hires",
                            "source": "user_input",
                        }
                    ],
                )
            )
            continue
        if dedicated_staffing and staffing_scenario == "existing_staff":
            rows.append(
                EstimateRow(
                    event=_event_for_staff_bundle(base),
                    status=RowStatus.COMPUTED_REVIEW,
                    reason_codes=[
                        "EXISTING_STAFF_DESIGNATION_NO_INCREMENTAL_PERSONNEL"
                    ],
                    reason=(
                        "법문상 기존 소속 직원 지정 시나리오를 선택했습니다. "
                        "신규 인건비·기관부담금·자산취득비는 추가하지 않았으며, "
                        "별도 업무수행비는 구체적 사업계획 확인 후 별도 추계합니다."
                    ),
                    formula="기존 직원 지정 → 신규 인력운영비 0원",
                    year_amounts_thousand=[0] * years,
                    selection_method=ORGANIZATION_SELECTION_VERSION,
                    selection_reason="사용자 선택: 기존 직원 지정",
                    selection_confidence=1.0,
                    variable_evidence=[
                        {
                            "name": "인력운영 시나리오",
                            "value": "existing_staff",
                            "unit": "scenario",
                            "source": "user_input",
                        }
                    ],
                )
            )
            continue
        if dedicated_staffing:
            selected = None
            reason = (
                "전담 직무 지정은 조직 신설이 아니므로 조직 법형식 선례를 적용하지 "
                "않고, 순증 인원 확인을 전제로 인력비 값 선례만 선택합니다."
            )
            confidence = 1.0
        else:
            selected, reason, confidence = select_typed_structure_case(
                cluster_context,
                exclude_bill_nos={bill_no} if bill_no else set(),
                cutoff_date=cutoff_date,
            )
            if selected is None:
                selected, reason, confidence, _ = select_organization_case(
                    query,
                    cluster,
                    structure_cases,
                    refresh=refresh,
                )
        bundle, bundle_reason, bundle_confidence = select_staff_cost_bundle(
            lifecycle_context,
            lifecycle_context,
            exclude_bill_nos={bill_no} if bill_no else set(),
            cutoff_date=cutoff_date,
            years=years,
            refresh=refresh,
        )
        value_case = None
        value_reason = bundle_reason
        value_confidence = bundle_confidence
        if bundle is None:
            value_case, value_reason, value_confidence, _ = select_organization_value_case(
                query,
                cluster,
                cases,
                years=years,
                target_source_text=cluster_source_text,
                refresh=refresh,
            )

        if selected is None and value_case is None and bundle is None:
            rows.append(
                EstimateRow(
                    event=base,
                    status=RowStatus.NEEDS_USER_INPUT,
                    reason_codes=["NO_TRANSFERABLE_ORGANIZATION_CASE"],
                    reason=(
                        "조직 신설·승격은 탐지했지만 구조 선례와 값 선례를 모두 "
                        f"확정하지 못했습니다. 구조: {reason} 값: {value_reason}"
                    ),
                    year_amounts_thousand=[0] * years,
                    selected_candidates=[
                        item
                        for case in cases[:3]
                        for _, item in case.items[:1]
                    ],
                    selection_method=ORGANIZATION_SELECTION_VERSION,
                    selection_reason=f"구조: {reason} 값: {value_reason}",
                    selection_confidence=max(confidence, value_confidence),
                )
            )
            continue
        if value_case is None and bundle is None:
            rows.append(
                EstimateRow(
                    event=base,
                    status=RowStatus.NEEDS_USER_INPUT,
                    reason_codes=["NO_SCALABLE_ORGANIZATION_VALUE_CASE"],
                    reason=(
                        f"조직 구조 선례 {selected.bill_no if selected else '미확정'}은 "
                        "검토했지만, 인건비·기본경비·"
                        "자산취득비와 인원 분모가 함께 완결된 값 선례가 없습니다. "
                        f"{value_reason}"
                    ),
                    year_amounts_thousand=[0] * years,
                    selection_method=ORGANIZATION_SELECTION_VERSION,
                    selection_reason=f"구조: {reason} 값: {value_reason}",
                    selection_confidence=min(confidence, value_confidence),
                )
            )
            continue
        structure_label = selected.bill_no if selected else "미확정"
        combined_reason = f"구조: {reason} 값: {value_reason}"
        combined_confidence = (
            min(confidence, value_confidence) if selected else value_confidence
        )

        mapped_count = _mapped_staff_count(cluster, net_staff_counts)
        legacy_count = net_staff_count if len(clusters) == 1 else None
        explicit_count = _explicit_net_staff_count(lifecycle_context)
        target_count = mapped_count or legacy_count or explicit_count
        target_count_source = (
            "user_input"
            if mapped_count or legacy_count
            else "law_text"
        )

        if bundle is not None:
            bundle_event = _event_for_staff_bundle(base)
            bundle_item = bundle.item
            bundle_series = _coherent_bundle_series(bundle_item, years)
            evidence = [
                {
                    "name": variable.get("name"),
                    "value": variable.get("value"),
                    "unit": variable.get("unit"),
                    "source": bundle_item.item_id,
                }
                for variable in bundle_item.variables
            ]
            if not target_count or bundle_series is None:
                rows.append(
                    EstimateRow(
                        event=bundle_event,
                        status=RowStatus.NEEDS_USER_INPUT,
                        reason_codes=["TARGET_ORGANIZATION_SCALE_MISSING"],
                        reason=(
                            f"구조 선례 {structure_label}, 완결 인력비 선례 "
                            f"{bundle_item.bill_no}과 비용 묶음은 확정했지만, "
                            "선례의 인원 규모 자체는 대상 의안으로 이전할 수 없습니다. "
                            "목표 인원−기존 인원−전입·재배치 인원으로 계산한 대상 순증 인원을 "
                            "입력하면 같은 선례의 보수·기관부담금·기본경비·자산취득비를 "
                            "한꺼번에 재계산합니다."
                        ),
                        formula=(
                            f"대상 순증 인원 ÷ 선례 인원({bundle.staff_count}명) × "
                            f"선례 연도별 {bundle_item.item_name}"
                        ),
                        recurrence=Recurrence(
                            "precedent_yearly_series",
                            None,
                            f"TAG:{bundle_item.bill_no}",
                            "대상 순증 인원 입력 대기",
                        ),
                        year_amounts_thousand=[None] * years,
                        selected_candidates=[bundle_item],
                        selection_method=ORGANIZATION_SELECTION_VERSION,
                        selection_reason=combined_reason,
                        selection_confidence=combined_confidence,
                        variable_evidence=[
                            *evidence,
                            {
                                "name": "대상 조직 순증 인원",
                                "value": None,
                                "unit": "명",
                                "source": "user_input",
                            },
                        ],
                    )
                )
            else:
                year_amounts = [
                    int(round(value * target_count / bundle.staff_count))
                    for value in bundle_series
                ]
                rows.append(
                    EstimateRow(
                        event=bundle_event,
                        status=RowStatus.COMPUTED_REVIEW,
                        reason_codes=["ORGANIZATION_COHERENT_STAFF_BUNDLE_TRANSFERRED"],
                        reason=(
                            "대상 정답 금액은 검색·선택에 사용하지 않았습니다. "
                            f"같은 인사·예산 체계의 선례 {bundle_item.bill_no}에서 "
                            "보수·기관부담금·기본경비·자산취득비와 인원 분모가 함께 "
                            f"완결된 행을 선택하고, {bundle.staff_count}명 대비 대상 순증 "
                            f"{target_count}명({target_count_source})의 비율만 적용했습니다. "
                            f"{combined_reason}"
                        ),
                        formula=(
                            f"선례 연도별 완결 인력운영비 × 대상 순증 인원({target_count}명) "
                            f"÷ 선례 인원({bundle.staff_count}명)"
                        ),
                        recurrence=Recurrence(
                            "precedent_yearly_series",
                            None,
                            f"TAG:{bundle_item.bill_no}",
                            "한 선례의 연도별 완결 인력운영비 계열",
                        ),
                        year_amounts_thousand=year_amounts,
                        selected_candidates=[bundle_item],
                        selection_method=ORGANIZATION_SELECTION_VERSION,
                        selection_reason=combined_reason,
                        selection_confidence=combined_confidence,
                        variable_evidence=[
                            *evidence,
                            {
                                "name": "대상 조직 순증 인원",
                                "value": target_count,
                                "unit": "명",
                                "source": target_count_source,
                            },
                        ],
                    )
                )
        else:
            assert value_case is not None
            item_index = 1
            for component, item in value_case.items:
                if component not in _VALUE_COMPONENTS:
                    continue
                item.similarity = value_case.similarity
                synthetic_event = _event_for_item(base, item, component, item_index)
                item_index += 1
                if (
                    component == "operating_expense"
                    and _organization_form(cluster_context) == "legislative_committee"
                    and _case_organization_form(value_case) == "legislative_committee"
                    and _is_fixed_operating_precedent(item)
                ):
                    rows.append(
                        EstimateRow(
                            event=synthetic_event,
                            status=RowStatus.COMPUTED_REVIEW,
                            reason_codes=[
                                "LEGISLATIVE_COMMITTEE_FIXED_OPERATING_SERIES_TRANSFERRED"
                            ],
                            reason=(
                                "대상 정답은 검색·선택에 사용하지 않았습니다. "
                                f"같은 입법기관 위원회 선례 {value_case.bill_no}가 "
                                "인원수 대신 비교 가능한 상임위원회 1개당 평균 "
                                "운영경비를 사용하므로, 그 연도별 계열을 항목 단위로 "
                                f"이전했습니다. {combined_reason}"
                            ),
                            formula=item.formula,
                            recurrence=Recurrence(
                                "precedent_yearly_series",
                                None,
                                f"TAG:{value_case.bill_no}",
                                "상임위원회 1개당 평균 운영경비의 연도별 계열",
                            ),
                            year_amounts_thousand=_series(item, years),
                            selected_candidates=[item],
                            selection_method=ORGANIZATION_SELECTION_VERSION,
                            selection_reason=combined_reason,
                            selection_confidence=combined_confidence,
                            variable_evidence=[
                                {
                                    "name": variable.get("name"),
                                    "value": variable.get("value"),
                                    "unit": variable.get("unit"),
                                    "source": item.item_id,
                                }
                                for variable in item.variables
                            ],
                        )
                    )
                    continue
                if component not in _COMPLETE_COMPONENTS:
                    continue
                precedent_count = _item_staff_count(value_case, component, item)
                scale_ready = (
                    precedent_count is not None
                    and target_count is not None
                    and target_count > 0
                )
                if not scale_ready:
                    rows.append(
                        EstimateRow(
                            event=synthetic_event,
                            status=RowStatus.NEEDS_USER_INPUT,
                            reason_codes=["TARGET_ORGANIZATION_SCALE_MISSING"],
                            reason=(
                                f"구조 선례 {structure_label}, 값 선례 {value_case.bill_no}과 "
                                "비용항목 산식은 확정했지만 선례의 인원은 대상 의안으로 "
                                "이전할 수 없습니다. 대상 순증 인원을 입력하면 재계산합니다."
                            ),
                            formula=(
                                f"대상 순증 인원 ÷ 선례 순증 인원"
                                f"({precedent_count or '미확인'}명) × "
                                f"값 선례 연도별 {item.item_name}"
                            ),
                            recurrence=Recurrence(
                                "precedent_yearly_series",
                                None,
                                f"TAG:{value_case.bill_no}",
                                "대상 순증 인원 입력 대기",
                            ),
                            year_amounts_thousand=[None] * years,
                            selected_candidates=[item],
                            selection_method=ORGANIZATION_SELECTION_VERSION,
                            selection_reason=combined_reason,
                            selection_confidence=combined_confidence,
                            variable_evidence=[
                                *[
                                    {
                                        "name": variable.get("name"),
                                        "value": variable.get("value"),
                                        "unit": variable.get("unit"),
                                        "source": item.item_id,
                                    }
                                    for variable in item.variables
                                ],
                                {
                                    "name": "대상 조직 순증 인원",
                                    "value": None,
                                    "unit": "명",
                                    "source": "user_input",
                                },
                            ],
                        )
                    )
                    continue

                year_amounts = _scaled_series(
                    item,
                    years,
                    target_count=target_count,
                    precedent_count=precedent_count,
                )
                rows.append(
                    EstimateRow(
                        event=synthetic_event,
                        status=RowStatus.COMPUTED_REVIEW,
                        reason_codes=["ORGANIZATION_CASE_ITEM_TRANSFERRED"],
                        reason=(
                            "대상 정답은 검색·선택 입력에서 제외했습니다. "
                            f"값 선례 {value_case.bill_no}의 항목 내부 변수만 사용하고, "
                            f"{precedent_count}명 대비 대상 순증 {target_count}명"
                            f"({target_count_source})의 비율로 재계산했습니다. "
                            f"{combined_reason}"
                        ),
                        formula=(
                            f"({item.formula}) × 대상 순증 인원({target_count}명) "
                            f"÷ 선례 순증 인원({precedent_count}명)"
                        ),
                        recurrence=Recurrence(
                            "precedent_yearly_series",
                            None,
                            f"TAG:{value_case.bill_no}",
                            "값 선례의 연도별 금액 계열",
                        ),
                        year_amounts_thousand=year_amounts,
                        selected_candidates=[item],
                        selection_method=ORGANIZATION_SELECTION_VERSION,
                        selection_reason=combined_reason,
                        selection_confidence=combined_confidence,
                        variable_evidence=[
                            *[
                                {
                                    "name": variable.get("name"),
                                    "value": variable.get("value"),
                                    "unit": variable.get("unit"),
                                    "source": item.item_id,
                                }
                                for variable in item.variables
                            ],
                            {
                                "name": "대상 조직 순증 인원",
                                "value": target_count,
                                "unit": "명",
                                "source": target_count_source,
                            },
                        ],
                    )
                )

        if dedicated_staffing:
            # A role designation does not itself create premises for a new
            # office, lease, or building.  Keep facilities out of this channel.
            continue

        # A promotion precedent that reuses an existing office can legitimately
        # have no capital/facility row.  Do not hallucinate construction cost,
        # but surface the target-side confirmation as HITL instead of silently
        # treating the missing component as zero.
        facility_event = next(
            (event for event in cluster if event.event_type == EventType.FACILITY_SYSTEM.value),
            _facility_review_event(base),
        )
        facility_item = next(
            (
                item
                for component, item in selected.items
                if component == "facility"
            ),
            None,
        ) if selected else None
        if selected is None:
            facility_reason = (
                "완전히 호환되는 조직 구조 선례를 확정하지 못했습니다. 인건비 계열과 "
                "별개로 대상 조직이 기존 청사·유휴공간을 쓰는지, 임차·신축이 필요한지 "
                "확인해야 합니다."
            )
            facility_code = "NO_TRANSFERABLE_ORGANIZATION_STRUCTURE"
            facility_candidates = (
                [bundle.item]
                if bundle is not None
                else [value_case.items[0][1]]
            )
        elif facility_item is not None:
            facility_reason = (
                f"구조 선례 {selected.bill_no}에는 시설비가 있지만 선례의 면적·공사범위·"
                "임차기간은 대상 의안으로 이전할 수 없습니다. 대상 시설의 추가성 및 "
                "면적·단가를 확인하면 별도 계산합니다."
            )
            facility_code = "TARGET_FACILITY_SCALE_MISSING"
            facility_candidates = [facility_item]
        else:
            facility_reason = (
                f"구조 선례 {selected.bill_no}은 기존 하위조직의 시설을 활용해 별도 "
                "시설비를 계상하지 않았습니다. 대상 의안도 기존 청사·진행 중 사업으로 "
                "수용 가능한지 확인하기 전에는 시설비를 0원으로 확정하지 않습니다."
            )
            facility_code = "FACILITY_ADDITIONALITY_REQUIRES_CONFIRMATION"
            facility_candidates = [selected.items[0][1]]
        rows.append(
            EstimateRow(
                event=facility_event,
                status=RowStatus.NEEDS_EVIDENCE,
                reason_codes=[facility_code],
                reason=facility_reason,
                year_amounts_thousand=[0] * years,
                selected_candidates=facility_candidates,
                selection_method=ORGANIZATION_SELECTION_VERSION,
                selection_reason=combined_reason,
                selection_confidence=combined_confidence,
            )
        )
        warnings.append(
            f"조직변경 정책 {ORGANIZATION_RETRIEVAL_VERSION}/"
            f"{ORGANIZATION_SELECTION_VERSION}: 구조 {structure_label}, "
            f"값 {(bundle.item.bill_no if bundle else value_case.bill_no)} 선택, "
            "정답 미사용, 완결 묶음 우선·항목별 단일 선례 준용."
        )
    return rows, consumed, warnings
