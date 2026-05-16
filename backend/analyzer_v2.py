"""analyzer_v2.py

새 조례안 PDF/텍스트 → RAG/TAG 기반 비용추계 분석 + 추계서 자동 생성.

이전 analyzer.py는 단순 규칙 기반. v2는:
  - PyMuPDF로 PDF 텍스트 추출
  - 조문 단위 분할
  - 조문별 비용유발 분석 (Gemini)
  - Supabase 벡터 검색 (match_assembly_chunks RPC)
  - TAG 산식 패턴 매칭
  - 종합 판단 + 추계서/사유서 생성

입출력은 server.py가 사용하기 좋은 dict 형태.
"""
from __future__ import annotations

import base64
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

import fitz  # PyMuPDF

from .config import get_env

GEMINI_API_KEY  = get_env("GEMINI_API_KEY")
GEMINI_MODEL    = get_env("GEMINI_MODEL", "gemini-2.5-pro")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
OPENAI_API_KEY  = get_env("OPENAI_API_KEY")
OPENAI_EMBED_MODEL = get_env("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
AZURE_EMBED_MODEL  = get_env("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
AZURE_API_VER   = "2024-02-01"
SUPA_URL        = get_env("SUPABASE_URL").rstrip("/")
SUPA_KEY        = get_env("SUPABASE_SERVICE_ROLE_KEY")
AZURE_KEY       = get_env("AZURE_OPENAI_API_KEY")
AZURE_ENDPOINT  = get_env("AZURE_OPENAI_ENDPOINT").rstrip("/")

_ARTICLE_RE = re.compile(r"제\s*\d+\s*조(?:의\d+)?(?:\s*\([^)]+\))?")


# ── HTTP 헬퍼 ─────────────────────────────────────────────────────────────────

def _post(url: str, headers: dict, payload: Any, timeout: int = 120) -> Any:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8")
        return json.loads(raw) if raw else None


# ── PDF + 조문 분할 ───────────────────────────────────────────────────────────

def extract_pdf_from_b64(content_b64: str) -> str:
    pdf_bytes = base64.b64decode(content_b64)
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return "\n".join(p.get_text() for p in doc).strip()


def split_articles_regex(text: str) -> list[dict[str, str]]:
    """정규식 기반 폴백."""
    splits = _ARTICLE_RE.split(text)
    headers = _ARTICLE_RE.findall(text)
    out: list[dict[str, str]] = []
    for h, body in zip(headers, splits[1:]):
        clean = re.sub(r"\s+", " ", body).strip()
        if len(clean) < 10:
            continue
        out.append({"no": h.strip(), "text": clean[:1500]})
    return out


_SPLIT_PROMPT = """아래는 한국 법령/조례 PDF에서 추출한 텍스트야.
본문 조문만 골라서 JSON 배열로 반환해줘.

[제외할 것]
- 입법예고 안내문 (의견제출, 제출기한 등 행정 안내)
- "부 칙" 또는 "부칙" 이후 내용
- "참고 관계법령" / "별표" / "별지" / "참고자료"
- 조례 본문의 "주요 내용 요약" 같이 정리된 부분

[포함할 것]
- 진짜 조문만 (제1조, 제2조 등 본문 조항)
- 조 번호, 조 제목, 조 본문 텍스트

[입력 텍스트]
{text}

[출력 JSON]
{{
  "articles": [
    {{"no": "제1조", "title": "목적", "text": "이 조례는 ..."}},
    {{"no": "제2조", "title": "정의", "text": "이 조례에서 ..."}}
  ]
}}
"""


def _gemini_raw_json(prompt: str) -> Any:
    """gemini_json 과 달리 list/dict 모두 그대로 반환."""
    url = f"{GEMINI_BASE_URL}/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    try:
        data = _post(url, {"Content-Type": "application/json"}, {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1,
            },
        }, timeout=120)
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[Gemini raw 오류] {exc}\n")
        return None


def split_articles(text: str) -> list[dict[str, str]]:
    """LLM 본문 추출 (1순위) + 정규식 폴백."""
    if len(text) < 200:
        return split_articles_regex(text)

    excerpt = text[:30000]
    try:
        parsed = _gemini_raw_json(_SPLIT_PROMPT.format(text=excerpt))
        # list 또는 {"articles": [...]} 둘 다 처리
        if isinstance(parsed, list):
            articles_raw = parsed
        elif isinstance(parsed, dict):
            articles_raw = parsed.get("articles") or []
            if not articles_raw and len(parsed) > 0:
                # 키 이름이 다를 수 있음 — 첫 list value 사용
                for v in parsed.values():
                    if isinstance(v, list):
                        articles_raw = v
                        break
        else:
            articles_raw = []

        out = []
        for a in articles_raw:
            if not isinstance(a, dict):
                continue
            no = (a.get("no") or a.get("number") or "").strip()
            title = (a.get("title") or "").strip()
            body = (a.get("text") or a.get("content") or "").strip()
            if not no or len(body) < 5:
                continue
            label = f"{no}({title})" if title else no
            out.append({"no": label, "text": body[:1500]})
        if out:
            return out
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[LLM 조문 분할 실패, 정규식 폴백] {exc}\n")

    return split_articles_regex(text)


# ── 임베딩 + 벡터 검색 ─────────────────────────────────────────────────────────

def embed_openai(text: str) -> list[float]:
    data = _post(
        "https://api.openai.com/v1/embeddings",
        {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        {
            "model": OPENAI_EMBED_MODEL,
            "input": text,
        },
    )
    return data["data"][0]["embedding"]


def embed_azure(text: str) -> list[float]:
    url = (f"{AZURE_ENDPOINT}/openai/deployments/{AZURE_EMBED_MODEL}"
           f"/embeddings?api-version={AZURE_API_VER}")
    data = _post(url, {
        "api-key": AZURE_KEY, "Content-Type": "application/json",
    }, {"input": [text]})
    return data["data"][0]["embedding"]


def embed(text: str) -> list[float]:
    if OPENAI_API_KEY:
        return embed_openai(text)
    if AZURE_KEY and AZURE_ENDPOINT:
        return embed_azure(text)
    raise RuntimeError("OPENAI_API_KEY 또는 Azure OpenAI 임베딩 설정이 필요합니다.")


def try_embed(text: str) -> list[float] | None:
    """임베딩은 RAG 보조 기능이다. 실패해도 Gemini 분석은 계속 진행한다."""
    try:
        return embed(text)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[embedding 비활성화] {exc}\n")
        return None


def embed_batch(texts: list[str]) -> list[list[float] | None]:
    """여러 텍스트를 한 번에 임베딩. OpenAI는 input list 받음 → 호출 1번."""
    if not texts:
        return []
    try:
        if OPENAI_API_KEY:
            data = _post(
                "https://api.openai.com/v1/embeddings",
                {
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                {"model": OPENAI_EMBED_MODEL, "input": texts},
            )
            ordered = sorted(data["data"], key=lambda x: x["index"])
            return [it["embedding"] for it in ordered]
        # Azure 폴백 — 1건씩 (Azure는 input list 지원 다름)
        return [try_embed(t) for t in texts]
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[embed_batch 실패, 1건씩 폴백] {exc}\n")
        return [try_embed(t) for t in texts]


def vector_search(emb: list[float], source: str | None = None,
                  doc_type: str | None = None, k: int = 5) -> list[dict]:
    """match_assembly_chunks RPC 호출 (Supabase에 등록된 함수)."""
    url = f"{SUPA_URL}/rest/v1/rpc/match_assembly_chunks"
    headers = {
        "apikey": SUPA_KEY, "Authorization": f"Bearer {SUPA_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "query_embedding": emb, "match_count": k,
        "filter_source": source, "filter_doc_type": doc_type,
    }
    try:
        return _post(url, headers, payload, timeout=30) or []
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"[vector_search 실패] {e}: {e.read().decode('utf-8','ignore')[:200]}\n")
        return []


# ── Gemini ────────────────────────────────────────────────────────────────────

def gemini_json(prompt: str, temperature: float = 0.1) -> dict | None:
    url = f"{GEMINI_BASE_URL}/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    try:
        data = _post(url, {"Content-Type": "application/json"}, {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": temperature,
            },
        }, timeout=180)
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        if isinstance(parsed, list):
            parsed = next((x for x in parsed if isinstance(x, dict)), None)
        return parsed if isinstance(parsed, dict) else None
    except Exception as exc:
        sys.stderr.write(f"[Gemini 오류] {exc}\n")
        return None


# ── 프롬프트 ──────────────────────────────────────────────────────────────────

ARTICLE_PROMPT = """당신은 지방조례안의 비용유발 여부를 판단하는 전문가입니다.

[조문]
{article_text}

[판단 기준 (법령 PDF 발췌)]
{legal_ref}

다음 JSON으로 답하세요:
{{
  "cost_trigger": true 또는 false,
  "trigger_type": "직접지원|위탁대행|시설구축|조직설치|대상확대|의무부과|없음",
  "obligation_strength": "mandatory|semi_mandatory|discretionary|aspirational",
  "reason": "왜 이렇게 판단했는지 한 줄"
}}
"""

FINAL_PROMPT = """당신은 지방의회 비용추계 전문가입니다. 새 조례안에 대해 종합 판단하세요.

[조례안명] {bill_name}

[조문별 비용유발 분석]
{articles_summary}

[유사 비용추계서 사례 (RAG)]
{similar_estimates}

[유사 미첨부사유 사례 (RAG)]
{similar_non_attach}

[비용추계 법령 기준 (RAG)]
{legal_ref}

다음 JSON으로 답하세요:
{{
  "verdict": "추계필요" | "미첨부_A" | "미첨부_B" | "미첨부_C",
  "verdict_label": "추계 필요" | "비용 없음(A)" | "추계 곤란(B)" | "기존예산 흡수(C)",
  "reason_summary": "종합 판단 2~3문장",
  "confidence": 0.0~1.0,
  "if_needs_estimate": {{
    "items": [
      {{
        "name": "항목명",
        "category": "인건비|운영비|사업비|지원금|위탁비",
        "formula": "산식 텍스트",
        "trigger_ref": "근거 조문",
        "variables_needed": ["대상자 수", "단가", ...]
      }}
    ],
    "year_estimates": [
      {{"year": 1, "amount_thousand": 숫자 또는 null, "note": "..."}}
    ]
  }} 또는 null,
  "if_non_attachment": {{
    "type": "A|B|C",
    "reason_text": "미첨부 사유 텍스트"
  }} 또는 null
}}
"""


# ── 메인 분석 함수 ─────────────────────────────────────────────────────────────

def analyze_v2(filename: str, content_b64: str) -> dict[str, Any]:
    """server.py가 호출하는 진입점. 입력: 파일명 + base64 PDF. 출력: 결과 dict."""
    t0 = time.time()

    # 1) PDF 추출
    text = extract_pdf_from_b64(content_b64)
    if not text:
        raise ValueError("PDF에서 텍스트를 추출하지 못했습니다.")
    articles = split_articles(text)
    if not articles:
        raise ValueError("조문이 탐지되지 않았습니다.")

    # 조례안명 추출 (PDF 첫 줄에서)
    first_lines = text[:500].split("\n")
    bill_name = next((l.strip() for l in first_lines if len(l.strip()) > 5), filename)

    # 2) 법령 PDF (legal_reference) RAG
    legal_query = "비용추계 미첨부 가능 기준 정의 규정 선언적 권고적"
    leg_emb = try_embed(legal_query)
    legal_chunks = vector_search(leg_emb, source="legal_reference", k=4) if leg_emb else []
    legal_ref = "\n---\n".join((c.get("content") or "")[:800] for c in legal_chunks)
    if not legal_ref:
        legal_ref = (
            "비용추계 판단 기준: 재정 지출 또는 수입 감소를 수반하는 조항은 추계 대상이다. "
            "직접 지원, 보조금, 위탁, 시설 설치, 조직 신설, 인력 배치, 대상 확대, 의무적 사업 수행은 "
            "비용유발 가능성이 높다. 정의·목적·선언적 규정, 단순 명칭 변경, 기존 제도 범위 내 정리는 "
            "비용 미수반 가능성이 있다. 대상자·단가·시행 여부가 불확정하면 미첨부 B, 기존 예산으로 "
            "흡수 가능하면 미첨부 C로 검토한다."
        )

    # 3) 조문별 처리 — 임베딩 배치 + 조문 분석 병렬
    arts = articles[:12]

    # 3-A. 임베딩: 모든 조문 + 전체 본문을 한 번에 (호출 1번)
    full_q = "\n".join(a["text"] for a in articles[:5])[:6000]
    emb_inputs = [a["text"][:2000] for a in arts] + [full_q]
    emb_results = embed_batch(emb_inputs)
    art_embs   = emb_results[:-1]
    bill_emb   = emb_results[-1] if emb_results else None

    # 3-B. 조문별 처리 함수 (각 worker 안에서 vector_search 2번 + gemini 1번)
    def process_article(idx: int, art: dict[str, str], art_emb: list[float] | None) -> dict[str, Any]:
        art_legal = vector_search(art_emb, source="legal_reference", k=2) if art_emb else []
        art_similar = (
            vector_search(art_emb, source="national_assembly", doc_type="cost_estimate", k=2)
            if art_emb else []
        )
        prompt = ARTICLE_PROMPT.format(
            article_text=art["text"], legal_ref=legal_ref[:2000],
        )
        result = gemini_json(prompt) or {}
        return {
            "_idx": idx,
            **art,
            "cost_trigger": bool(result.get("cost_trigger", False)),
            "trigger_type": result.get("trigger_type", "없음"),
            "obligation_strength": result.get("obligation_strength", "aspirational"),
            "reason": result.get("reason", ""),
            "legal_refs": [
                {
                    "chunk_id":   c.get("chunk_id"),
                    "similarity": round(float(c.get("similarity", 0)), 3),
                    "content":    (c.get("content") or "")[:2000],
                }
                for c in art_legal
            ],
            "similar_refs": [
                {
                    "bill_id":   c.get("bill_id"),
                    "bill_no":   c.get("bill_no"),
                    "bill_name": c.get("bill_name"),
                    "similarity": round(float(c.get("similarity", 0)), 3),
                    "content":   (c.get("content") or "")[:2000],
                }
                for c in art_similar
            ],
        }

    # 3-C. 병렬 실행 (Gemini RPM 고려해 동시 6개)
    article_results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [
            pool.submit(process_article, i, art, art_embs[i] if i < len(art_embs) else None)
            for i, art in enumerate(arts)
        ]
        for fut in as_completed(futures):
            article_results.append(fut.result())
    # 원래 순서 복원
    article_results.sort(key=lambda x: x["_idx"])
    for r in article_results:
        r.pop("_idx", None)

    # 4) 본문 임베딩으로 유사 RAG 검색 (위에서 이미 계산됨)
    similar_estimates = (
        vector_search(bill_emb, source="national_assembly", doc_type="cost_estimate", k=5)
        if bill_emb else []
    )
    similar_non_attach = (
        vector_search(bill_emb, source="national_assembly", doc_type="non_attachment_reason", k=3)
        if bill_emb else []
    )

    # 5) 종합 판단 + 추계서 생성
    articles_summary = "\n".join(
        f"{a['no']} | cost_trigger={a['cost_trigger']} | "
        f"type={a['trigger_type']} | strength={a['obligation_strength']} | "
        f"reason={a['reason'][:80]}"
        for a in article_results
    )
    similar_est_text = "\n---\n".join(
        f"[{s.get('bill_no')} {s.get('bill_name','')[:40]}]\n{(s.get('content') or '')[:600]}"
        for s in similar_estimates[:3]
    )
    similar_na_text = "\n---\n".join(
        f"[{s.get('bill_no')} {s.get('bill_name','')[:40]}]\n{(s.get('content') or '')[:400]}"
        for s in similar_non_attach[:2]
    )
    final = gemini_json(FINAL_PROMPT.format(
        bill_name=bill_name,
        articles_summary=articles_summary,
        similar_estimates=similar_est_text or "(없음)",
        similar_non_attach=similar_na_text or "(없음)",
        legal_ref=legal_ref[:2000],
    )) or {}

    # 6) 응답 조립
    return {
        "filename":     filename,
        "billName":     bill_name,
        "generatedAt":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "elapsedSec":   round(time.time() - t0, 1),
        "totalArticles": len(articles),
        "analyzedArticles": len(article_results),

        "articles": article_results,

        "verdict": {
            "type":        final.get("verdict", "unknown"),
            "label":       final.get("verdict_label", "판단 불가"),
            "summary":     final.get("reason_summary", ""),
            "confidence":  float(final.get("confidence", 0.0)),
        },

        "estimate":      final.get("if_needs_estimate"),
        "nonAttachment": final.get("if_non_attachment"),

        "references": {
            "similar_bills_cost_estimate": [
                {
                    "bill_id":    s.get("bill_id"),
                    "bill_no":    s.get("bill_no"),
                    "bill_name":  s.get("bill_name"),
                    "similarity": round(float(s.get("similarity", 0)), 3),
                    "content":    (s.get("content") or "")[:2000],
                }
                for s in similar_estimates
            ],
            "similar_bills_non_attachment": [
                {
                    "bill_id":    s.get("bill_id"),
                    "bill_no":    s.get("bill_no"),
                    "bill_name":  s.get("bill_name"),
                    "similarity": round(float(s.get("similarity", 0)), 3),
                    "content":    (s.get("content") or "")[:2000],
                }
                for s in similar_non_attach
            ],
            "legal_references": [
                {
                    "chunk_id":   c.get("chunk_id"),
                    "similarity": round(float(c.get("similarity", 0)), 3),
                    "content":    (c.get("content") or "")[:2000],
                }
                for c in legal_chunks
            ],
        },
    }
