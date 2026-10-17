"""Audit and preview an organization/administration evidence sidecar.

The existing TAG JSONL files are the immutable raw layer.  This script joins
their items and variables, identifies organization/committee cost components,
and emits *candidate* canonical variable mappings.  It never updates Supabase
or rewrites the raw seed files.

The output is deliberately a preview rather than an import file: a numeric
value being present in a precedent does not mean that it is transferable to a
new bill.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SEED_DIRS = (
    ROOT / "backend/generated/assembly_rag_seed",
    ROOT / "backend/generated/assembly_rag_seed_22_ce",
)
DEFAULT_OUTPUT_DIR = ROOT / "backend/generated/org_admin_v2_audit"


_COMMITTEE_RE = re.compile(r"위원회|심의회|협의회|위원단|자문단")
_ORG_CONTEXT_RE = re.compile(
    r"조직|행정기관|중앙행정기관|소속기관|본부|사무처|사무국|지원단|추진단|"
    r"전담조직|전담인력|증원|신규채용|"
    r"(?:인력|직원|공무원|직급별|계급별)정원|정원(?:증원|확대|조정)"
)
_COMPONENT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("employer_contribution", re.compile(r"기관부담|사용자부담")),
    ("basic_expense", re.compile(r"기본경비|기관운영비|행정운영비|운영경비")),
    ("space", re.compile(r"임차료|임대료|사무공간|청사|관리비")),
    ("asset", re.compile(r"자산취득|사무기기|사무용품|비품|집기")),
    (
        "personnel",
        re.compile(
            r"인건비|인력운영|보수|봉급|증원|신규채용|"
            r"(?:인력|직원|공무원|직급별|계급별)정원|정원(?:증원|확대|조정)"
        ),
    ),
)
_ADMIN_OPERATION_RE = re.compile(r"운영비|운영경비|행정지원|사무국운영|사업비")


@dataclass(frozen=True)
class ItemClassification:
    route: str
    component: str
    confidence: str
    reason: str


@dataclass(frozen=True)
class NormalizedCandidate:
    raw_item_id: str
    raw_structure_id: str
    bill_id: str
    item_name: str
    item_category: str
    route: str
    component: str
    raw_variable_type: str
    raw_variable_name: str
    canonical_key: str | None
    raw_value: float | int | None
    raw_unit: str
    source_text: str
    source_class: str
    basis_year_candidates: tuple[int, ...]
    mapping_confidence: str
    normalization_status: str
    transfer_policy: str


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL: {path}:{line_number}") from exc
            if isinstance(row, dict):
                yield row


def _item_blob(item: dict[str, Any]) -> str:
    return _compact(f"{item.get('item_name', '')} {item.get('item_category', '')}")


def structure_context(items: Iterable[dict[str, Any]]) -> dict[str, set[str]]:
    """Return high-precision organization routes visible anywhere in a case."""
    routes: dict[str, set[str]] = defaultdict(set)
    for item in items:
        structure_id = str(item.get("struct_id") or "")
        blob = _item_blob(item)
        category = _compact(item.get("item_category"))
        if not structure_id:
            continue
        if _COMMITTEE_RE.search(blob):
            routes[structure_id].add("committee")
        if (
            _ORG_CONTEXT_RE.search(blob)
            or category == "인건비"
            or re.search(r"기본경비|기관부담|자산취득비", blob)
        ):
            routes[structure_id].add("organization")
    return routes


def classify_item(
    item: dict[str, Any],
    sibling_routes: set[str] | None = None,
) -> ItemClassification | None:
    """Classify a TAG item without treating every generic benefit as payroll."""
    sibling_routes = sibling_routes or set()
    blob = _item_blob(item)
    category = _compact(item.get("item_category"))
    has_committee = bool(_COMMITTEE_RE.search(blob))
    has_org_context = bool(_ORG_CONTEXT_RE.search(blob))

    component = ""
    for name, pattern in _COMPONENT_RULES:
        if pattern.search(blob):
            component = name
            break

    # A generic benefit/support item containing words such as "급여" must not
    # become organization payroll merely because it transfers money to people.
    if category in {"지원금", "복지비", "사업비"} and not (
        has_committee or has_org_context or component in {
            "employer_contribution",
            "basic_expense",
            "space",
            "asset",
        }
    ):
        return None

    if has_committee:
        # A committee can create two distinct fiscal routes in one item set:
        # member meeting allowances stay on the committee route, while a
        # committee secretariat or a standing member is an organization
        # personnel/operations event.  Route by the cost mechanism instead of
        # allowing the word "위원회" to swallow every personnel item.
        if re.search(r"회의|참석|수당|사례금|안건검토", blob):
            return ItemClassification(
                "committee",
                "committee_meeting",
                "high",
                "committee_allowance_term",
            )
        if component in {
            "personnel",
            "employer_contribution",
            "basic_expense",
            "space",
            "asset",
        }:
            return ItemClassification(
                "organization",
                component,
                "high",
                "committee_organization_cost_mechanism",
            )
        if not component:
            component = (
                "committee_meeting"
                if re.search(r"회의|수당|사례금|안건검토", blob)
                else "committee_operation"
            )
        return ItemClassification("committee", component, "high", "explicit_committee_term")

    if has_org_context or category == "인건비":
        if not component:
            component = "operating_expense" if _ADMIN_OPERATION_RE.search(blob) else "other"
        return ItemClassification("organization", component, "high", "explicit_org_context")

    if component in {"employer_contribution", "basic_expense"}:
        return ItemClassification("organization", component, "high", "canonical_component")

    # "자산취득비" or "임차료" can be generic project/facility costs.  Include
    # them only when a sibling item proves that the estimate is organizational.
    if component in {"space", "asset", "personnel"} and sibling_routes:
        route = "committee" if sibling_routes == {"committee"} else "organization"
        return ItemClassification(route, component, "medium", "organization_sibling_context")

    return None


_ROLE_RULES: tuple[tuple[str, re.Pattern[str], set[str]], ...] = (
    (
        "employer_contribution_rate",
        re.compile(r"기관부담|사용자부담"),
        {"rate", "other"},
    ),
    (
        "basic_expense_ratio",
        re.compile(r"인건비대비기본경비|보수.*대비.*기본경비|기본경비비율|기본경비비중"),
        {"rate", "other"},
    ),
    (
        "wage_growth_rate",
        re.compile(r"임금.*(?:상승률|인상률)|보수.*(?:상승률|인상률)|인건비.*(?:상승률|인상률)"),
        {"rate", "other"},
    ),
    (
        "price_growth_rate",
        re.compile(r"소비자물가|물가상승률"),
        {"rate", "other"},
    ),
    (
        "meeting_unit_price",
        re.compile(
            r"(?:회의|참석|안건검토).*(?:수당|사례금|참석비).*(?:단가|금액|인당|회당)"
            r"|(?:단가|금액|인당|회당).*(?:회의|참석|안건검토).*(?:수당|사례금|참석비)"
            r"|위원.*(?:수당|사례금).*단가"
        ),
        {"unit_cost", "other"},
    ),
    (
        "annual_meetings",
        re.compile(
            r"연간.*(?:회의|자문).*횟수|연간.*(?:전원위원회|소위원회).*횟수|"
            r"회의.*횟수|개최.*횟수|회의개최"
        ),
        {"frequency", "target_count", "other"},
    ),
    (
        "committee_instance_count",
        re.compile(
            r"(?:시·?도|시·?군·?구|기초자치단체|광역자치단체)?.*"
            r"(?:위원회|심의회|협의회|기관)(?:의)?(?:개수|설치수|수)$"
        ),
        {"target_count", "other"},
    ),
    (
        "paid_member_count",
        re.compile(
            r"민간위원|비상임위원|위촉위원|수당지급(?:대상자|위원)|"
            r"유급위원|참석위원"
        ),
        {"target_count", "frequency", "other"},
    ),
    (
        "committee_member_count",
        re.compile(r"위원(?:회)?(?:구성)?(?:인원|수|정원|총원)|위원장수"),
        {"target_count", "frequency", "other"},
    ),
    (
        "headcount_by_grade",
        re.compile(r"직급별.*(?:인원|정원|구성)|계급별.*(?:인원|정원|구성)"),
        {"target_count", "other"},
    ),
    (
        "headcount",
        re.compile(r"증원.*인원|증원인력|소요인력|신규채용|지원인력|전담인력|정원|직원수|공무원수"),
        {"target_count", "frequency", "other"},
    ),
    (
        "salary_by_grade",
        re.compile(r"직급별.*(?:보수|봉급|인건비)|계급별.*(?:보수|봉급|인건비)"),
        {"unit_cost", "other"},
    ),
    (
        "salary_per_person",
        re.compile(
            r"1인당.*(?:보수|봉급|인건비|연봉)|인당.*(?:보수|봉급|인건비|연봉)|"
            r"^(?:월평균)?(?:보수|봉급)(?:액)?(?:\(|$)|월(?:평균)?보수"
        ),
        {"unit_cost", "other"},
    ),
    (
        "total_salary",
        re.compile(r"보수총액|인건비총액|연간인건비"),
        {"unit_cost", "other"},
    ),
    (
        "asset_unit_price_per_person",
        re.compile(
            r"1인당.*자산취득|인당.*자산취득|자산취득.*(?:단가|1인당|인당)"
        ),
        {"unit_cost", "other"},
    ),
    (
        "basic_expense_per_person",
        re.compile(r"1인당.*기본경비|인당.*기본경비"),
        {"unit_cost", "other"},
    ),
    (
        "required_area",
        re.compile(r"필요면적|사무공간.*면적|임차면적|전용면적|공급면적"),
        {"target_count", "other"},
    ),
    (
        "rent_unit_price",
        re.compile(r"임차료.*단가|임대료.*단가|면적당.*임차|평당.*임차"),
        {"unit_cost", "other"},
    ),
    (
        "duration",
        re.compile(
            r"존속기간|활동기간|사용기간|임차기간|운영기간|"
            r"수사기간|공소유지기간|추계기간|연장개월수"
        ),
        {"period", "frequency", "other"},
    ),
    (
        "start_timing",
        re.compile(r"발생시점|시행시점|지급시점|착수시점"),
        {"period", "frequency", "other"},
    ),
    (
        "asset_amount",
        re.compile(r"^자산취득비(?:총액|금액)?$"),
        {"unit_cost", "other"},
    ),
    (
        "committee_operating_amount",
        re.compile(r"위원회.*(?:연간|회당)?.*운영비|연간위원회운영비"),
        {"unit_cost", "other"},
    ),
    (
        "annual_operating_amount",
        re.compile(r"연간운영비|연간운영경비"),
        {"unit_cost", "other"},
    ),
    (
        "basic_expense_amount",
        re.compile(r"^기본경비(?:총액|금액)?$"),
        {"unit_cost", "other"},
    ),
)


def infer_canonical_key(
    variable_type: str,
    variable_name: str,
    component: str = "",
) -> tuple[str | None, str]:
    compact = _compact(variable_name)
    for key, pattern, expected_types in _ROLE_RULES:
        if pattern.search(compact):
            if variable_type in expected_types:
                confidence = "high" if variable_type != "other" else "medium"
                return key, confidence
            # A conflicting raw type is stronger evidence than a loose name
            # match (for example "회의수당 지급 대상자 수" is a count,
            # not a unit price).  Keep evaluating the later rules.
            continue
    if component.startswith("committee") and variable_type == "unit_cost" and re.search(
        r"(?:회의|참석|위원|자문).*(?:수당|사례금|자문료)"
        r"|(?:수당|사례금|자문료).*(?:회의|참석|위원|자문)",
        compact,
    ):
        return "meeting_unit_price", "medium"
    if component.startswith("committee") and variable_type in {"target_count", "other"}:
        if re.search(r"회당.*(?:심사|처리|안건).*인원", compact):
            return "cases_per_meeting", "medium"
        if re.search(r"접수건수|처리건수|심사인원|징계인원|항고심사인원", compact):
            return "annual_case_volume", "medium"
    if component == "personnel" and variable_type == "target_count" and re.search(
        r"인원|인력|직원수|공무원수|근로자수|의원수", compact
    ):
        return "headcount", "medium"
    return None, "low"


def infer_source_class(source_text: str) -> str:
    compact = _compact(source_text)
    if not compact:
        return "missing"
    if re.search(r"유사(?:기관|조직|사례)|선례|준용", compact):
        return "similar_case"
    if re.search(r"공무원보수규정|공무원수당|예산편성지침|단가및기준정보", compact):
        return "official_standard"
    if re.search(r"국회예산정책처.*전망", compact):
        return "official_forecast"
    if re.search(r"결산|집행액|예산액|예산안", compact):
        return "budget_or_settlement"
    if re.search(r"KOSIS|국가통계포털|통계청|행정자료|실태조사", compact, re.IGNORECASE):
        return "official_statistics"
    if re.search(r"가정|가정함|가정하여", compact):
        return "analyst_assumption"
    if re.search(r"개정안|제정안|법률안|안제\d+조", compact):
        return "bill_or_target_document"
    return "unclassified_source"


def infer_transfer_policy(source_class: str) -> str:
    return {
        "official_standard": "versioned_official",
        "bill_or_target_document": "target_specific",
        "similar_case": "comparable_only",
        "budget_or_settlement": "comparable_only",
        "official_statistics": "scope_check_required",
        "official_forecast": "versioned_official",
        "analyst_assumption": "review_required",
        "missing": "do_not_transfer",
        "unclassified_source": "review_required",
    }[source_class]


def extract_basis_year_candidates(text: str) -> tuple[int, ...]:
    years = {
        int(value)
        for value in re.findall(r"(?<!\d)((?:19|20)\d{2})(?:\s*년)?", str(text or ""))
        if 1900 <= int(value) <= 2100
    }
    return tuple(sorted(years))


def _normalization_status(
    canonical_key: str | None,
    value: Any,
    unit: str,
) -> str:
    if canonical_key is None:
        return "unmapped"
    if value is None:
        return "mapped_missing_value"
    if not unit:
        return "mapped_missing_unit"
    return "mapped"


def load_raw(seed_dirs: Iterable[Path]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Load canonical seeds and deduplicate rows copied between seed folders."""
    items: dict[str, dict[str, Any]] = {}
    variables: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for seed_dir in seed_dirs:
        for row in _read_jsonl(seed_dir / "cost_estimate_items.jsonl"):
            item_id = str(row.get("item_id") or "")
            if item_id:
                items[item_id] = row
        for row in _read_jsonl(seed_dir / "cost_estimate_variables.jsonl"):
            key = (
                str(row.get("item_id") or ""),
                str(row.get("variable_type") or ""),
                str(row.get("variable_name") or ""),
                str(row.get("source_text") or ""),
            )
            if key[0]:
                variables[key] = row
    return items, list(variables.values())


def build_candidates(
    items: dict[str, dict[str, Any]],
    variables: Iterable[dict[str, Any]],
) -> tuple[dict[str, ItemClassification], list[NormalizedCandidate]]:
    contexts = structure_context(items.values())
    selected: dict[str, ItemClassification] = {}
    for item_id, item in items.items():
        classification = classify_item(
            item,
            contexts.get(str(item.get("struct_id") or ""), set()),
        )
        if classification:
            selected[item_id] = classification

    candidates: list[NormalizedCandidate] = []
    for row in variables:
        item_id = str(row.get("item_id") or "")
        classification = selected.get(item_id)
        item = items.get(item_id)
        if not classification or not item:
            continue
        variable_type = str(row.get("variable_type") or "")
        variable_name = str(row.get("variable_name") or "")
        canonical_key, mapping_confidence = infer_canonical_key(
            variable_type,
            variable_name,
            classification.component,
        )
        source_text = str(row.get("source_text") or "")
        source_class = infer_source_class(source_text)
        raw_unit = str(row.get("variable_unit") or "")
        candidates.append(
            NormalizedCandidate(
                raw_item_id=item_id,
                raw_structure_id=str(item.get("struct_id") or ""),
                bill_id=str(item.get("bill_id") or ""),
                item_name=str(item.get("item_name") or ""),
                item_category=str(item.get("item_category") or ""),
                route=classification.route,
                component=classification.component,
                raw_variable_type=variable_type,
                raw_variable_name=variable_name,
                canonical_key=canonical_key,
                raw_value=row.get("variable_value"),
                raw_unit=raw_unit,
                source_text=source_text,
                source_class=source_class,
                basis_year_candidates=extract_basis_year_candidates(
                    f"{variable_name} {source_text}"
                ),
                mapping_confidence=mapping_confidence,
                normalization_status=_normalization_status(
                    canonical_key,
                    row.get("variable_value"),
                    raw_unit,
                ),
                transfer_policy=infer_transfer_policy(source_class),
            )
        )
    return selected, candidates


def build_report(
    all_items: dict[str, dict[str, Any]],
    selected_items: dict[str, ItemClassification],
    candidates: list[NormalizedCandidate],
) -> dict[str, Any]:
    status = Counter(row.normalization_status for row in candidates)
    unmapped_names = Counter(
        row.raw_variable_name
        for row in candidates
        if row.normalization_status == "unmapped"
    )
    selected_structure_ids = {
        str(all_items[item_id].get("struct_id") or "")
        for item_id in selected_items
    }
    return {
        "scope": {
            "all_cost_items": len(all_items),
            "selected_structures": len(selected_structure_ids),
            "selected_items": len(selected_items),
            "selected_variables": len(candidates),
        },
        "items": {
            "route": dict(Counter(value.route for value in selected_items.values())),
            "component": dict(
                Counter(value.component for value in selected_items.values())
            ),
            "selection_confidence": dict(
                Counter(value.confidence for value in selected_items.values())
            ),
        },
        "variables": {
            "normalization_status": dict(status),
            "canonical_key": dict(
                Counter(row.canonical_key or "unmapped" for row in candidates)
            ),
            "source_class": dict(Counter(row.source_class for row in candidates)),
            "transfer_policy": dict(
                Counter(row.transfer_policy for row in candidates)
            ),
            "with_value": sum(row.raw_value is not None for row in candidates),
            "with_unit": sum(bool(row.raw_unit) for row in candidates),
            "with_source_text": sum(bool(row.source_text) for row in candidates),
            "with_exactly_one_basis_year": sum(
                len(row.basis_year_candidates) == 1 for row in candidates
            ),
            "top_unmapped_variable_names": [
                {"name": name, "count": count}
                for name, count in unmapped_names.most_common(40)
            ],
        },
        "decision": {
            "raw_reingestion_required": False,
            "recommended_next_step": (
                "Review item-scope false positives and the most frequent unmapped "
                "variable names, then freeze canonical keys before creating DB tables."
            ),
        },
    }


def _render_markdown(report: dict[str, Any]) -> str:
    scope = report["scope"]
    variables = report["variables"]
    statuses = variables["normalization_status"]
    mapped = statuses.get("mapped", 0)
    selected_variables = scope["selected_variables"]
    mapped_pct = (mapped / selected_variables * 100) if selected_variables else 0.0
    lines = [
        "# Organization/Admin Variable Audit v2",
        "",
        "This is a read-only normalization preview over the existing TAG raw layer.",
        "",
        "## Scope",
        "",
        f"- All cost items: {scope['all_cost_items']:,}",
        f"- Candidate structures: {scope['selected_structures']:,}",
        f"- Candidate items: {scope['selected_items']:,}",
        f"- Connected variables: {selected_variables:,}",
        "",
        "## Initial normalization",
        "",
        f"- Fully mapped with value and unit: {mapped:,} ({mapped_pct:.1f}%)",
        f"- Mapped but value missing: {statuses.get('mapped_missing_value', 0):,}",
        f"- Mapped but unit missing: {statuses.get('mapped_missing_unit', 0):,}",
        f"- Unmapped: {statuses.get('unmapped', 0):,}",
        "",
        "## Item components",
        "",
    ]
    for key, count in sorted(report["items"]["component"].items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"- {key}: {count:,}")
    lines.extend(["", "## Most frequent unmapped variables", ""])
    for row in variables["top_unmapped_variable_names"][:20]:
        lines.append(f"- {row['name']}: {row['count']:,}")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Do not reingest the corpus. Keep the existing rows immutable and add a "
            "versioned evidence sidecar. `comparable_only` and `review_required` values "
            "must not be selected as automatic constants.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit organization/admin variables without modifying the raw DB."
    )
    parser.add_argument(
        "--seed-dir",
        action="append",
        type=Path,
        dest="seed_dirs",
        help="Seed directory; repeat for multiple corpora.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--stdout", action="store_true", help="Print JSON report only.")
    args = parser.parse_args()

    seed_dirs = tuple(args.seed_dirs or DEFAULT_SEED_DIRS)
    missing = [path for path in seed_dirs if not path.exists()]
    if missing:
        raise SystemExit(f"missing seed directories: {', '.join(map(str, missing))}")

    items, variables = load_raw(seed_dirs)
    selected_items, candidates = build_candidates(items, variables)
    report = build_report(items, selected_items, candidates)
    if args.stdout:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "audit.json"
    preview_path = args.output_dir / "normalized_candidates.jsonl"
    markdown_path = args.output_dir / "report.md"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with preview_path.open("w", encoding="utf-8") as handle:
        for candidate in candidates:
            handle.write(json.dumps(asdict(candidate), ensure_ascii=False) + "\n")
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")

    print(f"report: {report_path}")
    print(f"preview: {preview_path}")
    print(f"summary: {markdown_path}")


if __name__ == "__main__":
    main()
