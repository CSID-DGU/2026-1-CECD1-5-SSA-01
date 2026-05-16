"""build_assembly_rag_seed_fast.py

최적화된 의안 수집 파이프라인.

기존 build_assembly_rag_seed.py 대비:
  - ZIP 일괄 다운로드 (HTML 크롤링 제거)
  - 병렬 다운로드 (ThreadPoolExecutor)
  - PyMuPDF로 PDF 텍스트 추출 (Swift subprocess 제거)
  - HWP 파일 무시 (PDF만 추출)
  - 이미 처리된 bill_id 스킵 (재시작 가능)

출력:
  - bills.jsonl, documents.jsonl, chunks.jsonl, stat_variable_mentions.jsonl
  - 기존 파이프라인의 다음 단계(upload, embed, tag)와 호환

사용법:
    python -m backend.scripts.build_assembly_rag_seed_fast \
        --age 21 --max-bills 50 --concurrency 8
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import GENERATED_DIR, get_env

import fitz  # type: ignore[import-untyped]

# ── 상수 ──────────────────────────────────────────────────────────────────────

OPEN_ASSEMBLY_API_URL = "https://open.assembly.go.kr/portal/openapi/nzmimeepazxkubdpn"
LIKMS_ZIP_URL = "http://likms.assembly.go.kr/bill/bi/bill/detail/downloadDtlZip.do"
USER_AGENT = "Mozilla/5.0 cost-estimation-system/0.2"

DOC_TYPE_PATTERNS = (
    ("non_attachment_reason", ("미첨부",)),
    ("cost_estimate",         ("비용추계", "추계서")),
    ("bill_text",             ("의안원문",)),
)

STAT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "population_total":     ("인구", "주민등록인구", "총인구"),
    "population_by_age":    ("연령별", "고령", "노인", "청년", "아동", "영유아", "청소년"),
    "households":           ("가구", "세대", "1인가구", "한부모"),
    "benefit_recipients":   ("수급자", "기초생활", "차상위", "급여대상"),
    "disabled_population":  ("장애인", "등록장애인"),
    "consumer_price_index": ("소비자물가", "물가상승", "물가지수", "CPI"),
    "wages":                ("임금", "평균임금", "최저임금", "보수", "인건비"),
    "businesses_workers":   ("사업체", "종사자", "근로자", "취업자", "고용률"),
    "housing":              ("주택", "임대주택", "공공임대", "주거급여"),
    "students_schools":     ("학생", "학교", "학급", "교원", "어린이집"),
}

COST_TRIGGER_KEYWORDS = (
    "지원", "보조", "지급", "설치", "운영", "위탁", "구축",
    "실시", "수행", "제공", "양성", "교육", "상담", "센터",
    "기금", "출연", "예산", "비용",
)

_ARTICLE_RE = re.compile(r"제\s*\d+\s*조(?:의\d+)?(?:\s*\([^)]+\))?")
_TABLE_LINE = re.compile(r"(\|.+\||^\s{2,}\S.+\s{2,}\S)", re.MULTILINE)


# ── 인자 파싱 ──────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="최적화된 국회 의안 수집 (ZIP + 병렬 + PyMuPDF)")
    p.add_argument("--age", default="21")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--pages", type=int, default=1)
    p.add_argument("--size", type=int, default=50)
    p.add_argument("--max-bills", type=int, default=50)
    p.add_argument("--concurrency", type=int, default=8, help="병렬 다운로드 수")
    p.add_argument("--zip-timeout", type=int, default=180, help="ZIP 요청 타임아웃(초)")
    p.add_argument(
        "--output-dir", type=Path,
        default=GENERATED_DIR / "assembly_rag_seed",
    )
    p.add_argument("--skip-existing", action="store_true",
                   help="bills.jsonl에 이미 있는 bill_id 스킵")
    p.add_argument("--bills-from-discovery", type=Path,
                   help="디스커버리 JSON에서 추계서 또는 미첨부 있는 의안만 처리")
    p.add_argument("--include-cost-estimate", action="store_true",
                   help="--bills-from-discovery 사용 시 추계서 있는 의안 포함 (기본 켜짐)")
    p.add_argument("--include-non-attachment", action="store_true",
                   help="--bills-from-discovery 사용 시 미첨부 의안 포함 (기본 켜짐)")
    return p.parse_args()


# ── 의안 목록 ──────────────────────────────────────────────────────────────────

def fetch_bill_rows(api_key: str, args: argparse.Namespace) -> list[dict[str, Any]]:
    """일반 API 페이지 순회 모드."""
    rows: list[dict[str, Any]] = []
    for page in range(args.page, args.page + args.pages):
        q = {"KEY": api_key, "Type": "json",
             "pIndex": str(page), "pSize": str(args.size), "AGE": args.age}
        url = f"{OPEN_ASSEMBLY_API_URL}?{urllib.parse.urlencode(q)}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read())
        for item in payload.get("nzmimeepazxkubdpn", []):
            if "row" in item:
                rows.extend(item["row"])
        if len(rows) >= args.max_bills:
            break
    return rows[:args.max_bills]


def load_bills_from_discovery(path: Path, include_ce: bool, include_na: bool,
                              max_bills: int) -> list[dict[str, Any]]:
    """디스커버리 JSON에서 추계서/미첨부 있는 의안만 추출.

    디스커버리 결과 키는 대문자 (BILL_ID, BILL_NAME...). 본 파이프라인은
    국회 API와 같은 키를 요구하므로 그대로 사용 가능.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    selected: list[dict[str, Any]] = []
    for r in data.get("results", []):
        if r.get("error"):
            continue
        keep = (include_ce and r.get("has_cost_estimate")) or \
               (include_na and r.get("has_non_attachment"))
        if not keep:
            continue
        # 국회 API row 형식으로 정규화
        selected.append({
            "BILL_ID":      r["BILL_ID"],
            "BILL_NO":      r.get("BILL_NO"),
            "BILL_NAME":    r.get("BILL_NAME"),
            "AGE":          r.get("AGE"),
            "PROPOSER":     r.get("PROPOSER"),
            "PROPOSE_DT":   r.get("PROPOSE_DT"),
            "COMMITTEE":    r.get("COMMITTEE"),
            "PROC_RESULT":  r.get("PROC_RESULT"),
            "DETAIL_LINK":  f"http://likms.assembly.go.kr/bill/billDetail.do?billId={r['BILL_ID']}",
        })
    if max_bills:
        selected = selected[:max_bills]
    return selected


# ── ZIP 다운로드 ──────────────────────────────────────────────────────────────

def download_zip(bill_id: str, kind: str = "법률안", *, timeout: int = 180) -> bytes:
    data = urllib.parse.urlencode({
        "billId": bill_id, "billKindCd": kind, "dwFileGbn": "B",
    }).encode()
    req = urllib.request.Request(
        LIKMS_ZIP_URL, data=data, headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def classify_filename(name: str) -> str | None:
    flat = name.replace(" ", "")
    for doc_type, kws in DOC_TYPE_PATTERNS:
        if any(kw in flat for kw in kws):
            return doc_type
    return None


def extract_pdfs_from_zip(zip_bytes: bytes) -> dict[str, dict[str, Any]]:
    """ZIP 안에서 분류 가능한 PDF만 추출. doc_type → {filename, pdf_bytes}.

    같은 doc_type이 여러 개면 PDF 우선. HWP는 무시.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        return {}

    by_type: dict[str, list[tuple[str, bytes]]] = defaultdict(list)
    for info in zf.infolist():
        if info.is_dir():
            continue
        # 파일명 인코딩 복원 (cp437로 디코드된 UTF-8 한글 처리)
        name = info.filename
        try:
            name = info.filename.encode("cp437").decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
        if not name.lower().endswith(".pdf"):
            continue
        doc_type = classify_filename(name)
        if not doc_type:
            continue
        by_type[doc_type].append((name, zf.read(info)))

    selected: dict[str, dict[str, Any]] = {}
    for doc_type, items in by_type.items():
        items.sort(key=lambda x: x[0])
        selected[doc_type] = {"filename": items[0][0], "pdf_bytes": items[0][1]}
    return selected


# ── PDF → 텍스트 (PyMuPDF) ────────────────────────────────────────────────────

def extract_pdf_text(pdf_bytes: bytes) -> str:
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            parts = [page.get_text() for page in doc]
        return "\n".join(parts).strip()
    except Exception:
        return ""


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
    article_splits = _ARTICLE_RE.split(text)
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


def extract_cost_trigger_snippets(text: str) -> list[str]:
    article_pattern = re.compile(
        r"(제\s*\d+\s*조(?:의\d+)?\s*\([^)]+\).*?)(?=제\s*\d+\s*조|\Z)"
    )
    matches = article_pattern.findall(text)
    candidates = matches if matches else re.split(r"(?<=[.!?。])\s+|\n{2,}", text)
    snippets: list[str] = []
    for c in candidates:
        cleaned = re.sub(r"\s+", " ", c).strip()
        if len(cleaned) < 20:
            continue
        if any(kw in cleaned for kw in COST_TRIGGER_KEYWORDS):
            snippets.append(cleaned[:2400])
    return snippets[:12]


def extract_stat_candidates(text: str, meta: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for key, kws in STAT_KEYWORDS.items():
        hits = [kw for kw in kws if kw.lower() in text.lower()]
        if not hits:
            continue
        results.append({
            "variableKey":     key,
            "matchedKeywords": sorted(set(hits)),
            "billNo":          meta["billNo"],
            "billName":        meta["billName"],
            "documentType":    meta["documentType"],
            "sourceDocument":  meta["documentName"],
        })
    return results


# ── 의안 1건 처리 ──────────────────────────────────────────────────────────────

def process_bill(bill: dict[str, Any], zip_timeout: int) -> dict[str, Any]:
    """ZIP 다운 → PDF 추출 → 텍스트 추출 → 청킹. 모두 인메모리."""
    bill_id   = str(bill.get("BILL_ID") or "")
    bill_no   = str(bill.get("BILL_NO") or "")
    bill_name = str(bill.get("BILL_NAME") or "")

    record: dict[str, Any] = {
        "bill": {
            "source": "national_assembly",
            "age": bill.get("AGE"),
            "billId": bill_id,
            "billNo": bill_no,
            "billName": bill_name,
            "proposer": bill.get("PROPOSER"),
            "proposeDate": bill.get("PROPOSE_DT"),
            "committee": bill.get("COMMITTEE"),
            "processResult": bill.get("PROC_RESULT"),
            "detailLink": bill.get("DETAIL_LINK"),
            "memo": "",
            "allDocumentCount": 0,
            "selectedDocumentCount": 0,
            "hasCostEstimate":  False,
            "hasNonAttachment": False,
        },
        "documents":      [],
        "chunks":         [],   # cost_estimate / non_attachment (RAG 대상)
        "bill_text_only": [],   # bill_text snippets (TAG만 사용, RAG X)
        "stats":          [],
        "error":          None,
    }
    try:
        zip_bytes = download_zip(bill_id, timeout=zip_timeout)
        pdfs = extract_pdfs_from_zip(zip_bytes)
    except Exception as exc:
        record["error"] = repr(exc)
        return record

    record["bill"]["allDocumentCount"] = len(pdfs)
    record["bill"]["selectedDocumentCount"] = len(pdfs)
    record["bill"]["hasCostEstimate"]  = "cost_estimate" in pdfs
    record["bill"]["hasNonAttachment"] = "non_attachment_reason" in pdfs

    for doc_type, item in pdfs.items():
        text = extract_pdf_text(item["pdf_bytes"])
        status = "success" if text.strip() else "empty_text"
        doc_record = {
            "source":            "national_assembly",
            "billId":            bill_id,
            "billNo":            bill_no,
            "billName":          bill_name,
            "documentName":      item["filename"],
            "documentType":      doc_type,
            "fileType":          "pdf",
            "url":               None,
            "localPath":         None,
            "textExtractStatus": status,
            "ocrRequired":       status == "empty_text",
            "pdfAvailable":      True,
            "hwpAvailable":      False,
            "fallbackRequired":  False,
        }
        record["documents"].append(doc_record)
        if status != "success":
            continue

        # bill_text는 RAG 청크에 저장하지 않음 — bill_text_only 별도 파일로 분리
        # TAG 단계에서만 사용. assembly_chunks에는 절대 안 들어감.
        if doc_type == "bill_text":
            for i, snippet in enumerate(extract_cost_trigger_snippets(text)[:8], 1):
                record["bill_text_only"].append({
                    "chunkId":      f"{bill_id}:{doc_type}:{i}",
                    "billId":       bill_id,
                    "billNo":       bill_no,
                    "billName":     bill_name,
                    "age":          bill.get("AGE"),
                    "committee":    bill.get("COMMITTEE"),
                    "proposeDate":  bill.get("PROPOSE_DT"),
                    "documentName": item["filename"],
                    "documentType": doc_type,
                    "chunkIndex":   i,
                    "text":         snippet,
                })
            continue

        # cost_estimate / non_attachment → RAG 청크 + 통계 후보
        for i, chunk in enumerate(split_chunks(text), 1):
            chunk_record = {
                "chunkId":      f"{bill_id}:{doc_type}:{i}",
                "source":       "national_assembly",
                "billId":       bill_id,
                "billNo":       bill_no,
                "billName":     bill_name,
                "age":          bill.get("AGE"),
                "committee":    bill.get("COMMITTEE"),
                "proposeDate":  bill.get("PROPOSE_DT"),
                "documentName": item["filename"],
                "documentType": doc_type,
                "chunkIndex":   i,
                "text":         chunk,
            }
            record["chunks"].append(chunk_record)
            record["stats"].extend(extract_stat_candidates(chunk, chunk_record))
    return record


# ── 메인 ──────────────────────────────────────────────────────────────────────

def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_existing_bill_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out: set[str] = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    out.add(json.loads(line).get("billId", ""))
                except json.JSONDecodeError:
                    continue
    return out


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # 디스커버리 JSON 사용 시 API 안 거치고 리스트에서 직접 추출
    if args.bills_from_discovery:
        include_ce = args.include_cost_estimate or not args.include_non_attachment  # 기본 True
        include_na = args.include_non_attachment or not args.include_cost_estimate  # 기본 True
        # 둘 다 안 키면 둘 다 켜는 기본 동작
        if not args.include_cost_estimate and not args.include_non_attachment:
            include_ce = include_na = True
        print(f"디스커버리에서 의안 추출 (CE={include_ce}, NA={include_na})...")
        bills = load_bills_from_discovery(
            args.bills_from_discovery, include_ce, include_na, args.max_bills,
        )
        print(f"  → {len(bills)}건")
    else:
        api_key = get_env("OPEN_ASSEMBLY_API_KEY")
        if not api_key:
            raise SystemExit("OPEN_ASSEMBLY_API_KEY 가 .env에 필요합니다.")
        print(f"의안 목록 조회 (age={args.age}, max={args.max_bills})...")
        bills = fetch_bill_rows(api_key, args)
        print(f"  → {len(bills)}건")

    if args.skip_existing:
        existing = load_existing_bill_ids(args.output_dir / "bills.jsonl")
        before = len(bills)
        bills = [b for b in bills if str(b.get("BILL_ID")) not in existing]
        print(f"  → 기존 {len(existing)}건 스킵, 처리할 의안 {len(bills)}건 (이전 {before})")

    bill_records:    list[dict[str, Any]] = []
    document_records: list[dict[str, Any]] = []
    chunk_records:   list[dict[str, Any]] = []      # cost_estimate + non_attachment
    bill_text_records: list[dict[str, Any]] = []    # bill_text snippets (TAG only)
    stat_candidates: list[dict[str, Any]] = []
    errors:          list[dict[str, str]] = []

    t0 = time.time()
    print(f"병렬 다운로드 시작 (concurrency={args.concurrency})...")
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(process_bill, b, args.zip_timeout): b for b in bills}
        for i, fut in enumerate(as_completed(futures), 1):
            bill = futures[fut]
            try:
                rec = fut.result()
            except Exception as exc:
                errors.append({"billId": str(bill.get("BILL_ID")), "error": repr(exc)})
                print(f"  [{i}/{len(bills)}] ERROR {bill.get('BILL_NO')}: {exc}",
                      file=sys.stderr)
                continue
            if rec["error"]:
                errors.append({"billId": rec["bill"]["billId"], "error": rec["error"]})
                print(f"  [{i}/{len(bills)}] ERROR {rec['bill']['billNo']}: {rec['error']}",
                      file=sys.stderr)
                continue
            bill_records.append(rec["bill"])
            document_records.extend(rec["documents"])
            chunk_records.extend(rec["chunks"])
            bill_text_records.extend(rec["bill_text_only"])
            stat_candidates.extend(rec["stats"])
            doc_types = Counter(d["documentType"] for d in rec["documents"])
            print(f"  [{i}/{len(bills)}] {rec['bill']['billNo']} "
                  f"docs={dict(doc_types)} chunks={len(rec['chunks'])}")

    elapsed = time.time() - t0

    write_jsonl(args.output_dir / "bills.jsonl",     bill_records)
    write_jsonl(args.output_dir / "documents.jsonl", document_records)
    write_jsonl(args.output_dir / "chunks.jsonl",    chunk_records)
    write_jsonl(args.output_dir / "bill_text_for_tag.jsonl", bill_text_records)
    write_jsonl(args.output_dir / "stat_variable_mentions.jsonl", stat_candidates)

    summary = {
        "age":               args.age,
        "elapsedSeconds":    round(elapsed, 1),
        "concurrency":       args.concurrency,
        "inspectedBills":    len(bills),
        "storedBills":       len(bill_records),
        "storedDocuments":   len(document_records),
        "storedChunks":      len(chunk_records),
        "billTextSnippets":  len(bill_text_records),
        "documentTypeCounts": dict(Counter(d["documentType"] for d in document_records)),
        "billsWithCostEstimate":  sum(1 for b in bill_records if b["hasCostEstimate"]),
        "billsWithNonAttachment": sum(1 for b in bill_records if b["hasNonAttachment"]),
        "errors": errors,
    }
    (args.output_dir / "pipeline_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
