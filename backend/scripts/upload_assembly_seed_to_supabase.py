from __future__ import annotations

import argparse
import getpass
import json
import mimetypes
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import GENERATED_DIR, get_env


DEFAULT_SEED_DIR = GENERATED_DIR / "assembly_rag_seed"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload assembly RAG seed data to Supabase.")
    parser.add_argument("--seed-dir", type=Path, default=DEFAULT_SEED_DIR)
    parser.add_argument("--bucket", default=get_env("SUPABASE_STORAGE_BUCKET", "assembly-documents"))
    parser.add_argument("--skip-files", action="store_true", help="Skip Storage uploads.")
    parser.add_argument("--batch-size", type=int, default=100)
    return parser.parse_args()


def get_supabase_config() -> tuple[str, str]:
    url = get_env("SUPABASE_URL").rstrip("/")
    if not url:
        project_ref = input("SUPABASE project ref: ").strip()
        if not project_ref:
            raise SystemExit("SUPABASE_URL or project ref is required.")
        url = f"https://{project_ref}.supabase.co"

    key = get_env("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        key = getpass.getpass("SUPABASE_SERVICE_ROLE_KEY: ").strip()
    if not key:
        raise SystemExit("SUPABASE_SERVICE_ROLE_KEY is required.")

    return url, key


def request_json(
    url: str,
    key: str,
    *,
    method: str = "GET",
    payload: Any = None,
    headers: dict[str, str] | None = None,
    expected: tuple[int, ...] = (200, 201, 204),
) -> Any:
    body = None
    request_headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if headers:
        request_headers.update(headers)
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
            if response.status not in expected:
                raise RuntimeError(f"Unexpected status {response.status}: {raw}")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        if exc.code not in expected:
            raise RuntimeError(f"Supabase HTTP {exc.code}: {error_body}") from exc
        return None


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def upsert_rows(
    base_url: str,
    key: str,
    table: str,
    rows: list[dict[str, Any]],
    *,
    on_conflict: str,
    batch_size: int,
) -> None:
    if not rows:
        return
    endpoint = (
        f"{base_url}/rest/v1/{table}"
        f"?on_conflict={urllib.parse.quote(on_conflict)}"
    )
    headers = {
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    for batch in chunks(rows, batch_size):
        request_json(endpoint, key, method="POST", payload=batch, headers=headers)


def upload_file(base_url: str, key: str, bucket: str, local_path: Path, object_path: str) -> None:
    content_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
    url = f"{base_url}/storage/v1/object/{bucket}/{urllib.parse.quote(object_path)}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": content_type,
        "x-upsert": "true",
    }
    request = urllib.request.Request(
        url,
        data=local_path.read_bytes(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Storage upload failed for {local_path}: {exc.code} {error_body}") from exc


def normalize_bill(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "bill_id": row["billId"],
        "source": row.get("source", "national_assembly"),
        "age": int(row["age"]) if row.get("age") else None,
        "bill_no": row.get("billNo"),
        "bill_name": row.get("billName"),
        "proposer": row.get("proposer"),
        "propose_date": row.get("proposeDate") or None,
        "committee": row.get("committee"),
        "process_result": row.get("processResult"),
        "detail_link": row.get("detailLink"),
        "memo": row.get("memo"),
        "all_document_count": row.get("allDocumentCount", 0),
        "selected_document_count": row.get("selectedDocumentCount", 0),
        "has_cost_estimate":  bool(row.get("hasCostEstimate", False)),
        "has_non_attachment": bool(row.get("hasNonAttachment", False)),
    }


def normalize_document(row: dict[str, Any], bucket: str) -> dict[str, Any]:
    local_path = row.get("localPath")
    storage_path = build_storage_path(row) if local_path else None
    return {
        "bill_id": row["billId"],
        "bill_no": row.get("billNo"),
        "bill_name": row.get("billName"),
        "source": row.get("source", "national_assembly"),
        "document_name": row.get("documentName"),
        "document_type": row.get("documentType"),
        "file_type": row.get("fileType"),
        "source_url": row.get("url"),
        "local_path": local_path,
        "storage_bucket": bucket if storage_path else None,
        "storage_path": storage_path,
        "text_extract_status": row.get("textExtractStatus", "pending"),
        "ocr_required": row.get("ocrRequired", False),
        "pdf_available": row.get("pdfAvailable", False),
        "hwp_available": row.get("hwpAvailable", False),
        "fallback_required": row.get("fallbackRequired", False),
    }


def build_storage_path(row: dict[str, Any]) -> str:
    age = row.get("age") or "unknown"
    bill_no = row.get("billNo") or row.get("billId") or "unknown"
    document_type = row.get("documentType") or "document"
    local_name = Path(row.get("localPath") or "document.bin").name
    return f"national_assembly/{age}/{bill_no}/{document_type}/{local_name}"


def normalize_chunk(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": row["chunkId"],
        "bill_id": row["billId"],
        "bill_no": row.get("billNo"),
        "bill_name": row.get("billName"),
        "age": row.get("age"),
        "committee": row.get("committee"),
        "propose_date": row.get("proposeDate") or None,
        "source": row.get("source", "national_assembly"),
        "document_name": row.get("documentName"),
        "document_type": row.get("documentType"),
        "chunk_index": row.get("chunkIndex"),
        "content": row.get("text"),
        "embedding": None,  # 별도 임베딩 스크립트에서 채움
    }


def normalize_stat_candidate(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "variable_key": row["variableKey"],
        "candidate_source": row.get("candidateSource"),
        "matched_keywords": row.get("matchedKeywords", []),
        "used_in_documents": row.get("usedInDocuments", 0),
        "example_bills": row.get("exampleBills", []),
        "kosis_mapping_status": row.get("kosisMappingStatus", "needs_mapping"),
    }


def main() -> None:
    args = parse_args()
    base_url, key = get_supabase_config()
    seed_dir = args.seed_dir

    bills = [normalize_bill(row) for row in load_jsonl(seed_dir / "bills.jsonl")]
    raw_documents = load_jsonl(seed_dir / "documents.jsonl")
    documents = [normalize_document(row, args.bucket) for row in raw_documents]
    chunks_path = seed_dir / "chunks.jsonl"
    if not chunks_path.exists():
        chunks_path = seed_dir / "chunks_with_local_vectors.jsonl"
    raw_chunks = load_jsonl(chunks_path)
    # bill_text는 RAG 청크 저장 안 함 (의안원문은 bill_cost_triggers로만 처리)
    raw_chunks = [c for c in raw_chunks if c.get("documentType") != "bill_text"]
    chunk_rows = [normalize_chunk(row) for row in raw_chunks]

    stat_path = seed_dir / "kosis_needed_statistics_candidates.json"
    stat_rows = []
    if stat_path.exists():
        stat_rows = [normalize_stat_candidate(row) for row in json.loads(stat_path.read_text(encoding="utf-8"))]

    if not args.skip_files:
        for row in raw_documents:
            local_path = Path(row.get("localPath") or "")
            if not local_path.exists():
                continue
            upload_file(base_url, key, args.bucket, local_path, build_storage_path(row))

    upsert_rows(base_url, key, "assembly_bills", bills, on_conflict="bill_id", batch_size=args.batch_size)
    upsert_rows(
        base_url,
        key,
        "assembly_documents",
        documents,
        on_conflict="bill_id,document_type,document_name,file_type,source_url",
        batch_size=args.batch_size,
    )
    upsert_rows(base_url, key, "assembly_chunks", chunk_rows, on_conflict="chunk_id", batch_size=args.batch_size)
    upsert_rows(
        base_url,
        key,
        "kosis_stat_candidates",
        stat_rows,
        on_conflict="variable_key",
        batch_size=args.batch_size,
    )

    print(
        json.dumps(
            {
                "uploadedBills": len(bills),
                "uploadedDocuments": len(documents),
                "uploadedChunks": len(chunk_rows),
                "uploadedStatCandidates": len(stat_rows),
                "bucket": args.bucket,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
