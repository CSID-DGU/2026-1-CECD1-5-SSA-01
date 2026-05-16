"""embed_chunks.py

chunks.jsonl 에서 텍스트를 읽어 OpenAI text-embedding-3-small 으로 임베딩을 생성하고
Supabase assembly_chunks 테이블의 embedding 컬럼을 업데이트한다.

사용법:
    python -m backend.scripts.embed_chunks \\
        --seed-dir backend/generated/assembly_rag_seed_age21_50 \\
        [--batch-size 100] \\
        [--dry-run]
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import GENERATED_DIR, get_env

DEFAULT_SEED_DIR = GENERATED_DIR / "assembly_rag_seed"
EMBEDDING_MODEL = get_env("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM = 1536
AZURE_API_VERSION = "2024-02-01"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and upload chunk embeddings.")
    parser.add_argument("--seed-dir", type=Path, default=DEFAULT_SEED_DIR)
    parser.add_argument("--batch-size", type=int, default=100, help="Azure OpenAI API 배치 크기")
    parser.add_argument("--supabase-batch", type=int, default=50, help="Supabase upsert 배치 크기")
    parser.add_argument("--sleep", type=float, default=0.5, help="API 호출 간격(초)")
    parser.add_argument("--dry-run", action="store_true", help="임베딩만 생성, Supabase 저장 건너뜀")
    return parser.parse_args()


# ── Azure OpenAI API ─────────────────────────────────────────────────────────

def get_azure_config() -> tuple[str, str]:
    key = get_env("AZURE_OPENAI_API_KEY")
    if not key:
        key = getpass.getpass("AZURE_OPENAI_API_KEY: ").strip()
    if not key:
        raise SystemExit("AZURE_OPENAI_API_KEY 가 필요합니다.")

    endpoint = get_env("AZURE_OPENAI_ENDPOINT").rstrip("/")
    if not endpoint:
        endpoint = input("AZURE_OPENAI_ENDPOINT (예: https://xxx.openai.azure.com): ").strip()
    if not endpoint:
        raise SystemExit("AZURE_OPENAI_ENDPOINT 가 필요합니다.")

    return key, endpoint


def embed_batch(texts: list[str], api_key: str, endpoint: str) -> list[list[float]]:
    """Azure OpenAI Embeddings API 호출.
    URL: {endpoint}/openai/deployments/{deployment}/embeddings?api-version={version}
    """
    url = (
        f"{endpoint}/openai/deployments/{EMBEDDING_MODEL}"
        f"/embeddings?api-version={AZURE_API_VERSION}"
    )
    payload = {"input": texts}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Azure OpenAI HTTP {exc.code}: {error_body}") from exc

    items = sorted(data["data"], key=lambda x: x["index"])
    return [item["embedding"] for item in items]


# ── Supabase ─────────────────────────────────────────────────────────────────

def get_supabase_config() -> tuple[str, str]:
    url = get_env("SUPABASE_URL").rstrip("/")
    if not url:
        ref = input("SUPABASE project ref: ").strip()
        url = f"https://{ref}.supabase.co"
    key = get_env("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        key = getpass.getpass("SUPABASE_SERVICE_ROLE_KEY: ").strip()
    if not key:
        raise SystemExit("SUPABASE_SERVICE_ROLE_KEY 가 필요합니다.")
    return url, key


def upsert_embeddings(
    base_url: str,
    supa_key: str,
    rows: list[dict[str, Any]],
) -> None:
    """chunk_id + embedding 을 assembly_chunks 에 upsert."""
    url = f"{base_url}/rest/v1/assembly_chunks?on_conflict=chunk_id"
    body = json.dumps(rows, ensure_ascii=False).encode("utf-8")
    headers = {
        "apikey": supa_key,
        "Authorization": f"Bearer {supa_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Supabase HTTP {exc.code}: {error_body}") from exc


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        print(f"[WARN] 파일 없음: {path}", file=sys.stderr)
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def batched(items: list[Any], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    azure_key, azure_endpoint = get_azure_config()

    if not args.dry_run:
        supa_url, supa_key = get_supabase_config()

    chunks_path = args.seed_dir / "chunks.jsonl"
    if not chunks_path.exists():
        chunks_path = args.seed_dir / "chunks_with_local_vectors.jsonl"
    all_chunks = load_jsonl(chunks_path)
    if not all_chunks:
        print(f"[INFO] RAG 대상 chunks 0건 (cost_estimate/non_attachment 없는 의안). 임베딩 스킵.")
        return

    print(f"총 chunk 수: {len(all_chunks)} | 모델: {EMBEDDING_MODEL}")

    embedded: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for batch_idx, batch in enumerate(batched(all_chunks, args.batch_size), start=1):
        texts = [row.get("text", "") for row in batch]
        chunk_ids = [row.get("chunkId", "") for row in batch]

        valid = [
            (row.get("chunkId", ""), row.get("text", ""), row)
            for row in batch
            if row.get("text", "").strip() and row.get("chunkId") and row.get("billId")
        ]
        if not valid:
            print(f"  배치 {batch_idx}: 텍스트 없음, 건너뜀")
            continue

        valid_ids, valid_texts, valid_rows = zip(*valid)

        try:
            vectors = embed_batch(list(valid_texts), azure_key, azure_endpoint)
        except Exception as exc:
            print(f"  [ERROR] 배치 {batch_idx} 임베딩 실패: {exc}", file=sys.stderr)
            errors.append({"batch": str(batch_idx), "error": repr(exc)})
            continue

        for chunk_id, vector, row in zip(valid_ids, vectors, valid_rows):
            embedded.append({
                "chunk_id":     chunk_id,
                "bill_id":      row["billId"],
                "bill_no":      row.get("billNo"),
                "bill_name":    row.get("billName"),
                "age":          row.get("age"),
                "committee":    row.get("committee"),
                "propose_date": row.get("proposeDate") or None,
                "source":       row.get("source", "national_assembly"),
                "document_name":row.get("documentName"),
                "document_type":row.get("documentType", ""),
                "chunk_index":  row.get("chunkIndex"),
                "content":      row["text"],
                "embedding":    vector,
            })

        token_count = sum(len(t.split()) for t in valid_texts)
        print(f"  배치 {batch_idx}: {len(valid_ids)}건 임베딩 완료 (~{token_count} tokens)")
        time.sleep(args.sleep)

    print(f"\n임베딩 생성 완료: {len(embedded)}건 / 오류: {len(errors)}건")

    if args.dry_run:
        out_path = args.seed_dir / "chunks_embedded.jsonl"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            for row in embedded:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"[DRY-RUN] 저장: {out_path}")
        return

    # Supabase upsert
    print(f"\nSupabase 업로드 시작 (배치 {args.supabase_batch}건)...")
    uploaded = 0
    for supa_batch in batched(embedded, args.supabase_batch):
        try:
            upsert_embeddings(supa_url, supa_key, list(supa_batch))
            uploaded += len(supa_batch)
            print(f"  업로드 {uploaded}/{len(embedded)}건")
        except Exception as exc:
            print(f"  [ERROR] Supabase 업로드 실패: {exc}", file=sys.stderr)
            errors.append({"phase": "supabase", "error": repr(exc)})

    summary = {
        "totalChunks": len(all_chunks),
        "embeddedCount": len(embedded),
        "uploadedCount": uploaded,
        "errorCount": len(errors),
        "model": EMBEDDING_MODEL,
        "errors": errors,
    }
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
