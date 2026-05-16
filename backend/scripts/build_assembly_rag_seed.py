from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import GENERATED_DIR, SCRIPT_DIR
from backend.scripts.collect_open_assembly_cost_docs import (
    LIKMS_AJAX_URL,
    dedupe_docs,
    extract_hidden_inputs,
    extract_memo,
    extract_report_docs,
    fetch_bill_rows,
    get_api_key,
    is_cost_related,
    request_bytes,
    request_text,
    safe_filename,
)


DOCUMENT_TYPES_FOR_DOWNLOAD = {
    "bill_text",
    "cost_estimate",
    "non_attachment_reason",
}

STAT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "population_total": ("인구", "주민등록인구", "총인구"),
    "population_by_age": ("연령별", "고령", "노인", "청년", "아동", "영유아", "청소년"),
    "households": ("가구", "세대", "1인가구", "한부모"),
    "benefit_recipients": ("수급자", "기초생활", "차상위", "급여대상", "복지대상"),
    "disabled_population": ("장애인", "등록장애인"),
    "consumer_price_index": ("소비자물가", "물가상승", "물가지수", "CPI"),
    "wages": ("임금", "평균임금", "최저임금", "보수", "인건비"),
    "businesses_workers": ("사업체", "종사자", "근로자", "취업자", "고용률"),
    "housing": ("주택", "임대주택", "공공임대", "주거급여"),
    "students_schools": ("학생", "학교", "학급", "교원", "어린이집"),
    "facilities": ("시설", "복지관", "의료기관", "문화시설", "센터"),
}

COST_TRIGGER_KEYWORDS = (
    "지원",
    "보조",
    "지급",
    "설치",
    "운영",
    "위탁",
    "구축",
    "실시",
    "수행",
    "제공",
    "양성",
    "교육",
    "상담",
    "센터",
    "기금",
    "출연",
    "예산",
    "비용",
)

TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a small local RAG seed set from National Assembly bills."
    )
    parser.add_argument("--age", default="22", help="National Assembly term.")
    parser.add_argument("--page", type=int, default=1, help="Start page.")
    parser.add_argument("--pages", type=int, default=1, help="Pages to request.")
    parser.add_argument("--size", type=int, default=50, help="Rows per page.")
    parser.add_argument("--max-bills", type=int, default=50, help="Bills to inspect.")
    parser.add_argument("--sleep", type=float, default=0.1, help="Delay between bills.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=GENERATED_DIR / "assembly_rag_seed",
        help="Output directory.",
    )
    return parser.parse_args()


def classify_document(document_name: str, label: str) -> str:
    text = f"{document_name} {label}".replace(" ", "")
    if "미첨부" in text and is_cost_related(text):
        return "non_attachment_reason"
    if "비용추계" in text or "추계서" in text:
        return "cost_estimate"
    if "의안원문" in text:
        return "bill_text"
    if "검토보고" in text:
        return "review_report"
    if "심사보고" in text:
        return "committee_report"
    if "회의록" in text:
        return "minutes"
    return "other"


def select_preferred_file_per_document(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for doc in docs:
        grouped[(doc["documentName"], doc["documentType"])].append(doc)

    selected: list[dict[str, Any]] = []
    for group in grouped.values():
        file_types = {item["fileType"] for item in group}
        preferred = sorted(
            group,
            key=lambda item: (
                0
                if item["fileType"] == "pdf"
                else 1
                if item["fileType"] in {"hwp", "hwpx"}
                else 2
            ),
        )[0]
        preferred["pdfAvailable"] = "pdf" in file_types
        preferred["hwpAvailable"] = bool(file_types.intersection({"hwp", "hwpx"}))
        preferred["fallbackRequired"] = preferred["fileType"] != "pdf"
        selected.append(preferred)
    return dedupe_docs(selected)


def download_document(
    bill: dict[str, Any],
    doc: dict[str, Any],
    output_dir: Path,
) -> Path:
    bill_no = safe_filename(bill.get("BILL_NO") or bill.get("BILL_ID") or "bill")
    bill_dir = output_dir / "files" / bill_no
    bill_dir.mkdir(parents=True, exist_ok=True)
    suffix = doc["fileType"] if doc["fileType"] != "unknown" else "bin"
    name = safe_filename(doc["documentName"] or doc["documentType"] or "document")
    filename = f"{doc['documentType']}_{name}.{suffix}"
    path = unique_path(bill_dir / filename)
    path.write_bytes(request_bytes(doc["url"], timeout=60))
    return path


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not allocate unique path for {path}")


def extract_pdf_text(path: Path) -> str:
    if path.suffix.lower() != ".pdf":
        return ""
    command = ["swift", str(SCRIPT_DIR / "extract_pdf_text.swift"), str(path)]
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


# 표 행: |로 구분되거나 공백 정렬된 숫자/텍스트 줄
_TABLE_LINE_RE = re.compile(r"(\|.+\||^\s{2,}\S.+\s{2,}\S)", re.MULTILINE)
# 조문 경계: "제N조" 패턴
_ARTICLE_RE = re.compile(r"제\s*\d+\s*조(?:의\d+)?(?:\s*\([^)]+\))?")


def _is_table_block(text: str) -> bool:
    """줄의 30% 이상이 표 형식이면 표 블록으로 판단."""
    lines = text.splitlines()
    if not lines:
        return False
    table_lines = sum(1 for ln in lines if _TABLE_LINE_RE.search(ln))
    return table_lines / len(lines) >= 0.3


def split_chunks(
    text: str,
    *,
    max_chars: int = 2400,   # ~800 tokens
    overlap: int = 600,      # ~200 tokens
) -> list[str]:
    """표·조문 경계를 보존하면서 chunk 분할.

    우선순위:
    1. 표 블록 → 통째로 하나의 chunk (헤더 포함)
    2. 조문(제N조) 단위 분할
    3. 나머지 → 슬라이딩 윈도우
    """
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        return []

    # 조문 단위로 1차 분할
    article_splits = _ARTICLE_RE.split(text)
    article_headers = _ARTICLE_RE.findall(text)

    segments: list[str] = []
    # 조문 앞 서두가 있으면 포함
    if article_splits[0].strip():
        segments.append(article_splits[0].strip())
    for header, body in zip(article_headers, article_splits[1:]):
        segments.append(f"{header} {body}".strip())

    # 조문 분할 실패 시 원문 그대로
    if not segments:
        segments = [text]

    chunks: list[str] = []
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        # 표 블록이면 통째로 보존 (max_chars의 2배까지 허용)
        if _is_table_block(segment) or len(segment) <= max_chars * 2:
            chunks.append(segment)
            continue

        # 긴 일반 텍스트 → 슬라이딩 윈도우
        start = 0
        while start < len(segment):
            end = min(start + max_chars, len(segment))
            chunk = segment[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end == len(segment):
                break
            start = max(0, end - overlap)

    return chunks


def detect_text_extract_status(text: str, file_type: str) -> str:
    """텍스트 추출 결과로 상태 판단."""
    if file_type in {"hwp", "hwpx"}:
        return "unsupported_hwp"
    if not text or not text.strip():
        return "empty_text"   # → ocr_required 대상
    return "success"


def extract_cost_trigger_snippets(text: str) -> list[str]:
    snippets: list[str] = []
    article_pattern = re.compile(r"(제\s*\d+\s*조(?:의\d+)?\s*\([^)]+\).*?)(?=제\s*\d+\s*조|\Z)")
    matches = article_pattern.findall(text)
    candidates = matches if matches else re.split(r"(?<=[.!?。])\s+|\n{2,}", text)

    for candidate in candidates:
        cleaned = re.sub(r"\s+", " ", candidate).strip()
        if len(cleaned) < 20:
            continue
        if any(keyword in cleaned for keyword in COST_TRIGGER_KEYWORDS):
            snippets.append(cleaned[:2400])
    return snippets[:12]


def extract_stat_candidates(text: str, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for key, keywords in STAT_KEYWORDS.items():
        hits = [keyword for keyword in keywords if keyword.lower() in text.lower()]
        if not hits:
            continue
        results.append(
            {
                "variableKey": key,
                "matchedKeywords": sorted(set(hits)),
                "billNo": metadata["billNo"],
                "billName": metadata["billName"],
                "documentType": metadata["documentType"],
                "sourceDocument": metadata["documentName"],
            }
        )
    return results


def collect_bill_artifacts(
    bill: dict[str, Any],
    output_dir: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    detail_url = str(bill.get("DETAIL_LINK") or "")
    detail_html = request_text(detail_url)
    form = extract_hidden_inputs(detail_html)
    form.setdefault("billId", str(bill.get("BILL_ID", "")))
    form.setdefault("billNo", str(bill.get("BILL_NO", "")))
    form.setdefault("billKindCd", "법률안")

    fragment_html = request_text(LIKMS_AJAX_URL, data=form)
    docs = extract_report_docs(fragment_html)
    for doc in docs:
        doc["documentType"] = classify_document(doc["documentName"], doc["label"])
        doc["downloadedTo"] = None
        doc["textExtracted"] = False

    docs = select_preferred_file_per_document(docs)
    selected_docs = [doc for doc in docs if doc["documentType"] in DOCUMENT_TYPES_FOR_DOWNLOAD]

    bill_record = {
        "source": "national_assembly",
        "age": bill.get("AGE"),
        "billId": bill.get("BILL_ID"),
        "billNo": bill.get("BILL_NO"),
        "billName": bill.get("BILL_NAME"),
        "proposer": bill.get("PROPOSER"),
        "proposeDate": bill.get("PROPOSE_DT"),
        "committee": bill.get("COMMITTEE"),
        "processResult": bill.get("PROC_RESULT"),
        "detailLink": detail_url,
        "memo": extract_memo(detail_html, fragment_html),
        "allDocumentCount": len(docs),
        "selectedDocumentCount": len(selected_docs),
    }

    document_records: list[dict[str, Any]] = []
    chunk_records: list[dict[str, Any]] = []
    stat_candidates: list[dict[str, Any]] = []

    for doc in selected_docs:
        local_path = download_document(bill, doc, output_dir)
        text = extract_pdf_text(local_path)
        extract_status = detect_text_extract_status(text, doc["fileType"])
        doc["downloadedTo"] = str(local_path)
        doc["textExtracted"] = extract_status == "success"
        doc["textExtractStatus"] = extract_status
        doc["ocrRequired"] = extract_status == "empty_text"

        document_record = {
            "source": "national_assembly",
            "billId": bill.get("BILL_ID"),
            "billNo": bill.get("BILL_NO"),
            "billName": bill.get("BILL_NAME"),
            "documentName": doc["documentName"],
            "documentType": doc["documentType"],
            "fileType": doc["fileType"],
            "url": doc["url"],
            "localPath": str(local_path),
            "textExtractStatus": extract_status,
            "ocrRequired": doc["ocrRequired"],
            "pdfAvailable": doc.get("pdfAvailable", False),
            "hwpAvailable": doc.get("hwpAvailable", False),
            "fallbackRequired": doc.get("fallbackRequired", False),
        }
        document_records.append(document_record)

        if not text:
            continue  # 텍스트 없으면 chunk 생성 건너뜀

        text_chunks = split_chunks(text)
        if doc["documentType"] == "bill_text":
            trigger_chunks = extract_cost_trigger_snippets(text)
            text_chunks = trigger_chunks or text_chunks[:4]

        for chunk_index, chunk in enumerate(text_chunks, start=1):
            chunk_id = f"{bill.get('BILL_ID')}:{doc['documentType']}:{chunk_index}"
            chunk_record = {
                "chunkId": chunk_id,
                "source": "national_assembly",
                "billId": bill.get("BILL_ID"),
                "billNo": bill.get("BILL_NO"),
                "billName": bill.get("BILL_NAME"),
                "age": bill.get("AGE"),
                "committee": bill.get("COMMITTEE"),
                "proposeDate": bill.get("PROPOSE_DT"),
                "documentName": doc["documentName"],
                "documentType": doc["documentType"],
                "chunkIndex": chunk_index,
                "text": chunk,
                # embedding: None (실제 임베딩은 별도 스크립트에서 처리)
            }
            chunk_records.append(chunk_record)
            stat_candidates.extend(extract_stat_candidates(chunk, chunk_record))

    return bill_record, document_records, chunk_records, stat_candidates


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def summarize_stat_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = candidate["variableKey"]
        if key not in by_key:
            by_key[key] = {
                "variableKey": key,
                "candidateSource": "KOSIS_OR_RELATED_PUBLIC_STATISTICS",
                "matchedKeywords": set(),
                "usedInDocuments": 0,
                "exampleBills": [],
                "kosisMappingStatus": "needs_mapping",
            }
        item = by_key[key]
        item["matchedKeywords"].update(candidate["matchedKeywords"])
        item["usedInDocuments"] += 1
        if len(item["exampleBills"]) < 5:
            item["exampleBills"].append(
                {
                    "billNo": candidate["billNo"],
                    "billName": candidate["billName"],
                    "documentType": candidate["documentType"],
                }
            )

    result: list[dict[str, Any]] = []
    for item in by_key.values():
        result.append(
            {
                **item,
                "matchedKeywords": sorted(item["matchedKeywords"]),
            }
        )
    return sorted(result, key=lambda row: row["usedInDocuments"], reverse=True)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    api_key = get_api_key()
    bills = fetch_bill_rows(api_key, args)

    bill_records: list[dict[str, Any]] = []
    document_records: list[dict[str, Any]] = []
    chunk_records: list[dict[str, Any]] = []
    stat_candidates: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for index, bill in enumerate(bills, start=1):
        try:
            bill_record, documents, chunks, stats = collect_bill_artifacts(bill, args.output_dir)
            bill_records.append(bill_record)
            document_records.extend(documents)
            chunk_records.extend(chunks)
            stat_candidates.extend(stats)
            print(
                f"[{index}/{len(bills)}] {bill_record['billNo']} "
                f"docs={len(documents)} chunks={len(chunks)} stats={len(stats)}"
            )
        except Exception as exc:  # noqa: BLE001 - keep collecting on malformed documents.
            errors.append(
                {
                    "billId": str(bill.get("BILL_ID", "")),
                    "billNo": str(bill.get("BILL_NO", "")),
                    "error": repr(exc),
                }
            )
            print(f"[{index}/{len(bills)}] ERROR {bill.get('BILL_NO')}: {exc}", file=sys.stderr)
        time.sleep(args.sleep)

    write_jsonl(args.output_dir / "bills.jsonl", bill_records)
    write_jsonl(args.output_dir / "documents.jsonl", document_records)
    write_jsonl(args.output_dir / "chunks.jsonl", chunk_records)
    write_jsonl(args.output_dir / "stat_variable_mentions.jsonl", stat_candidates)

    stat_catalog = summarize_stat_candidates(stat_candidates)
    (args.output_dir / "kosis_needed_statistics_candidates.json").write_text(
        json.dumps(stat_catalog, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 파일 타입 통계 리포트
    pdf_available = sum(1 for d in document_records if d.get("pdfAvailable"))
    hwp_only = sum(
        1 for d in document_records
        if d.get("fallbackRequired") and not d.get("pdfAvailable")
    )
    text_success = sum(
        1 for d in document_records if d.get("textExtractStatus") == "success"
    )
    text_empty = sum(
        1 for d in document_records if d.get("textExtractStatus") == "empty_text"
    )
    ocr_required = sum(1 for d in document_records if d.get("ocrRequired"))
    hwp_unsupported = sum(
        1 for d in document_records if d.get("textExtractStatus") == "unsupported_hwp"
    )

    summary = {
        "age": args.age,
        "inspectedBills": len(bills),
        "storedBills": len(bill_records),
        "storedDocuments": len(document_records),
        "storedChunks": len(chunk_records),
        "statVariableKinds": len(stat_catalog),
        "fileTypeStats": {
            "pdfAvailableCount": pdf_available,
            "hwpOnlyCount": hwp_only,
            "textExtractSuccessCount": text_success,
            "textExtractEmptyCount": text_empty,
            "ocrRequiredCount": ocr_required,
            "hwpUnsupportedCount": hwp_unsupported,
        },
        "errors": errors,
        "outputs": {
            "bills": str(args.output_dir / "bills.jsonl"),
            "documents": str(args.output_dir / "documents.jsonl"),
            "chunks": str(args.output_dir / "chunks.jsonl"),
            "statMentions": str(args.output_dir / "stat_variable_mentions.jsonl"),
            "statCatalog": str(args.output_dir / "kosis_needed_statistics_candidates.json"),
        },
    }
    (args.output_dir / "pipeline_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
