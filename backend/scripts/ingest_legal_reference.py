"""ingest_legal_reference.py

비용추계 관련 법령 PDF를 한 번만 읽어 assembly_chunks에 올린다.

source = "legal_reference" 로 구분되어 RAG 검색 시 법령 근거로 활용된다.

사용법:
    python -m backend.scripts.ingest_legal_reference \
        --pdf "/path/to/법안비용추계_이해와_실제 1.pdf"
"""
from __future__ import annotations

import argparse
import getpass
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import SCRIPT_DIR, get_env

DOC_ID       = "LEGAL_REF_COST_ESTIMATION"
BILL_ID      = "LEGAL_REF_COST_ESTIMATION"
EMBED_MODEL  = get_env("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
AZURE_VER    = "2024-02-01"

# 조문 경계 패턴
_ARTICLE_RE  = re.compile(r"제\s*\d+\s*조(?:의\d+)?(?:\s*\([^)]+\))?")
_TABLE_LINE  = re.compile(r"(\|.+\||^\s{2,}\S.+\s{2,}\S)", re.MULTILINE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="법령 PDF를 RAG용으로 Supabase에 적재한다.")
    parser.add_argument(
        "--pdf",
        type=Path,
        default=Path("/Users/anseung-won/Desktop/프로젝트/비용추계자동화시스템/법안비용추계_이해와_실제 1.pdf"),
    )
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true", help="Supabase 저장 없이 청킹/임베딩만 확인")
    return parser.parse_args()


# ── PDF 텍스트 추출 ────────────────────────────────────────────────────────────

def extract_pdf_text(pdf_path: Path) -> str:
    swift = SCRIPT_DIR / "extract_pdf_text.swift"
    result = subprocess.run(
        ["swift", str(swift), str(pdf_path)],
        check=False, capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"PDF 추출 실패: {result.stderr[:300]}")
    return result.stdout.strip()


# ── 청킹 ──────────────────────────────────────────────────────────────────────

def is_table_block(text: str) -> bool:
    lines = text.splitlines()
    if not lines:
        return False
    return sum(1 for ln in lines if _TABLE_LINE.search(ln)) / len(lines) >= 0.3


def split_chunks(text: str, max_chars: int = 2400, overlap: int = 600) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        return []

    article_splits  = _ARTICLE_RE.split(text)
    article_headers = _ARTICLE_RE.findall(text)

    segments: list[str] = []
    if article_splits[0].strip():
        segments.append(article_splits[0].strip())
    for header, body in zip(article_headers, article_splits[1:]):
        segments.append(f"{header} {body}".strip())
    if not segments:
        segments = [text]

    chunks: list[str] = []
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        if is_table_block(seg) or len(seg) <= max_chars * 2:
            chunks.append(seg)
            continue
        start = 0
        while start < len(seg):
            end = min(start + max_chars, len(seg))
            chunk = seg[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end == len(seg):
                break
            start = max(0, end - overlap)
    return chunks


# ── Azure 임베딩 ───────────────────────────────────────────────────────────────

def get_azure_config() -> tuple[str, str]:
    key = get_env("AZURE_OPENAI_API_KEY")
    if not key:
        key = getpass.getpass("AZURE_OPENAI_API_KEY: ").strip()
    endpoint = get_env("AZURE_OPENAI_ENDPOINT").rstrip("/")
    if not endpoint:
        endpoint = input("AZURE_OPENAI_ENDPOINT: ").strip()
    return key, endpoint


def embed_batch(texts: list[str], api_key: str, endpoint: str) -> list[list[float]]:
    url = f"{endpoint}/openai/deployments/{EMBED_MODEL}/embeddings?api-version={AZURE_VER}"
    body = json.dumps({"input": texts}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"api-key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Azure OpenAI {exc.code}: {exc.read().decode()}") from exc
    return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]


# ── Supabase ──────────────────────────────────────────────────────────────────

def get_supabase_config() -> tuple[str, str]:
    url = get_env("SUPABASE_URL").rstrip("/")
    if not url:
        ref = input("SUPABASE project ref: ").strip()
        url = f"https://{ref}.supabase.co"
    key = get_env("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        key = getpass.getpass("SUPABASE_SERVICE_ROLE_KEY: ").strip()
    return url, key


def upsert_chunks(base_url: str, key: str, rows: list[dict[str, Any]]) -> None:
    url = f"{base_url}/rest/v1/assembly_chunks?on_conflict=chunk_id"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    body = json.dumps(rows, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Supabase {exc.code}: {exc.read().decode()}") from exc


def ensure_bill_row(base_url: str, key: str) -> None:
    """assembly_bills FK 충족용 더미 행 보장."""
    url = f"{base_url}/rest/v1/assembly_bills?on_conflict=bill_id"
    row = [{
        "bill_id":   BILL_ID,
        "source":    "legal_reference",
        "bill_name": "법안비용추계 이해와 실제 (관계법령)",
    }]
    headers = {
        "apikey": key, "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    body = json.dumps(row, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"assembly_bills 행 삽입 실패: {exc.read().decode()}") from exc


# ── 메인 ──────────────────────────────────────────────────────────────────────

def batched(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def main() -> None:
    args = parse_args()

    if not args.pdf.exists():
        raise SystemExit(f"PDF 파일 없음: {args.pdf}")

    print(f"PDF 텍스트 추출 중: {args.pdf.name}")
    text = extract_pdf_text(args.pdf)
    if not text:
        raise SystemExit("텍스트 추출 결과가 비어있습니다.")
    print(f"  추출 완료: {len(text):,} 자")

    chunks = split_chunks(text)
    print(f"  청킹 완료: {len(chunks)}개 chunk")

    azure_key, azure_endpoint = get_azure_config()

    if not args.dry_run:
        supa_url, supa_key = get_supabase_config()
        ensure_bill_row(supa_url, supa_key)

    rows: list[dict[str, Any]] = []
    total_batches = (len(chunks) + args.batch_size - 1) // args.batch_size

    for batch_idx, batch in enumerate(batched(chunks, args.batch_size), start=1):
        texts = [c for c in batch if c.strip()]
        if not texts:
            continue
        vectors = embed_batch(texts, azure_key, azure_endpoint)
        for chunk_idx_in_batch, (chunk_text, vector) in enumerate(zip(texts, vectors)):
            global_idx = (batch_idx - 1) * args.batch_size + chunk_idx_in_batch + 1
            rows.append({
                "chunk_id":      f"{DOC_ID}:{global_idx}",
                "bill_id":       BILL_ID,
                "source":        "legal_reference",
                "document_name": args.pdf.name,
                "document_type": "legal_reference",
                "chunk_index":   global_idx,
                "content":       chunk_text,
                "embedding":     vector,
            })
        print(f"  임베딩 배치 {batch_idx}/{total_batches} 완료 ({len(texts)}건)")

    print(f"\n임베딩 완료: {len(rows)}건")

    if args.dry_run:
        print("[DRY-RUN] Supabase 저장 건너뜀")
        return

    uploaded = 0
    for batch in batched(rows, args.batch_size):
        upsert_chunks(supa_url, supa_key, list(batch))
        uploaded += len(batch)
        print(f"  Supabase 업로드 {uploaded}/{len(rows)}건")

    print(f"\n완료: {len(rows)}개 chunk → assembly_chunks (source=legal_reference)")


if __name__ == "__main__":
    main()
