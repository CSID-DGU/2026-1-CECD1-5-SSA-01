"""Build committee profiles and operand-level evidence from existing TAG data.

This is an additive backfill.  It never deletes or rewrites the existing TAG
tables.  By default it writes deterministic JSONL artifacts only; ``--upload``
must be supplied explicitly after the SQL migration has been applied.

Example:
    python -m backend.legacy.scripts.backfill_committee_evidence
    python -m backend.legacy.scripts.backfill_committee_evidence --upload
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import urllib.error
import urllib.request
from typing import Any, Iterable

from backend.erce_web.config import GENERATED_DIR, get_env


EXTRACTION_VERSION = "committee-evidence-backfill-v1.1"
DEFAULT_SEED_DIRS = (
    GENERATED_DIR / "assembly_rag_seed",
    GENERATED_DIR / "assembly_rag_seed_22_ce",
)
DEFAULT_OUTPUT_DIR = GENERATED_DIR / "committee_evidence_v1"

_BODY = r"(?:위원회|심의회|협의회)"
_COMMITTEE_ITEM = re.compile(r"위원회|심의회|협의회|위원\s*수당|회의\s*수당")
_GENERIC_NAMES = {
    "위원회", "심의회", "협의회", "전문위원회", "분과위원회", "소위원회",
    "자문위원회", "실무위원회", "위원회심의", "위원회운영",
}
_ITEM_NAME = re.compile(rf"^(.{{2,80}}?{_BODY})")
_TITLE_NAME = re.compile(
    rf"제\d+조(?:의\d+)?\(([^()]{{2,70}}?{_BODY})(?:의?(?:설치|구성|운영|기능).*)?\)"
)
_DEFINED_NAME = re.compile(rf"([가-힣A-Za-z0-9ㆍ·]{{2,60}}{_BODY})\(이하")


def _compact(value: Any) -> str:
    compact = re.sub(r"\s+", "", str(value or ""))
    return re.sub(r"-\d+-", "", compact)


def _stable_key(prefix: str, *parts: Any) -> str:
    payload = "|".join(_compact(part).lower() for part in parts)
    return f"{prefix}:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]}"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _dedupe_rows(rows: Iterable[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for row in rows:
        identifier = str(row.get(key) or "")
        if identifier:
            values[identifier] = row
    return list(values.values())


def _clean_name(value: str) -> str | None:
    name = re.sub(r"\s+", " ", value or "").strip(" ·ㆍ･-()")
    name = re.sub(r"^(?:\d+개\s*)", "", name)
    normalized = _compact(name)
    normalized = re.sub(r"의?(?:설치|구성|운영|기능)$", "", normalized)
    if normalized in _GENERIC_NAMES or len(normalized) < 4:
        return None
    if len(normalized) > 60 or not re.search(_BODY + r"$", normalized):
        return None
    return name[: name.rfind("회") + 1] if name.endswith(("위원회", "심의회", "협의회")) else normalized


def committee_name_from_item(item_name: str) -> str | None:
    match = _ITEM_NAME.search(re.sub(r"\s+", " ", item_name or "").strip())
    return _clean_name(match.group(1)) if match else None


def committee_names_from_context(context: str) -> list[str]:
    compact = _compact(context)
    candidates = [*(_TITLE_NAME.findall(compact)), *(_DEFINED_NAME.findall(compact))]
    names: list[str] = []
    for candidate in candidates:
        name = _clean_name(candidate)
        if name and name not in names:
            names.append(name)
    return names


def _article_tokens(trigger_ref: str) -> tuple[str, ...]:
    return tuple(
        re.sub(r"\s+", "", value)
        for value in re.findall(r"제\s*\d+\s*조(?:의\s*\d+)?", trigger_ref or "")
    )


def select_context(
    chunks: list[dict[str, Any]],
    *,
    committee_name: str | None,
    trigger_ref: str,
    max_chunks: int = 5,
) -> tuple[str, list[str]]:
    name_key = _compact(committee_name)
    article_keys = _article_tokens(trigger_ref)
    scored: list[tuple[int, int, bool, str, str]] = []
    for chunk in chunks:
        text = str(chunk.get("text") or chunk.get("content") or "")
        compact = _compact(text)
        document_type = str(chunk.get("documentType") or chunk.get("document_type") or "unknown")
        score = 0
        if name_key and name_key in compact:
            score += 5
        score += 2 * sum(key in compact for key in article_keys)
        if re.search(rf"제\d+조(?:의\d+)?\([^)]*{_BODY}", compact):
            score += 1
        if score and document_type == "bill_text":
            score += 3
        elif score and document_type == "cost_estimate":
            score += 1
        # OCR can split a table row into a title-only chunk. Keep it eligible
        # as a last resort, but prefer chunks that contain an actual rule.
        if len(compact) < 80:
            score -= 5
        if re.search(r"구성|소속|둔다|둠|설치|위원장", compact):
            score += 2
        # Profile fields must come from the target provision, not from the
        # precedent discussion later in a cost-estimate report. Analogy text
        # remains available through variable/formula evidence atoms.
        is_analogy = bool(re.search(r"유사사례|유사한사례|준용|참고하여", compact))
        if is_analogy:
            score -= 8
        if score:
            scored.append((
                score,
                -int(chunk.get("chunkIndex") or chunk.get("chunk_index") or 0),
                is_analogy,
                text,
                document_type,
            ))
    scored.sort(reverse=True)
    clean = [row for row in scored if not row[2]]
    if clean:
        scored = clean
    selected: list[str] = []
    selected_keys: set[str] = set()
    source_types: list[str] = []
    for _, _, _, text, document_type in scored:
        text_key = _compact(text)
        if text_key not in selected_keys:
            selected.append(text)
            selected_keys.add(text_key)
            source_types.append(document_type)
        if len(selected) >= max_chunks:
            break
    return "\n".join(selected)[:12000], sorted(set(source_types))


def target_field_context(context: str, committee_name: str, *, radius: int = 550) -> str:
    """Return only windows that describe the named target committee."""
    compact = _compact(context)
    name_key = _compact(committee_name)
    windows: list[tuple[int, int, str]] = []
    for match in re.finditer(re.escape(name_key), compact):
        start = max(0, match.start() - radius)
        end = min(len(compact), match.end() + radius)
        window = compact[start:end]
        score = 0
        if re.search(r"둔다|둠|설치|구성|기능|심의|의결", window):
            score += 3
        if re.search(r"위원장|위원수|명이내|총\d+명|소속", window):
            score += 2
        if re.search(r"유사사례|현행.*위원회|참고하여|준용하여", window):
            score -= 3
        windows.append((score, -match.start(), window))
    windows.sort(reverse=True)
    selected: list[str] = []
    for _, _, window in windows:
        if window not in selected:
            selected.append(window)
        if len(selected) >= 3:
            break
    return " ".join(selected) if selected else compact


def _function_class(text: str) -> str:
    compact = _compact(text)
    if re.search(r"후보추천|추천위원회|선출ㆍ지명|선출·지명", compact):
        return "appointment_recommendation"
    if re.search(r"공론조사|공론절차|공론화|숙의|국민참여|시민참여|주민참여", compact):
        return "participatory_deliberation"
    if re.search(r"임금|보수|근로조건|노사|노동조건", compact):
        return "wage_bargaining"
    if re.search(r"수급추계|수요추계|공급추계|기술평가|안전성평가|영향평가", compact):
        return "technical_forecast_or_evaluation"
    if re.search(r"종합계획|기본계획|육성계획|발전계획|진흥계획|정책심의", compact):
        return "standing_strategy"
    if re.search(r"분쟁|징계|판정|심판|제재|조정신청|사건조정", compact):
        return "case_adjudication"
    return "general"


def _lifecycle(text: str) -> str:
    compact = _compact(text)
    if re.search(r"(?:선출|지명|추천|임명).{0,30}(?:때마다|할때마다)", compact):
        return "event_driven"
    if re.search(r"존속기한|한시적|활동기간|설립준비위원회", compact):
        return "temporary"
    if re.search(r"(?:둔다|둠|설치한다|구성한다|운영한다|설치·운영|설치및운영)", compact):
        return "standing"
    return "unknown"


def _member_count(text: str, committee_name: str = "") -> tuple[float | None, bool | None]:
    compact = _compact(text)
    patterns = (
        r"위원장\d*명을포함(?:하여|한)?(\d+)명이내?.{0,30}?구성",
        r"총\s*(\d+)명으로구성",
        r"(\d+)명의?추천?위원(?:회위원)?으로구성",
        rf"{_BODY}.{{0,100}}?(\d+)명이내?.{{0,20}}?구성",
    )
    name_positions = [
        match.start() for match in re.finditer(re.escape(_compact(committee_name)), compact)
    ] if committee_name else []
    candidates: list[tuple[int, int, re.Match[str]]] = []
    for pattern_index, pattern in enumerate(patterns):
        for match in re.finditer(pattern, compact):
            distance = min(
                (abs(match.start() - position) for position in name_positions),
                default=0,
            )
            nearby = compact[max(0, match.start() - 140):match.end() + 80]
            current_penalty = 1000 if re.search(r"현행|현재|기존", nearby) else 0
            legal_bonus = 500 if re.search(r"개정안|제\d+항|의무규정|하도록함", nearby) else 0
            candidates.append((current_penalty - legal_bonus + distance, pattern_index, match))
    for _, _, match in sorted(candidates, key=lambda row: (row[0], row[1])):
        if match:
            numeric = next(
                (value for value in match.groups() if value and value.isdigit()),
                None,
            )
            if numeric is not None:
                return float(numeric), "이내" in match.group(0)
    return None, None


def _parent_authority(text: str, committee_name: str = "") -> str | None:
    compact = _compact(text)
    target = re.escape(_compact(committee_name)) if committee_name else rf"[가-힣A-Za-z0-9ㆍ·]{{2,60}}{_BODY}"
    match = re.search(rf"(.{{2,100}}?)소속(?:으로|에|하에){target}", compact)
    if not match:
        return None
    prefix = re.split(r"에따른|따른|위하여|위해|위한", match.group(1))[-1]
    authority = re.search(
        r"([가-힣A-Za-z0-9ㆍ·]{2,45}위원회|국무총리|대통령|국회|[가-힣]{1,20}(?:부|처|청)?장관)$",
        prefix,
    )
    return authority.group(1) if authority else None


def _plan_period(text: str) -> float | None:
    compact = _compact(text)
    for pattern in (r"(\d+)년마다", r"(\d+)년주기", r"수립주기.{0,20}?(\d+)년"):
        match = re.search(pattern, compact)
        if match and 1 <= int(match.group(1)) <= 20:
            return float(match.group(1))
    return None


def classify_evidence_role(variable: dict[str, Any]) -> str:
    variable_type = str(variable.get("variable_type") or "").lower()
    variable_name = _compact(variable.get("variable_name") or "")
    variable_unit = _compact(variable.get("variable_unit") or "")
    variable_source = _compact(variable.get("source_text") or "")
    text = _compact(
        f"{variable.get('variable_name') or ''} {variable.get('variable_unit') or ''} "
        f"{variable.get('source_text') or ''}"
    )
    if variable_type == "target_count":
        if "건" in variable_unit and not re.search(r"위원|인원|사람", variable_name):
            return "case_volume"
        if (
            "개" in variable_unit
            or re.search(r"위원회수|위원회개수|협의회수|심의회수|기관수|자치단체수", variable_name)
        ):
            return "committee_instances"
        if (
            re.search(r"추가|순증|증원|차이", variable_name)
            or re.search(r"(?:추가되는|증가하는|차이인|순증(?:하는)?)(?:위원)?\d+명", variable_source)
        ):
            return "incremental_paid_members"
        if re.search(r"민간|위촉|비상임|외부위원|수당지급대상|회의수당대상", variable_name):
            return "paid_members"
        if re.search(r"당연직|공무원|정부위원", variable_name):
            return "public_official_members"
        if re.search(r"위원수|전체위원|총위원|구성위원|참여위원", variable_name):
            return "total_members"
        return "target_count"
    if variable_type == "unit_cost":
        if re.search(r"회의|수당|사례금|안건검토", text):
            return "meeting_unit_price"
        return "other_unit_cost"
    if variable_type == "frequency":
        if (
            "건" in variable_unit
            and re.search(r"심의건수|처리건수|회의당.*건수", text)
        ):
            return "cases_per_meeting"
        if re.search(r"구성건수|구성횟수|선출건수|지명건수|추천건수", variable_name):
            return "events_per_year"
        if re.search(r"회의|개최|개회", variable_name):
            return "meetings_per_event" if "위원회당" in variable_name else "annual_meetings"
        if re.search(r"회의|개최|개회", text):
            return "annual_meetings"
        if re.search(r"계획|주기", text):
            return "plan_period"
        return "frequency"
    if variable_type == "period":
        return "plan_period" if re.search(r"계획|수립|주기", text) else "estimate_period"
    if variable_type == "rate":
        return "rate"
    return "other"


def normalize_value(value: Any, unit: str, role: str) -> tuple[float | None, str | None]:
    if value is None or value == "":
        return None, unit or None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, unit or None
    compact_unit = _compact(unit)
    if role in {"meeting_unit_price", "other_unit_cost"}:
        if "억원" in compact_unit:
            return number * 100_000_000, "원"
        if "백만원" in compact_unit:
            return number * 1_000_000, "원"
        if "만원" in compact_unit:
            return number * 10_000, "원"
        if "천원" in compact_unit:
            return number * 1_000, "원"
        return number, "원" if "원" in compact_unit else unit or None
    if role in {"annual_meetings", "meetings_per_event", "events_per_year", "frequency"}:
        return number, "회/년" if "회" in compact_unit else unit or None
    if role in {
        "paid_members", "incremental_paid_members", "public_official_members",
        "total_members", "target_count", "committee_instances", "case_volume",
    }:
        return number, "명" if "명" in compact_unit else unit or None
    if role in {"plan_period", "estimate_period"}:
        return number, "년" if "년" in compact_unit else unit or None
    return number, unit or None


def _derivation(source_text: str) -> tuple[str, str, list[str]]:
    compact = _compact(source_text)
    flags: list[str] = []
    if re.search(r"역산|산출금액.{0,20}적용", compact):
        return "reverse_engineered", "do_not_transfer", ["REVERSE_ENGINEERED_VALUE"]
    if re.search(r"유사사례|유사한사례|준용|참고하여|참조하여", compact):
        flags.append("ANALOGY_DERIVED")
        return "analogy", "review", flags
    if re.search(r"가정|추정", compact):
        flags.append("ASSUMPTION")
        return "assumption", "review", flags
    if re.search(r"예산.*지침|집행지침|기준단가", compact):
        return "official_guideline", "direct", flags
    if re.search(r"운영실적|개최실적|현황|실제.{0,10}개최", compact):
        return "reported_actual", "direct", flags
    return "direct_statement", "review", flags


def _formula_scope(item_name: str, source_text: str) -> str:
    compact = _compact(f"{item_name} {source_text}")
    has_main = bool(re.search(r"본위원회|본회의", compact))
    has_sub = bool(re.search(r"분과위원회|소위원회|실무위원회", compact))
    if has_main and has_sub:
        return "combined"
    if has_sub:
        return "subcommittee"
    if re.search(_BODY, compact):
        return "main_committee"
    return "unknown"


def _basis_year(text: str) -> int | None:
    years = [int(value) for value in re.findall(r"(?<!\d)(20\d{2})년", text or "")]
    return max(years) if years else None


_COMMITTEE_PRODUCT = re.compile(
    r"민간위원(\d+)명[×xX*](?:회의)?참석수당(?:단가)?"
    r"(\d+(?:\.\d+)?)(억원|백만원|만원|천원|원)"
    r"[×xX*]회의(?:개최)?횟수(\d+)회"
)


def recover_formula_operands(
    chunks: list[dict[str, Any]], committee_name: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Recover only an explicit committee product printed in the report.

    This is intentionally narrower than free-form number extraction. It fills
    a known ingestion gap while retaining the exact equation as provenance.
    """
    name_key = _compact(committee_name)
    for chunk in chunks:
        if str(chunk.get("documentType") or chunk.get("document_type")) != "cost_estimate":
            continue
        text = str(chunk.get("text") or chunk.get("content") or "")
        compact = _compact(text)
        if name_key not in compact:
            continue
        for match in _COMMITTEE_PRODUCT.finditer(compact):
            name_positions = [item.start() for item in re.finditer(re.escape(name_key), compact)]
            if not name_positions or min(abs(position - match.start()) for position in name_positions) > 2000:
                continue
            paid, price, price_unit, meetings = match.groups()
            equation = match.group(0)
            source = compact[max(0, match.start() - 1200):match.end() + 400]
            return [
                {
                    "variable_type": "target_count",
                    "variable_name": "민간위원 수",
                    "variable_value": float(paid),
                    "variable_unit": "명",
                    "source_text": source,
                    "recovered_from_report_text": True,
                },
                {
                    "variable_type": "unit_cost",
                    "variable_name": "회의 참석수당",
                    "variable_value": float(price),
                    "variable_unit": price_unit,
                    "source_text": source,
                    "recovered_from_report_text": True,
                },
                {
                    "variable_type": "frequency",
                    "variable_name": "연간 회의 개최 횟수",
                    "variable_value": float(meetings),
                    "variable_unit": "회/년",
                    "source_text": source,
                    "recovered_from_report_text": True,
                },
            ], equation
    return [], None


def _jsonl_write(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def load_seed(seed_dirs: Iterable[Path]) -> dict[str, list[dict[str, Any]]]:
    names = (
        "cost_estimate_structures", "cost_estimate_items", "cost_estimate_variables",
        "cost_estimate_amounts", "bill_text_for_tag", "chunks",
    )
    result: dict[str, list[dict[str, Any]]] = {name: [] for name in names}
    for directory in seed_dirs:
        for name in names:
            result[name].extend(_read_jsonl(directory / f"{name}.jsonl"))
    result["cost_estimate_structures"] = _dedupe_rows(result["cost_estimate_structures"], "struct_id")
    result["cost_estimate_items"] = _dedupe_rows(result["cost_estimate_items"], "item_id")
    result["bill_text_for_tag"] = _dedupe_rows(result["bill_text_for_tag"], "chunkId")
    result["chunks"] = _dedupe_rows(result["chunks"], "chunkId")
    return result


def build_backfill(data: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    structures = {
        str(row.get("struct_id") or ""): row
        for row in data["cost_estimate_structures"]
        if row.get("struct_id")
    }
    variables_by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for variable in data["cost_estimate_variables"]:
        variables_by_item[str(variable.get("item_id") or "")].append(variable)
    amounts_by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for amount in data["cost_estimate_amounts"]:
        amounts_by_item[str(amount.get("item_id") or "")].append(amount)
    chunks_by_bill: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in [*data.get("bill_text_for_tag", []), *data.get("chunks", [])]:
        chunks_by_bill[str(chunk.get("billId") or "")].append(chunk)

    profiles: dict[str, dict[str, Any]] = {}
    atoms: dict[str, dict[str, Any]] = {}
    skipped: Counter[str] = Counter()
    source_item_count = 0

    for item in data["cost_estimate_items"]:
        item_name = str(item.get("item_name") or "")
        if not _COMMITTEE_ITEM.search(item_name):
            continue
        source_item_count += 1
        item_id = str(item.get("item_id") or "")
        struct_id = str(item.get("struct_id") or "")
        structure = structures.get(struct_id) or {}
        bill_id = str(item.get("bill_id") or structure.get("bill_id") or "")
        if not bill_id:
            skipped["missing_bill_id"] += 1
            continue
        trigger_ref = str(item.get("trigger_ref") or "")
        name = committee_name_from_item(item_name)
        context, source_document_types = select_context(
            chunks_by_bill.get(bill_id, []),
            committee_name=name,
            trigger_ref=trigger_ref,
        )
        if name is None:
            names = committee_names_from_context(context)
            if len(names) == 1:
                name = names[0]
            else:
                skipped["ambiguous_or_generic_name"] += 1
                continue
        if not context:
            skipped["missing_source_context"] += 1

        normalized_name = _compact(name)
        profile_key = _stable_key("committee", bill_id, normalized_name)
        field_context = target_field_context(context, name)
        count, is_cap = _member_count(field_context, name)
        profile_provenance = (
            "bill_text" if "bill_text" in source_document_types
            else "cost_estimate_restatement"
        )
        source_refs = {trigger_ref} if trigger_ref else set()
        existing = profiles.get(profile_key)
        if existing:
            source_refs.update(existing["raw_attributes"].get("source_refs") or [])
            source_items = set(existing["raw_attributes"].get("source_item_keys") or [])
            source_items.add(item_id)
            if context and context not in existing["source_text"]:
                existing["source_text"] = (existing["source_text"] + "\n" + context)[:12000]
            existing["raw_attributes"]["source_refs"] = sorted(source_refs)
            existing["raw_attributes"]["source_item_keys"] = sorted(source_items)
            existing_types = set(existing["raw_attributes"].get("source_document_types") or [])
            existing_types.update(source_document_types)
            existing["raw_attributes"]["source_document_types"] = sorted(existing_types)
            if "bill_text" in existing_types:
                existing["profile_provenance"] = "bill_text"
            if existing["total_member_count"] is None and count is not None:
                existing["total_member_count"] = count
                existing["member_count_is_cap"] = is_cap
            profile = existing
        else:
            profile = {
                "profile_key": profile_key,
                "bill_id": bill_id,
                "bill_no": structure.get("bill_no"),
                "bill_name": structure.get("bill_name"),
                "propose_date": structure.get("propose_date"),
                "committee_name": name,
                "normalized_name": normalized_name,
                "source_article_ref": trigger_ref or None,
                "source_text": context or None,
                "profile_provenance": profile_provenance,
                "lifecycle": _lifecycle(field_context),
                "function_class": _function_class(f"{name} {field_context}"),
                "parent_authority": _parent_authority(field_context, name),
                "total_member_count": count,
                "member_count_is_cap": is_cap,
                "paid_member_count": None,
                "public_official_count": None,
                "has_subcommittee": bool(re.search(r"분과위원회|소위원회|실무위원회", field_context)),
                "has_secretariat": bool(re.search(r"사무처|사무국|지원단", field_context)),
                "plan_period_years": _plan_period(field_context),
                "formula_signature": None,
                "profile_status": "partial" if context else "needs_review",
                "requires_review": profile_provenance != "bill_text",
                "extraction_method": "deterministic_backfill",
                "extraction_version": EXTRACTION_VERSION,
                "raw_attributes": {
                    "source_refs": sorted(source_refs),
                    "source_item_keys": [item_id],
                    "source_document_types": source_document_types,
                    "profile_field_context": field_context,
                },
            }
            profiles[profile_key] = profile

        roles: set[str] = set()
        paid_values: list[float] = []
        public_values: list[float] = []
        total_values: list[float] = []
        item_variables = list(variables_by_item.get(item_id, []))
        existing_roles = {classify_evidence_role(variable) for variable in item_variables}
        recovered_formula: str | None = None
        core_roles = {"paid_members", "annual_meetings", "meeting_unit_price"}
        if not core_roles.issubset(existing_roles):
            recovered_variables, recovered_formula = recover_formula_operands(
                chunks_by_bill.get(bill_id, []), name,
            )
            for variable in recovered_variables:
                if classify_evidence_role(variable) not in existing_roles:
                    item_variables.append(variable)
        for variable in item_variables:
            role = classify_evidence_role(variable)
            roles.add(role)
            raw_value = variable.get("variable_value")
            raw_unit = str(variable.get("variable_unit") or "")
            normalized_value, normalized_unit = normalize_value(raw_value, raw_unit, role)
            source_text = str(variable.get("source_text") or "")
            derivation, transferability, quality_flags = _derivation(source_text)
            if variable.get("recovered_from_report_text"):
                quality_flags = [*quality_flags, "RECOVERED_FROM_REPORT_TEXT"]
            scope = _formula_scope(item_name, source_text)
            atom_key = _stable_key(
                "evidence", profile_key, item_id, role, raw_value, raw_unit, source_text,
            )
            atom = {
                "atom_key": atom_key,
                "profile_key": profile_key,
                "bill_id": bill_id,
                "source_item_key": item_id,
                "evidence_role": role,
                "raw_value": raw_value,
                "text_value": None,
                "raw_unit": raw_unit or None,
                "normalized_value": normalized_value,
                "normalized_unit": normalized_unit,
                "formula_text": None,
                "formula_scope": scope,
                "provenance_type": "cost_estimate",
                "derivation_type": derivation,
                "transferability": transferability,
                "source_ref": trigger_ref or None,
                "source_text": source_text or None,
                "basis_year": _basis_year(source_text),
                "valid_from": None,
                "valid_to": None,
                "review_status": "candidate",
                "quality_flags": quality_flags,
            }
            atoms[atom_key] = atom
            if normalized_value is not None:
                if role == "paid_members":
                    paid_values.append(normalized_value)
                elif role == "public_official_members":
                    public_values.append(normalized_value)
                elif role == "total_members":
                    total_values.append(normalized_value)

        formulas = sorted({
            str(amount.get("formula_text") or "").strip()
            for amount in amounts_by_item.get(item_id, [])
            if str(amount.get("formula_text") or "").strip()
        })
        if recovered_formula:
            formulas = sorted({*formulas, recovered_formula})
        for formula in formulas:
            atom_key = _stable_key("evidence", profile_key, item_id, "formula_expression", formula)
            atoms[atom_key] = {
                "atom_key": atom_key,
                "profile_key": profile_key,
                "bill_id": bill_id,
                "source_item_key": item_id,
                "evidence_role": "formula_expression",
                "raw_value": None,
                "text_value": None,
                "raw_unit": None,
                "normalized_value": None,
                "normalized_unit": None,
                "formula_text": formula,
                "formula_scope": _formula_scope(item_name, formula),
                "provenance_type": "cost_estimate",
                "derivation_type": "direct_statement",
                "transferability": "review",
                "source_ref": trigger_ref or None,
                "source_text": formula,
                "basis_year": _basis_year(formula),
                "valid_from": None,
                "valid_to": None,
                "review_status": "candidate",
                "quality_flags": [],
            }

        if {"paid_members", "annual_meetings", "meeting_unit_price"}.issubset(roles):
            prefix = "committee_instances*" if "committee_instances" in roles else ""
            profile["formula_signature"] = f"{prefix}paid_members*annual_meetings*meeting_unit_price"
        elif {"incremental_paid_members", "annual_meetings", "meeting_unit_price"}.issubset(roles):
            prefix = "committee_instances*" if "committee_instances" in roles else ""
            profile["formula_signature"] = f"{prefix}incremental_paid_members*annual_meetings*meeting_unit_price"
        elif formulas and not profile["formula_signature"]:
            profile["formula_signature"] = "unparsed_formula"

        def stable_single(values: list[float]) -> float | None:
            unique = sorted(set(values))
            return unique[0] if len(unique) == 1 else None

        for field, values in (
            ("paid_member_count", paid_values),
            ("public_official_count", public_values),
            ("total_member_count", total_values),
        ):
            value = stable_single(values)
            if value is not None and profile.get(field) is None:
                profile[field] = value
        if context and profile["formula_signature"]:
            profile["profile_status"] = "partial"

    # Preserve the exact source behind every derived profile field. These are
    # descriptive legal facts, so they are searchable but not directly copied
    # into another bill as numeric assumptions.
    for profile in profiles.values():
        source_text = str(profile.get("source_text") or "")
        field_context = target_field_context(source_text, str(profile["committee_name"]))
        profile["raw_attributes"]["profile_field_context"] = field_context
        profile["lifecycle"] = _lifecycle(field_context)
        profile["function_class"] = _function_class(
            f"{profile['committee_name']} {field_context}"
        )
        profile["parent_authority"] = _parent_authority(
            field_context, str(profile["committee_name"])
        )
        legal_count, legal_is_cap = _member_count(
            field_context, str(profile["committee_name"])
        )
        if legal_count is not None:
            profile["total_member_count"] = legal_count
            profile["member_count_is_cap"] = legal_is_cap
        profile["has_subcommittee"] = bool(
            re.search(r"분과위원회|소위원회|실무위원회", field_context)
        )
        profile["has_secretariat"] = bool(re.search(r"사무처|사무국|지원단", field_context))
        profile["plan_period_years"] = _plan_period(field_context)

        quality_issues = list(profile["raw_attributes"].get("quality_issues") or [])
        total_count = profile.get("total_member_count")
        paid_count = profile.get("paid_member_count")
        if total_count is not None and total_count > 100:
            profile["raw_attributes"]["rejected_total_member_count"] = total_count
            profile["total_member_count"] = None
            profile["member_count_is_cap"] = None
            quality_issues.append("IMPLAUSIBLE_MEMBER_COUNT")
        elif total_count is not None and paid_count is not None and paid_count > total_count:
            profile["raw_attributes"]["rejected_total_member_count"] = total_count
            profile["total_member_count"] = None
            profile["member_count_is_cap"] = None
            quality_issues.append("PAID_MEMBERS_EXCEED_TOTAL")
        profile["raw_attributes"]["quality_issues"] = sorted(set(quality_issues))

        provenance = str(profile.get("profile_provenance") or "cost_estimate_restatement")
        source_ref = profile.get("source_article_ref")
        legal_flags = [] if provenance == "bill_text" else ["SECONDARY_LEGAL_RESTATEMENT"]
        legal_values = (
            ("profile_lifecycle", profile.get("lifecycle"), None, None),
            ("profile_function_class", profile.get("function_class"), None, None),
            ("profile_parent_authority", profile.get("parent_authority"), None, None),
            ("profile_total_members", None, profile.get("total_member_count"), "명"),
            ("profile_has_subcommittee", str(bool(profile.get("has_subcommittee"))).lower(), None, None),
            ("profile_has_secretariat", str(bool(profile.get("has_secretariat"))).lower(), None, None),
        )
        for role, text_value, numeric_value, unit in legal_values:
            if role in {"profile_has_subcommittee", "profile_has_secretariat"} and text_value == "false":
                continue
            if text_value in (None, "unknown", "general") and numeric_value is None:
                continue
            atom_key = _stable_key("evidence", profile["profile_key"], "profile", role)
            atoms[atom_key] = {
                "atom_key": atom_key,
                "profile_key": profile["profile_key"],
                "bill_id": profile["bill_id"],
                "source_item_key": None,
                "evidence_role": role,
                "raw_value": numeric_value,
                "text_value": text_value,
                "raw_unit": unit,
                "normalized_value": numeric_value,
                "normalized_unit": unit,
                "formula_text": None,
                "formula_scope": "unknown",
                "provenance_type": provenance,
                "derivation_type": "direct_statement",
                "transferability": "do_not_transfer",
                "source_ref": source_ref,
                "source_text": field_context or None,
                "basis_year": _basis_year(field_context),
                "valid_from": None,
                "valid_to": None,
                "review_status": "candidate",
                "quality_flags": legal_flags,
            }

        profile["requires_review"] = bool(
            provenance != "bill_text"
            or profile.get("lifecycle") == "unknown"
            or not source_text
            or bool(profile["raw_attributes"].get("quality_issues"))
        )
        has_core_formula = (
            profile.get("formula_signature") in {
                "paid_members*annual_meetings*meeting_unit_price",
                "incremental_paid_members*annual_meetings*meeting_unit_price",
                "committee_instances*paid_members*annual_meetings*meeting_unit_price",
                "committee_instances*incremental_paid_members*annual_meetings*meeting_unit_price",
            }
        )
        has_legal_size = profile.get("total_member_count") is not None
        has_lifecycle = profile.get("lifecycle") != "unknown"
        if source_text and has_core_formula and has_legal_size and has_lifecycle:
            profile["profile_status"] = "complete"
        elif source_text:
            profile["profile_status"] = "partial"
        else:
            profile["profile_status"] = "needs_review"

    profile_rows = sorted(profiles.values(), key=lambda row: row["profile_key"])
    atom_rows = sorted(atoms.values(), key=lambda row: row["atom_key"])
    role_counts = Counter(str(row["evidence_role"]) for row in atom_rows)
    derivation_counts = Counter(str(row["derivation_type"]) for row in atom_rows)
    status_counts = Counter(str(row["profile_status"]) for row in profile_rows)
    lifecycle_counts = Counter(str(row["lifecycle"]) for row in profile_rows)
    source_type_counts: Counter[str] = Counter()
    for row in profile_rows:
        for source_type in row["raw_attributes"].get("source_document_types") or []:
            source_type_counts[str(source_type)] += 1
    orphan_atoms = sum(row["profile_key"] not in profiles for row in atom_rows)
    summary = {
        "extraction_version": EXTRACTION_VERSION,
        "source_committee_items": source_item_count,
        "profiles": len(profile_rows),
        "evidence_atoms": len(atom_rows),
        "profile_status": dict(sorted(status_counts.items())),
        "lifecycle": dict(sorted(lifecycle_counts.items())),
        "source_document_types": dict(sorted(source_type_counts.items())),
        "evidence_roles": dict(sorted(role_counts.items())),
        "derivation_types": dict(sorted(derivation_counts.items())),
        "skipped": dict(sorted(skipped.items())),
        "quality": {
            "duplicate_profile_keys": len(profile_rows) - len({row["profile_key"] for row in profile_rows}),
            "duplicate_atom_keys": len(atom_rows) - len({row["atom_key"] for row in atom_rows}),
            "orphan_atoms": orphan_atoms,
            "profiles_with_source_text": sum(bool(row.get("source_text")) for row in profile_rows),
            "profiles_requiring_review": sum(bool(row.get("requires_review")) for row in profile_rows),
            "profiles_with_quarantined_fields": sum(
                bool(row["raw_attributes"].get("quality_issues")) for row in profile_rows
            ),
            "recovered_operand_atoms": sum(
                "RECOVERED_FROM_REPORT_TEXT" in (row.get("quality_flags") or [])
                for row in atom_rows
            ),
            "profiles_with_complete_formula": sum(
                bool(row.get("formula_signature"))
                and row.get("formula_signature") != "unparsed_formula"
                for row in profile_rows
            ),
        },
    }
    return profile_rows, atom_rows, summary


def _upload_batch(base_url: str, key: str, table: str, rows: list[dict[str, Any]], conflict: str) -> None:
    for index in range(0, len(rows), 100):
        payload = json.dumps(rows[index:index + 100], ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/rest/v1/{table}?on_conflict={conflict}",
            data=payload,
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"{table} upload failed: HTTP {error.code}: {detail}") from error


def upload(profiles: list[dict[str, Any]], atoms: list[dict[str, Any]]) -> None:
    base_url = get_env("SUPABASE_URL").rstrip("/")
    key = get_env("SUPABASE_SERVICE_ROLE_KEY")
    if not base_url or not key:
        raise SystemExit("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY가 필요합니다.")
    _upload_batch(base_url, key, "committee_profiles", profiles, "profile_key")
    _upload_batch(base_url, key, "committee_evidence_atoms", atoms, "atom_key")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="기존 TAG에서 위원회 증거 계층을 백필합니다.")
    parser.add_argument("--seed-dir", type=Path, action="append", dest="seed_dirs")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--upload", action="store_true", help="SQL migration 적용 후 원격 DB에 upsert")
    parser.add_argument("--no-write", action="store_true", help="JSONL 산출물을 쓰지 않고 요약만 출력")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seed_dirs = tuple(args.seed_dirs or DEFAULT_SEED_DIRS)
    data = load_seed(seed_dirs)
    profiles, atoms, summary = build_backfill(data)
    if summary["quality"]["duplicate_profile_keys"] or summary["quality"]["duplicate_atom_keys"] or summary["quality"]["orphan_atoms"]:
        raise SystemExit(f"quality gate failed: {summary['quality']}")
    if not args.no_write:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        _jsonl_write(args.output_dir / "committee_profiles.jsonl", profiles)
        _jsonl_write(args.output_dir / "committee_evidence_atoms.jsonl", atoms)
        (args.output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.upload:
        upload(profiles, atoms)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
