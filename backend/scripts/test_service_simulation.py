"""test_service_simulation.py

새 조례안 PDF 입력 → RAG + TAG + Gemini → 비용추계 분석/추계서 자동 생성.

서비스 레이어 시뮬레이션 (백엔드 API 만들기 전 검증용).

흐름:
  1. PDF 텍스트 추출 (PyMuPDF)
  2. 조문 단위 분할
  3. 조문별 비용유발 분석 (Gemini + RAG)
  4. 종합 판단: 추계 vs 미첨부
  5. 추계서 또는 미첨부사유서 생성 (Gemini + RAG + TAG)

사용법:
    python -m backend.scripts.test_service_simulation \
        --pdf "/path/to/조례안.pdf"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import get_env

import fitz  # PyMuPDF

GEMINI_API_KEY  = get_env("GEMINI_API_KEY")
GEMINI_MODEL    = get_env("GEMINI_MODEL", "gemini-2.5-pro")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
EMBED_MODEL     = get_env("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
AZURE_API_VER   = "2024-02-01"
SUPA_URL        = get_env("SUPABASE_URL").rstrip("/")
SUPA_KEY        = get_env("SUPABASE_SERVICE_ROLE_KEY")
AZURE_KEY       = get_env("AZURE_OPENAI_API_KEY")
AZURE_ENDPOINT  = get_env("AZURE_OPENAI_ENDPOINT").rstrip("/")

_ARTICLE_RE = re.compile(r"제\s*\d+\s*조(?:의\d+)?(?:\s*\([^)]+\))?")


# ── 유틸 ──────────────────────────────────────────────────────────────────────

def http_post_json(url: str, headers: dict, payload: Any) -> Any:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def http_get_json(url: str, headers: dict) -> Any:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


# ── PDF 추출 ──────────────────────────────────────────────────────────────────

def extract_pdf(pdf_path: Path) -> str:
    with fitz.open(str(pdf_path)) as doc:
        return "\n".join(p.get_text() for p in doc).strip()


def split_articles(text: str) -> list[dict[str, str]]:
    """조문 단위로 분할. [{'no': '제3조', 'text': '...'}]"""
    splits = _ARTICLE_RE.split(text)
    headers = _ARTICLE_RE.findall(text)
    out = []
    for h, body in zip(headers, splits[1:]):
        body = re.sub(r"\s+", " ", body).strip()
        if len(body) < 10:
            continue
        out.append({"no": h.strip(), "text": body[:1500]})
    return out


# ── 임베딩 ────────────────────────────────────────────────────────────────────

def embed(text: str) -> list[float]:
    url = (f"{AZURE_ENDPOINT}/openai/deployments/{EMBED_MODEL}"
           f"/embeddings?api-version={AZURE_API_VER}")
    data = http_post_json(url, {
        "api-key": AZURE_KEY, "Content-Type": "application/json",
    }, {"input": [text]})
    return data["data"][0]["embedding"]


# ── Supabase 벡터 검색 ────────────────────────────────────────────────────────

def supa_match_chunks(embedding: list[float], source: str = None,
                      doc_type: str = None, k: int = 5) -> list[dict]:
    """assembly_chunks 벡터 검색. PostgREST의 RPC 또는 inline pgvector 쿼리."""
    # PostgREST는 vector 연산자 직접 지원 안 함. SQL을 RPC로 노출하거나
    # /rest/v1/assembly_chunks?select=...&order=embedding.<-> 등 사용
    # 여기선 간단한 시도: pgvector 연산 직접
    filt = ""
    if source:
        filt += f"&source=eq.{source}"
    if doc_type:
        filt += f"&document_type=eq.{doc_type}"
    # 벡터 문자열화
    vec_str = "[" + ",".join(f"{x:.6f}" for x in embedding) + "]"
    # PostgREST 쿼리에 vector를 직접 줘서 코사인 거리 정렬
    url = (f"{SUPA_URL}/rest/v1/assembly_chunks"
           f"?select=chunk_id,bill_id,bill_no,bill_name,document_type,content"
           f"{filt}"
           f"&limit={k}")
    headers = {
        "apikey": SUPA_KEY, "Authorization": f"Bearer {SUPA_KEY}",
    }
    # NOTE: 실제 ANN 정렬은 SQL RPC가 필요. 임시로 단순 검색.
    return http_get_json(url, headers)


def supa_vector_search(embedding: list[float], k: int = 5,
                       source: str | None = None) -> list[dict]:
    """SQL RPC를 통한 코사인 유사도 검색.

    Supabase에는 vector 검색용 RPC를 별도로 만들어야 하지만,
    여기선 PostgREST의 raw vector 쿼리 패턴을 시도.
    """
    # PostgREST에서 벡터 정렬을 위해 함수 호출. 없으면 fallback.
    # 일단 keyword fallback 사용 (content_trgm).
    return []


# ── Gemini ────────────────────────────────────────────────────────────────────

def gemini_json(prompt: str) -> dict | None:
    url = f"{GEMINI_BASE_URL}/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    try:
        data = http_post_json(url, {"Content-Type": "application/json"}, {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1,
            },
        })
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        if isinstance(parsed, list):
            parsed = next((x for x in parsed if isinstance(x, dict)), None)
        return parsed if isinstance(parsed, dict) else None
    except Exception as exc:
        print(f"    [Gemini 오류] {exc}", file=sys.stderr)
        return None


# ── 분석 단계 ─────────────────────────────────────────────────────────────────

ARTICLE_PROMPT = """당신은 지방조례안의 비용유발 여부를 판단하는 전문가입니다.

[조문]
{article_text}

[참고 - 비용추계 기준 (법령 PDF에서)]
{legal_ref}

다음 JSON으로 답하세요:
{{
  "cost_trigger": true 또는 false,
  "trigger_type": "직접지원|위탁대행|시설구축|조직설치|대상확대|의무부과|없음",
  "obligation_strength": "mandatory|semi_mandatory|discretionary|aspirational",
  "reason": "왜 이렇게 판단했는지 한 줄"
}}
"""

FINAL_PROMPT = """당신은 지방의회 비용추계 전문가입니다.

[새 조례안 조문별 분석 결과]
{articles_analysis}

[유사 사례 비용추계서 RAG]
{similar_estimates}

[법령 PDF 기준 RAG]
{legal_ref}

다음을 JSON으로 답하세요:
{{
  "verdict": "추계필요|미첨부_A|미첨부_B|미첨부_C",
  "reason_summary": "종합 판단 요약 2~3문장",
  "if_needs_estimate": {{
    "items": [
      {{"name": "항목명", "formula": "산식", "trigger_ref": "근거 조문"}}
    ],
    "variables_needed": ["대상자 수", "단가", ...],
    "year_amounts_estimate": [
      {{"year": 1, "amount_thousand": 숫자_또는_null, "note": "..."}}
    ]
  }} 또는 null,
  "if_non_attachment": {{
    "type": "A|B|C",
    "reason_text": "미첨부 사유 텍스트"
  }} 또는 null,
  "confidence": 0.0~1.0
}}
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    print(f"📄 PDF 읽기: {args.pdf.name}")
    text = extract_pdf(args.pdf)
    print(f"   {len(text):,}자 추출")
    articles = split_articles(text)
    print(f"   조문 {len(articles)}개 분할\n")

    if not articles:
        print("[ERROR] 조문이 추출되지 않았습니다.")
        return

    # 1) 법령 PDF 참고 검색
    print("🔍 법령 PDF (legal_reference) 검색 (기준 가져옴)...")
    legal_query = "비용추계 미첨부 가능 기준 정의 규정 선언적 권고적"
    leg_emb = embed(legal_query)
    legal_chunks = supa_match_chunks(leg_emb, source="legal_reference", k=3)
    legal_ref = "\n---\n".join(c.get("content", "")[:800] for c in legal_chunks)
    print(f"   법령 청크 {len(legal_chunks)}건 확보\n")

    # 2) 조문별 분석
    print("📋 조문별 비용유발 분석...")
    article_results = []
    for i, art in enumerate(articles[:10], 1):  # 처음 10조문만
        prompt = ARTICLE_PROMPT.format(
            article_text=art["text"][:1500],
            legal_ref=legal_ref[:2000],
        )
        result = gemini_json(prompt) or {}
        article_results.append({**art, **result})
        flag = "🔴" if result.get("cost_trigger") else "⚪"
        print(f"   {flag} {art['no']:20s} {result.get('trigger_type','?'):10s} "
              f"{result.get('obligation_strength','?'):15s} {result.get('reason','')[:50]}")

    # 3) 유사 추계서 검색
    print("\n🔍 유사 추계서 RAG 검색...")
    full_query = "\n".join(a["text"] for a in articles[:5])
    bill_emb = embed(full_query[:8000])
    similar = supa_match_chunks(bill_emb, source="national_assembly",
                                doc_type="cost_estimate", k=args.top_k)
    print(f"   유사 사례 {len(similar)}건")
    for s in similar[:3]:
        print(f"     - {s.get('bill_no')} | {s.get('bill_name','')[:40]}")

    # 4) 종합 판단 + 추계서 생성
    print("\n⚖️ 종합 판단 + 추계서 작성...")
    articles_summary = "\n".join(
        f"{a['no']}: cost_trigger={a.get('cost_trigger')} type={a.get('trigger_type')} "
        f"reason={a.get('reason','')[:80]}"
        for a in article_results
    )
    similar_text = "\n---\n".join(
        f"[{s.get('bill_no')} {s.get('bill_name','')[:30]}]\n{s.get('content','')[:600]}"
        for s in similar[:3]
    )
    final = gemini_json(FINAL_PROMPT.format(
        articles_analysis=articles_summary,
        similar_estimates=similar_text,
        legal_ref=legal_ref[:2000],
    ))

    print("\n" + "=" * 60)
    print("🎯 최종 결과")
    print("=" * 60)
    print(json.dumps(final, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
