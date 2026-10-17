"""Build an isolated evidence/search DB for the goods-services pilot.

The existing TAG, sidecar and Supabase data are read-only inputs.  The output is
an independent SQLite file so the v2 schema can be inspected and discarded
without changing production candidates.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import time
from typing import Any, Iterator
import uuid

import fitz  # type: ignore[import-untyped]

from backend.legacy.engines.general_cost_precedent_selector import infer_mechanism, infer_priced_scopes


ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "backend/migrations/20260927_general_cost_v2_pilot.sqlite.sql"
SIDECAR_DIR = ROOT / "backend/generated/general_cost_sidecar_v1"
PDF_ROOT = ROOT / "backend/generated/assembly_22_pdfs/by_bill"
HOLDOUT_MANIFEST = ROOT / "backend/generated/assembly_22_validation_holdout_v1/manifest.jsonl"
EMBEDDING_PATH = ROOT / "backend/generated/tag_item_embeddings.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "backend/generated/general_cost_v2_pilot_goods_services"
DEFAULT_DB = DEFAULT_OUTPUT_DIR / "pilot.sqlite3"
DEFAULT_EXPORT_DIR = DEFAULT_OUTPUT_DIR / "supabase_migration_bundle"

SCHEMA_VERSION = "general-cost-evidence-v2-pilot"
PIPELINE_VERSION = "goods-services-pilot-loader-v1"
PARSER_VERSION = f"pymupdf:{getattr(fitz, '__version__', 'unknown')}"
PILOT_BILL_NOS = ("2211831", "2215597", "2213147", "2213203", "2212387")

MIGRATION_TABLE_ORDER = (
    "schema_meta", "ingestion_runs", "ingestion_stages", "dataset_splits",
    "documents", "document_chunks", "chunk_embeddings", "formula_templates", "cost_items",
    "item_formula_links", "variables", "amount_observations", "evidence_links",
    "item_embeddings",
)
JSON_COLUMNS = {
    "ingestion_runs": {"metrics_json"},
    "ingestion_stages": {"details_json"},
    "formula_templates": {
        "cost_natures_json", "required_variables_json", "optional_variables_json",
        "applicability_json",
    },
    "cost_items": {
        "priced_scopes_json", "implementing_agencies_json", "policy_domains_json",
        "quality_flags_json",
    },
    "item_formula_links": {"missing_variables_json"},
    "variables": {"quality_flags_json"},
}
TARGET_TABLES = {
    table: f"public.general_cost_v2_{table}" for table in MIGRATION_TABLE_ORDER
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def stable_key(prefix: str, *values: Any) -> str:
    payload = "\x1f".join(str(value or "") for value in values)
    return f"{prefix}:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def measured(stages: dict[str, dict[str, Any]], name: str) -> Iterator[dict[str, Any]]:
    state: dict[str, Any] = {"record_count": 0, "failure_count": 0, "details": {}}
    started = time.perf_counter()
    try:
        yield state
    finally:
        state["duration_ms"] = round((time.perf_counter() - started) * 1000)
        stages[name] = state


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _compact(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", text or "").lower()


def _ngrams(text: str, n: int = 3) -> set[str]:
    compact = _compact(text)
    if not compact:
        return set()
    if len(compact) <= n:
        return {compact}
    return {compact[index:index + n] for index in range(len(compact) - n + 1)}


def locate_quote(pages: list[str], quote: str) -> tuple[int | None, str, float]:
    compact_quote = _compact(quote)
    if not compact_quote:
        return None, "unresolved", 0.0
    for page_no, page in enumerate(pages, start=1):
        if compact_quote in _compact(page):
            return page_no, "exact", 1.0
    query_grams = _ngrams(quote)
    best_page: int | None = None
    best_score = 0.0
    for page_no, page in enumerate(pages, start=1):
        page_grams = _ngrams(page)
        containment = len(query_grams & page_grams) / max(len(query_grams), 1)
        prefix = SequenceMatcher(None, compact_quote[:240], _compact(page)[:2000]).ratio()
        score = max(containment, prefix * 0.7)
        if score > best_score:
            best_page, best_score = page_no, score
    if best_page is not None and best_score >= 0.42:
        return best_page, "fuzzy", round(best_score, 6)
    return None, "unresolved", round(best_score, 6)


def source_excerpt(page: str, locator_query: str, radius: int = 2) -> str:
    """Return a short verbatim page excerpt around the closest matching line."""
    lines = [line.strip() for line in page.splitlines() if line.strip()]
    if not lines:
        return ""
    query_grams = _ngrams(locator_query)
    best_index, best_score = 0, -1.0
    for index, line in enumerate(lines):
        line_grams = _ngrams(line)
        score = len(query_grams & line_grams) / max(len(query_grams), 1)
        if score > best_score:
            best_index, best_score = index, score
    start = max(0, best_index - radius)
    end = min(len(lines), best_index + radius + 1)
    return " / ".join(lines[start:end])[:1200]


def amount_locator_query(row: dict[str, Any], item_name: str) -> str:
    """Build a page-location query from the item, year and normalized amount."""
    parts = [item_name, str(row.get("year_label") or "")]
    amount = row.get("amount_thousand")
    if isinstance(amount, (int, float)):
        million = float(amount) / 1000.0
        parts.extend((f"{million:g}", f"{million:,.1f}".rstrip("0").rstrip(".")))
    return " ".join(part for part in parts if part)


def extract_pages(path: Path) -> list[str]:
    with fitz.open(path) as document:
        return [page.get_text("text").strip() for page in document]


def load_embeddings() -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    for row in read_jsonl(EMBEDDING_PATH):
        item_id = str(row.get("item_id") or "")
        vector = row.get("emb")
        if item_id and isinstance(vector, list) and vector:
            result[item_id] = [float(value) for value in vector]
    return result


def export_migration_bundle(database: Path, output_dir: Path) -> dict[str, Any]:
    """Export FK-ordered JSONL with JSON/vector values ready for PostgreSQL."""
    output_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    row_counts: dict[str, int] = {}
    file_hashes: dict[str, str] = {}
    for table in MIGRATION_TABLE_ORDER:
        rows = []
        for raw in connection.execute(f"select * from {table}"):
            row = dict(raw)
            for column in JSON_COLUMNS.get(table, set()):
                if row.get(column) is not None:
                    row[column] = json.loads(row[column])
            if table == "amount_observations":
                row["is_total"] = bool(row["is_total"])
            if table == "item_embeddings":
                row["embedding"] = json.loads(row.pop("vector_json"))
            rows.append(row)
        payload = "".join(_json(row) + "\n" for row in rows)
        path = output_dir / f"{table}.jsonl"
        path.write_text(payload, encoding="utf-8")
        row_counts[table] = len(rows)
        file_hashes[path.name] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    connection.close()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "target": "Supabase PostgreSQL + pgvector",
        "target_schema": "public general_cost_v2_* tables",
        "table_order": list(MIGRATION_TABLE_ORDER),
        "target_tables": TARGET_TABLES,
        "row_counts": row_counts,
        "sha256": file_hashes,
        "type_mapping": {
            "*_json": "jsonb",
            "item_embeddings.embedding": "vector(1536)",
            "document_chunks_fts": "generated tsvector + GIN index; not exported",
            "cost_items_fts": "generated tsvector + GIN index; not exported",
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def build_database(output_path: Path, bill_nos: tuple[str, ...] = PILOT_BILL_NOS) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    holdout_rows = read_jsonl(HOLDOUT_MANIFEST)
    holdout_bill_nos = {str(row.get("bill_no") or "") for row in holdout_rows}
    overlap = sorted(set(bill_nos) & holdout_bill_nos)
    if overlap:
        raise RuntimeError(f"validation holdout leakage: {overlap}")

    document_profiles = {
        str(row.get("bill_id") or ""): row
        for row in read_jsonl(SIDECAR_DIR / "document_profiles.jsonl")
    }
    item_profiles = [
        row for row in read_jsonl(SIDECAR_DIR / "item_profiles.jsonl")
        if row.get("cost_nature") == "goods_services"
        and str(row.get("bill_no") or "") in set(bill_nos)
    ]
    if not item_profiles:
        raise RuntimeError("pilot item profiles not found")
    item_profiles.sort(key=lambda row: (bill_nos.index(str(row.get("bill_no"))), str(row.get("profile_key"))))
    selected_profile_keys = {str(row["profile_key"]) for row in item_profiles}
    variables = [
        row for row in read_jsonl(SIDECAR_DIR / "variable_evidence.jsonl")
        if str(row.get("profile_key")) in selected_profile_keys
    ]
    amounts = [
        row for row in read_jsonl(SIDECAR_DIR / "amount_observations.jsonl")
        if str(row.get("profile_key")) in selected_profile_keys
    ]
    formulas = read_jsonl(SIDECAR_DIR / "formula_definitions.jsonl")
    embeddings = load_embeddings()

    variables_by_profile: dict[str, list[dict[str, Any]]] = defaultdict(list)
    amounts_by_profile: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in variables:
        variables_by_profile[str(row.get("profile_key"))].append(row)
    for row in amounts:
        amounts_by_profile[str(row.get("profile_key"))].append(row)

    run_id = f"pilot:{uuid.uuid4().hex}"
    started_at = utc_now()
    stages: dict[str, dict[str, Any]] = {}

    temporary = Path(tempfile.mkstemp(prefix="goods-v2-", suffix=".sqlite3", dir=output_path.parent)[1])
    try:
        connection = sqlite3.connect(temporary)
        connection.row_factory = sqlite3.Row
        connection.execute("pragma foreign_keys = on")
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        connection.execute(
            "insert into schema_meta values (?, ?, ?, ?)",
            (SCHEMA_VERSION, "02_goods_services", started_at, "isolated five-document pilot"),
        )
        connection.execute(
            "insert into ingestion_runs values (?, ?, ?, ?, ?, null, 'running', ?, '{}')",
            (run_id, PIPELINE_VERSION, "goods_services", "sidecar_v1_plus_raw_pdf", started_at, len(bill_nos)),
        )

        pages_by_document: dict[str, list[str]] = {}
        chunk_by_page: dict[tuple[str, int], str] = {}
        metadata_by_bill_no: dict[str, dict[str, Any]] = {}

        with measured(stages, "parse_source_documents") as stage:
            for bill_no in bill_nos:
                metadata_path = PDF_ROOT / bill_no / "metadata.json"
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                metadata_by_bill_no[bill_no] = metadata
                bill_id = str(metadata["bill_id"])
                connection.execute(
                    "insert into dataset_splits values (?, ?, 'development', ?, ?)",
                    (bill_id, bill_no, "assembly-22-holdout-v1", started_at),
                )
                for document_type in ("cost_estimate", "bill_text"):
                    source_path = PDF_ROOT / bill_no / f"{document_type}.pdf"
                    document_meta = metadata["documents"][document_type]
                    pages = extract_pages(source_path)
                    document_id = f"document:{bill_id}:{document_type}"
                    pages_by_document[document_id] = pages
                    connection.execute(
                        """insert into documents (
                          document_id,bill_id,bill_no,bill_name,age,proposer,propose_date,committee,
                          document_type,source_path,source_url,original_name,sha256,page_count,
                          dataset_split,extraction_status,extraction_version,run_id
                        ) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'development','parsed',?,?)""",
                        (
                            document_id, bill_id, bill_no, metadata["bill_name"], metadata["age"],
                            metadata.get("proposer"), metadata.get("propose_date"), metadata.get("committee"),
                            document_type, str(source_path.relative_to(ROOT)), None,
                            document_meta.get("original_name"), document_meta["sha256"], len(pages),
                            PARSER_VERSION, run_id,
                        ),
                    )
                    for page_no, content in enumerate(pages, start=1):
                        chunk_id = f"chunk:{bill_id}:{document_type}:{page_no}"
                        chunk_by_page[(document_id, page_no)] = chunk_id
                        connection.execute(
                            "insert into document_chunks values (?,?,?,?,?,?,?)",
                            (
                                chunk_id, document_id, page_no, page_no - 1, content,
                                hashlib.sha256(content.encode("utf-8")).hexdigest(), PARSER_VERSION,
                            ),
                        )
                        connection.execute(
                            "insert into document_chunks_fts(chunk_id,content) values (?,?)",
                            (chunk_id, content),
                        )
                        stage["record_count"] += 1

        with measured(stages, "load_formula_registry") as stage:
            for row in formulas:
                connection.execute(
                    "insert into formula_templates values (?,?,?,?,?,?,?,?,?,?)",
                    (
                        row.get("formula_key"), _json(row.get("cost_natures") or []), row.get("label") or "",
                        row.get("expression_text") or row.get("expression") or "",
                        _json(row.get("required_variables") or row.get("required") or []),
                        _json(row.get("optional_variables") or row.get("optional") or []),
                        row.get("recurrence") or "mixed", _json(row.get("applicability") or {}),
                        row.get("template_version") or SCHEMA_VERSION, "candidate",
                    ),
                )
                stage["record_count"] += 1

        evidence_rows: list[tuple[str, str, str, str, str]] = []
        with measured(stages, "load_cost_items") as stage:
            for profile in item_profiles:
                profile_key = str(profile["profile_key"])
                bill_no = str(profile["bill_no"])
                metadata = metadata_by_bill_no[bill_no]
                bill_id = str(metadata["bill_id"])
                document_id = f"document:{bill_id}:cost_estimate"
                item_name = str(profile.get("item_name") or "")
                component = str(profile.get("component") or "other_goods_service")
                mechanism = infer_mechanism(item_name, component)
                scopes = list(infer_priced_scopes(item_name, mechanism)) or [component]
                quality_flags = []
                if not profile.get("trigger_ref"):
                    quality_flags.append("trigger_ref_missing")
                quality_flags.extend(("implementing_agency_missing", "policy_domain_missing"))
                connection.execute(
                    """insert into cost_items values (
                      ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                    )""",
                    (
                        profile_key, profile.get("source_item_key"), document_id, bill_id, bill_no,
                        profile.get("bill_name") or metadata["bill_name"], item_name,
                        profile.get("trigger_ref"), "goods_services", component, mechanism,
                        _json(scopes), "[]", "[]", None,
                        profile.get("classification_confidence") or "low",
                        profile.get("classification_reason") or "imported from sidecar v1",
                        "general_cost_sidecar_v1", "candidate", _json(quality_flags),
                    ),
                )
                formula_key = str(profile.get("formula_family") or "REVIEW_REQUIRED")
                connection.execute(
                    "insert into item_formula_links values (?,?,?,?,?,?)",
                    (
                        profile_key, formula_key, profile.get("formula_readiness") or "unresolved",
                        _json(profile.get("missing_formula_variables") or []),
                        "sidecar v1 canonical-variable compatibility", "candidate",
                    ),
                )
                source_rows = variables_by_profile.get(profile_key, [])
                evidence_text = " ".join(str(row.get("source_text") or "") for row in source_rows)
                connection.execute(
                    "insert into cost_items_fts values (?,?,?,?,?,?)",
                    (profile_key, item_name, mechanism, component, metadata["bill_name"], evidence_text),
                )
                item_quote = next((str(row.get("source_text") or "") for row in source_rows if row.get("source_text")), item_name)
                evidence_rows.append(("item", profile_key, document_id, item_quote, item_quote))
                evidence_rows.append(("formula", f"{profile_key}:{formula_key}", document_id, item_quote, item_quote))
                vector = embeddings.get(str(profile.get("source_item_key") or ""))
                if vector:
                    connection.execute(
                        "insert into item_embeddings values (?,?,?,?,?)",
                        (
                            profile_key, "text-embedding-3-small", len(vector), _json(vector),
                            f"{item_name} {component} {mechanism}",
                        ),
                    )
                stage["record_count"] += 1

        with measured(stages, "load_variables_and_amounts") as stage:
            for row in variables:
                profile_key = str(row["profile_key"])
                variable_id = str(row.get("evidence_key") or stable_key("variable", profile_key, row.get("raw_variable_fingerprint")))
                connection.execute(
                    """insert into variables values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        variable_id, profile_key, row.get("canonical_key"), row.get("raw_variable_name") or "",
                        row.get("raw_variable_type"), row.get("raw_value"), row.get("raw_unit"),
                        row.get("normalized_value"), row.get("normalized_unit"), row.get("basis_year"),
                        row.get("source_class") or "unclassified_source",
                        row.get("transfer_policy") or "review_required",
                        row.get("mapping_confidence") or "low",
                        row.get("normalization_status") or "unmapped", row.get("unit_status") or "not_normalized",
                        "candidate", _json(row.get("quality_flags") or []),
                    ),
                )
                item = next(profile for profile in item_profiles if str(profile["profile_key"]) == profile_key)
                bill_id = str(metadata_by_bill_no[str(item["bill_no"])]["bill_id"])
                evidence_rows.append((
                    "variable", variable_id, f"document:{bill_id}:cost_estimate",
                    str(row.get("source_text") or row.get("raw_variable_name") or ""),
                    str(row.get("source_text") or row.get("raw_variable_name") or ""),
                ))
                stage["record_count"] += 1
            for row in amounts:
                profile_key = str(row["profile_key"])
                observation_id = str(row.get("observation_key") or stable_key("amount", profile_key, row.get("year_label"), row.get("amount_thousand")))
                connection.execute(
                    "insert into amount_observations values (?,?,?,?,?,?,?,?)",
                    (
                        observation_id, profile_key, row.get("year_label"), row.get("year_offset"),
                        row.get("amount_thousand"), row.get("formula_text"), int(bool(row.get("is_total"))), "candidate",
                    ),
                )
                item = next(profile for profile in item_profiles if str(profile["profile_key"]) == profile_key)
                bill_id = str(metadata_by_bill_no[str(item["bill_no"])]["bill_id"])
                locator_query = amount_locator_query(row, str(item.get("item_name") or ""))
                evidence_rows.append((
                    "amount", observation_id, f"document:{bill_id}:cost_estimate",
                    locator_query, "",
                ))
                stage["record_count"] += 1

        with measured(stages, "link_page_evidence") as stage:
            for entity_type, entity_id, document_id, locator_query, source_quote in evidence_rows:
                page_no, method, score = locate_quote(pages_by_document[document_id], locator_query)
                chunk_id = chunk_by_page.get((document_id, page_no)) if page_no is not None else None
                if page_no is not None and not source_quote:
                    source_quote = source_excerpt(
                        pages_by_document[document_id][page_no - 1], locator_query
                    )
                connection.execute(
                    "insert or ignore into evidence_links values (?,?,?,?,?,?,?,?,?,?)",
                    (
                        stable_key("link", entity_type, entity_id, locator_query), entity_type, entity_id,
                        chunk_id, page_no, locator_query, source_quote, method, score, "candidate",
                    ),
                )
                stage["record_count"] += 1
                if method == "unresolved":
                    stage["failure_count"] += 1

        with measured(stages, "validate_database") as stage:
            foreign_key_errors = connection.execute("pragma foreign_key_check").fetchall()
            integrity = connection.execute("pragma integrity_check").fetchone()[0]
            holdout_overlap = connection.execute(
                "select count(*) from dataset_splits where split = 'validation_holdout'"
            ).fetchone()[0]
            if foreign_key_errors or integrity != "ok" or holdout_overlap:
                raise RuntimeError(
                    f"db validation failed: fk={len(foreign_key_errors)} integrity={integrity} holdout={holdout_overlap}"
                )
            stage["record_count"] = 3
            stage["details"] = {"integrity": integrity, "foreign_key_errors": len(foreign_key_errors), "holdout_overlap": holdout_overlap}

        table_counts = {}
        for table in (
            "documents", "document_chunks", "cost_items", "item_formula_links", "variables",
            "amount_observations", "evidence_links", "chunk_embeddings", "item_embeddings",
        ):
            table_counts[table] = connection.execute(f"select count(*) from {table}").fetchone()[0]
        locator_counts = {
            row[0]: row[1]
            for row in connection.execute("select locator_method,count(*) from evidence_links group by locator_method")
        }
        metrics = {
            "schema_version": SCHEMA_VERSION,
            "pipeline_version": PIPELINE_VERSION,
            "pilot_bill_nos": list(bill_nos),
            "cost_nature": "goods_services",
            "table_counts": table_counts,
            "evidence_locator": locator_counts,
            "embedding_coverage": round(table_counts["item_embeddings"] / max(table_counts["cost_items"], 1), 6),
            "stages": {
                name: {
                    "duration_ms": value["duration_ms"],
                    "record_count": value["record_count"],
                    "failure_count": value["failure_count"],
                    "details": value["details"],
                }
                for name, value in stages.items()
            },
        }
        for stage_name, value in stages.items():
            connection.execute(
                "insert into ingestion_stages values (?,?,?,?,?,?)",
                (
                    run_id, stage_name, value["duration_ms"], value["record_count"],
                    value["failure_count"], _json(value["details"]),
                ),
            )
        connection.execute(
            "update ingestion_runs set finished_at=?,status='completed',metrics_json=? where run_id=?",
            (utc_now(), _json(metrics), run_id),
        )
        connection.commit()
        connection.close()
        temporary.replace(output_path)
        return metrics
    except Exception:
        if 'connection' in locals():
            connection.close()
        if temporary.exists():
            temporary.unlink()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Build isolated v2 goods-services pilot DB")
    parser.add_argument("--output", type=Path, default=DEFAULT_DB)
    parser.add_argument("--export-dir", type=Path, default=DEFAULT_EXPORT_DIR)
    parser.add_argument("--bill-no", action="append", default=[])
    args = parser.parse_args()
    bill_nos = tuple(args.bill_no) if args.bill_no else PILOT_BILL_NOS
    metrics = build_database(args.output, bill_nos)
    migration = export_migration_bundle(args.output, args.export_dir)
    metrics["migration_bundle"] = {
        "path": str(args.export_dir),
        "row_counts": migration["row_counts"],
    }
    report_path = args.output.with_name("build_report.json")
    report_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
