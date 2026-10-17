"""제22대 국회 비용추계서와 대응 의안원문 PDF를 파일로 수집한다.

기존 ``cost_estimate_discovery_22.json``의 후보를 실제 ZIP으로 다시 확인한다.
비용추계요구서, 미첨부사유서, 깨진 PDF는 비용추계서로 저장하지 않는다.

저장 구조::

    backend/generated/assembly_22_pdfs/
      by_bill/<의안번호>/
        cost_estimate.pdf
        bill_text.pdf
        metadata.json
      by_category/<카테고리>/<의안번호> -> ../../by_bill/<의안번호>
      manifest.jsonl
      summary.json

한 추계서가 여러 비용 성격을 가질 수 있으므로 원본은 한 번만 저장하고, 카테고리
폴더에는 상대 심볼릭 링크를 만든다. 재실행 시 완결된 의안번호는 건너뛴다.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import fitz  # type: ignore[import-untyped]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import GENERATED_DIR, get_env


DISCOVERY_DEFAULT = GENERATED_DIR / "cost_estimate_discovery_22.json"
OUTPUT_DEFAULT = GENERATED_DIR / "assembly_22_pdfs"
ZIP_URL = "http://likms.assembly.go.kr/bill/bi/bill/detail/downloadDtlZip.do"
USER_AGENT = "Mozilla/5.0 cost-estimation-system/assembly-22-pdf-collector"

CATEGORY_DIRS = {
    "인건비": "01_인건비",
    "물건비": "02_물건비",
    "이전지출": "03_이전지출",
    "자본지출": "04_자본지출",
    "조세감면": "05_조세감면",
    "세외수입감소": "06_세외수입감소",
    "출자출연": "07_출자출연",
    "분류검토": "99_분류검토",
}

# TAG가 없는 신규 문서는 추계서 본문의 명시적 비용 용어로만 후보 분류한다.
CATEGORY_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "인건비": (
        re.compile(r"인건비|인력운영비|보수액|봉급액|연봉|기관부담금"),
        re.compile(r"(?:공무원|직원|상임위원).{0,20}(?:보수|급여|수당)"),
    ),
    "물건비": (
        re.compile(r"운영비|기본경비|사무관리비|공공운영비|연구용역비|위탁비"),
        re.compile(r"교육비|홍보비|조사비|행사비|시스템\s*(?:구축|운영)비"),
    ),
    "이전지출": (
        re.compile(r"보조금|지원금|보상금|장려금|교부금|부담금\s*지원"),
        re.compile(r"(?:대상자|수급자|가구|기업).{0,30}(?:지급|지원)"),
    ),
    "자본지출": (
        re.compile(r"시설비|건설비|공사비|설계비|감리비|토지매입|부지매입"),
        re.compile(r"자산취득비|장비구입비|청사\s*(?:신축|건립)|시설\s*건립"),
    ),
    "조세감면": (
        re.compile(r"조세지출|세수\s*(?:감소|감면)|세액\s*(?:공제|감면)"),
        re.compile(r"(?:소득세|법인세|부가가치세|관세|지방세).{0,25}(?:감면|면제|공제|비과세)"),
    ),
    "세외수입감소": (
        re.compile(r"세외수입\s*(?:감소|감면)|재정수입\s*감소"),
        re.compile(r"(?:수수료|사용료|부담금|과태료|과징금).{0,25}(?:감면|면제|감소)"),
    ),
    "출자출연": (
        re.compile(r"출자금|출연금|정부출자|정부출연|출자\s*소요|출연\s*소요"),
    ),
}

TAG_CATEGORY_MAP = {
    "인건비": "인건비",
    "운영비": "물건비",
    "사업비": "물건비",
    "위탁비": "물건비",
    "지원금": "이전지출",
    "보조금": "이전지출",
    "시설비": "자본지출",
    "자산취득비": "자본지출",
    "세액감면": "조세감면",
    "조세지출": "조세감면",
    "세수감소": "조세감면",
    "재정수입 감소": "세외수입감소",
    "출자금": "출자출연",
    "출연금": "출자출연",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="22대 비용추계서+의안원문 PDF 수집")
    parser.add_argument("--discovery", type=Path, default=DISCOVERY_DEFAULT)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DEFAULT)
    parser.add_argument("--concurrency", type=int, default=12)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--limit", type=int, default=0, help="0이면 전체 후보")
    parser.add_argument("--bill-no", action="append", default=[], help="특정 의안번호만 수집")
    parser.add_argument("--retry-incomplete", action="store_true")
    parser.add_argument("--reindex-only", action="store_true", help="다운로드 없이 분류·목록만 재생성")
    parser.add_argument("--refresh-discovery", action="store_true", help="22대 신규 의안만 공식 사이트에서 추가 확인")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _decoded_name(info: zipfile.ZipInfo) -> str:
    name = info.filename
    try:
        return name.encode("cp437").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return name


def _document_type(name: str) -> str | None:
    flat = re.sub(r"\s+", "", name)
    if not flat.lower().endswith(".pdf"):
        return None
    if "미첨부" in flat:
        return None
    if "비용추계요구서" in flat or "추계요구서" in flat:
        return None
    if "비용추계서" in flat or ("비용추계" in flat and "요구" not in flat):
        return "cost_estimate"
    if "의안원문" in flat:
        return "bill_text"
    return None


def _valid_pdf(data: bytes) -> tuple[bool, str, int]:
    if not data.startswith(b"%PDF"):
        return False, "", 0
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            page_count = len(doc)
            text = "\n".join(page.get_text() for page in doc).strip()
        return page_count > 0, text, page_count
    except Exception:
        return False, "", 0


def _download_zip(bill_id: str, timeout: int) -> bytes:
    body = urllib.parse.urlencode({
        "billId": bill_id,
        "billKindCd": "법률안",
        "dwFileGbn": "B",
    }).encode()
    req = urllib.request.Request(
        ZIP_URL,
        data=body,
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def _extract_pair(zip_bytes: bytes) -> dict[str, dict[str, Any]]:
    found: dict[str, list[dict[str, Any]]] = defaultdict(list)
    try:
        archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        return {}
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = _decoded_name(info)
            doc_type = _document_type(name)
            if not doc_type:
                continue
            data = archive.read(info)
            valid, text, pages = _valid_pdf(data)
            if not valid:
                continue
            found[doc_type].append({
                "original_name": name,
                "data": data,
                "text": text,
                "pages": pages,
                "sha256": hashlib.sha256(data).hexdigest(),
            })

    # 같은 역할의 PDF가 여러 개면 텍스트가 가장 풍부한 문서를 사용한다.
    selected: dict[str, dict[str, Any]] = {}
    for doc_type, docs in found.items():
        selected[doc_type] = max(docs, key=lambda item: (len(item["text"]), item["pages"]))
    return selected


def _load_candidates(path: Path, bill_nos: set[str], limit: int) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    candidates = [
        row for row in data.get("results", [])
        if not row.get("error")
        and row.get("has_cost_estimate")
        and str(row.get("AGE")) == "22"
        and (not bill_nos or str(row.get("BILL_NO")) in bill_nos)
    ]
    candidates.sort(key=lambda row: (str(row.get("PROPOSE_DT") or ""), str(row.get("BILL_NO") or "")))
    if limit:
        candidates = candidates[:limit]
    return candidates


def _refresh_discovery(path: Path, concurrency: int) -> None:
    """기존 전수조사 이후 추가된 의안과 이전 오류 건만 다시 확인한다."""
    from backend.scripts.discover_cost_estimate_bills import (
        fetch_bills_for_age,
        inspect_zip,
    )

    api_key = get_env("OPEN_ASSEMBLY_API_KEY")
    if not api_key:
        raise SystemExit("OPEN_ASSEMBLY_API_KEY가 필요합니다.")
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"results": []}
    old_map = {str(row.get("BILL_ID")): row for row in old.get("results", []) if row.get("BILL_ID")}
    bills = fetch_bills_for_age("22", api_key)
    todo = [
        bill for bill in bills
        if str(bill.get("BILL_ID")) not in old_map
        or old_map[str(bill.get("BILL_ID"))].get("error")
    ]
    print(f"신규·재시도 의안 {len(todo):,}건 확인", flush=True)
    if todo:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(inspect_zip, bill): bill for bill in todo}
            for index, future in enumerate(as_completed(futures), 1):
                result = future.result()
                old_map[str(result.get("BILL_ID"))] = result
                if index % 100 == 0 or index == len(futures):
                    print(f"신규 의안 확인 {index:,}/{len(futures):,}", flush=True)

    # API 응답 순서를 유지하고, 현재 API에 존재하는 의안만 스냅샷에 남긴다.
    ordered = [old_map[str(bill.get("BILL_ID"))] for bill in bills if str(bill.get("BILL_ID")) in old_map]
    successes = sum(1 for row in ordered if not row.get("error"))
    payload = {
        "ages": ["22"],
        "totalChecked": len(ordered),
        "successes": successes,
        "errors": len(ordered) - successes,
        "withCostEstimate": sum(bool(row.get("has_cost_estimate")) for row in ordered),
        "withNonAttachment": sum(bool(row.get("has_non_attachment")) for row in ordered),
        "billTextOnly": sum(
            bool(row.get("has_bill_text"))
            and not (row.get("has_cost_estimate") or row.get("has_non_attachment"))
            for row in ordered
        ),
        "results": ordered,
    }
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)
    print(
        f"갱신 완료: 전체 의안 {len(ordered):,}, 비용추계서 후보 "
        f"{payload['withCostEstimate']:,}, 오류 {payload['errors']:,}",
        flush=True,
    )


def _load_tag_categories() -> dict[str, Counter[str]]:
    output: dict[str, Counter[str]] = defaultdict(Counter)
    for base in (
        GENERATED_DIR / "assembly_rag_seed_22_ce",
        GENERATED_DIR / "assembly_rag_seed_22",
    ):
        structures_path = base / "cost_estimate_structures.jsonl"
        items_path = base / "cost_estimate_items.jsonl"
        if not structures_path.exists() or not items_path.exists():
            continue
        structure_to_bill: dict[str, str] = {}
        bill_id_to_no: dict[str, str] = {}
        for line in structures_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            bill_no = str(row.get("bill_no") or "")
            if bill_no:
                structure_to_bill[str(row.get("struct_id") or "")] = bill_no
                bill_id_to_no[str(row.get("bill_id") or "")] = bill_no
        for line in items_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            struct_id = str(row.get("struct_id") or "")
            bill_no = str(
                row.get("bill_no")
                or structure_to_bill.get(struct_id)
                or bill_id_to_no.get(str(row.get("bill_id") or ""))
                or ""
            )
            if not bill_no:
                continue
            raw = str(row.get("item_category") or "").strip()
            for source, target in TAG_CATEGORY_MAP.items():
                if source in raw:
                    output[bill_no][target] += 3
            item_text = f"{row.get('item_name') or ''} {raw}"
            for category, patterns in CATEGORY_PATTERNS.items():
                if any(pattern.search(item_text) for pattern in patterns):
                    output[bill_no][category] += 2
    return output


def _local_pdf_index(output_dir: Path) -> dict[str, dict[str, Path]]:
    """기존 generated 폴더의 공식 PDF를 의안번호·역할별로 한 번만 색인한다."""
    candidates: dict[str, dict[str, list[Path]]] = defaultdict(lambda: defaultdict(list))
    output_resolved = output_dir.resolve()
    for path in GENERATED_DIR.rglob("*.pdf"):
        try:
            path.resolve().relative_to(output_resolved)
            continue
        except ValueError:
            pass
        match = re.search(r"(?<!\d)(22\d{5})(?!\d)", str(path))
        if not match:
            continue
        doc_type = _document_type(path.name)
        if doc_type:
            candidates[match.group(1)][doc_type].append(path)

    selected: dict[str, dict[str, Path]] = {}
    for bill_no, groups in candidates.items():
        selected[bill_no] = {}
        for doc_type, paths in groups.items():
            # 동일 파일이 여러 실험 폴더에 있으면 가장 큰 PDF를 우선한다.
            selected[bill_no][doc_type] = max(paths, key=lambda path: path.stat().st_size)
    return selected


def _read_local_pair(bill_no: str, local_index: dict[str, dict[str, Path]]) -> dict[str, dict[str, Any]]:
    paths = local_index.get(bill_no, {})
    if not all(kind in paths for kind in ("cost_estimate", "bill_text")):
        return {}
    pair: dict[str, dict[str, Any]] = {}
    for doc_type in ("cost_estimate", "bill_text"):
        path = paths[doc_type]
        try:
            data = path.read_bytes()
        except OSError:
            return {}
        valid, text, pages = _valid_pdf(data)
        if not valid:
            return {}
        pair[doc_type] = {
            "original_name": path.name,
            "data": data,
            "text": text,
            "pages": pages,
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    return pair


def _classify(bill_no: str, text: str, tag_map: dict[str, Counter[str]]) -> tuple[list[str], dict[str, int], str]:
    scores = Counter(tag_map.get(bill_no, {}))
    source = "tag+text" if scores else "text_heuristic"
    compact = re.sub(r"\s+", " ", text)[:250_000]
    for category, patterns in CATEGORY_PATTERNS.items():
        hits = sum(1 for pattern in patterns if pattern.search(compact))
        if hits:
            scores[category] += hits
    categories = [category for category in CATEGORY_DIRS if category != "분류검토" and scores[category] > 0]
    if not categories:
        return ["분류검토"], {}, "unclassified"
    categories.sort(key=lambda category: (-scores[category], list(CATEGORY_DIRS).index(category)))
    return categories, dict(scores), source


def _metadata_path(output_dir: Path, bill_no: str) -> Path:
    return output_dir / "by_bill" / bill_no / "metadata.json"


def _is_complete(output_dir: Path, bill_no: str) -> bool:
    directory = output_dir / "by_bill" / bill_no
    return (
        (directory / "cost_estimate.pdf").is_file()
        and (directory / "bill_text.pdf").is_file()
        and (directory / "metadata.json").is_file()
    )


def _write_bytes_once(path: Path, data: bytes) -> None:
    if path.exists():
        return
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_bytes(data)
    os.replace(temp, path)


def _link_categories(output_dir: Path, bill_no: str, categories: list[str]) -> None:
    target = output_dir / "by_bill" / bill_no
    for category in categories:
        category_dir = output_dir / "by_category" / CATEGORY_DIRS[category]
        category_dir.mkdir(parents=True, exist_ok=True)
        link = category_dir / bill_no
        if link.exists() or link.is_symlink():
            continue
        link.symlink_to(Path("..") / ".." / "by_bill" / bill_no, target_is_directory=True)


def _process(row: dict[str, Any], output_dir: Path, timeout: int,
             tag_map: dict[str, Counter[str]], local_index: dict[str, dict[str, Path]],
             retry_incomplete: bool) -> dict[str, Any]:
    bill_no = str(row.get("BILL_NO") or "")
    bill_id = str(row.get("BILL_ID") or "")
    if not bill_no or not bill_id:
        return {"status": "invalid_metadata", "bill_no": bill_no, "bill_id": bill_id}
    if _is_complete(output_dir, bill_no):
        metadata = json.loads(_metadata_path(output_dir, bill_no).read_text(encoding="utf-8"))
        _link_categories(output_dir, bill_no, metadata.get("categories") or ["분류검토"])
        return {"status": "already_complete", "bill_no": bill_no}

    old_metadata = _metadata_path(output_dir, bill_no)
    if old_metadata.exists() and not retry_incomplete:
        metadata = json.loads(old_metadata.read_text(encoding="utf-8"))
        if metadata.get("status") != "complete":
            return {"status": "already_incomplete", "bill_no": bill_no}

    pair = _read_local_pair(bill_no, local_index)
    reused_local = bool(pair)
    if not pair:
        try:
            pair = _extract_pair(_download_zip(bill_id, timeout))
        except Exception as exc:
            return {"status": "download_error", "bill_no": bill_no, "error": repr(exc)}

    missing = [kind for kind in ("cost_estimate", "bill_text") if kind not in pair]
    directory = output_dir / "by_bill" / bill_no
    directory.mkdir(parents=True, exist_ok=True)
    if missing:
        metadata = {
            "status": "incomplete",
            "missing": missing,
            "bill_id": bill_id,
            "bill_no": bill_no,
            "bill_name": row.get("BILL_NAME"),
            "propose_date": row.get("PROPOSE_DT"),
        }
        old_metadata.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "incomplete", "bill_no": bill_no, "missing": missing}

    cost = pair["cost_estimate"]
    bill = pair["bill_text"]
    categories, scores, classification_source = _classify(bill_no, cost["text"], tag_map)
    _write_bytes_once(directory / "cost_estimate.pdf", cost["data"])
    _write_bytes_once(directory / "bill_text.pdf", bill["data"])
    metadata = {
        "status": "complete",
        "age": 22,
        "bill_id": bill_id,
        "bill_no": bill_no,
        "bill_name": row.get("BILL_NAME"),
        "proposer": row.get("PROPOSER"),
        "propose_date": row.get("PROPOSE_DT"),
        "committee": row.get("COMMITTEE"),
        "process_result": row.get("PROC_RESULT"),
        "categories": categories,
        "primary_category": categories[0],
        "classification_source": classification_source,
        "classification_status": "candidate",
        "category_scores": scores,
        "documents": {
            "cost_estimate": {
                "filename": "cost_estimate.pdf",
                "original_name": cost["original_name"],
                "pages": cost["pages"],
                "sha256": cost["sha256"],
            },
            "bill_text": {
                "filename": "bill_text.pdf",
                "original_name": bill["original_name"],
                "pages": bill["pages"],
                "sha256": bill["sha256"],
            },
        },
    }
    old_metadata.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    _link_categories(output_dir, bill_no, categories)
    return {
        "status": "reused_local" if reused_local else "downloaded",
        "bill_no": bill_no,
        "categories": categories,
    }


def _clear_category_links(output_dir: Path) -> None:
    category_root = output_dir / "by_category"
    if not category_root.exists():
        return
    for path in category_root.glob("*/*"):
        if path.is_symlink():
            path.unlink()


def _rebuild_indexes(output_dir: Path, candidate_count: int, run_counts: Counter[str],
                     tag_map: dict[str, Counter[str]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    category_counts: Counter[str] = Counter()
    _clear_category_links(output_dir)
    for path in sorted((output_dir / "by_bill").glob("*/metadata.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if row.get("status") == "complete":
            cost_path = path.parent / "cost_estimate.pdf"
            try:
                valid, text, _ = _valid_pdf(cost_path.read_bytes())
            except OSError:
                valid, text = False, ""
            if valid:
                categories, scores, source = _classify(str(row.get("bill_no") or ""), text, tag_map)
                row["categories"] = categories
                row["primary_category"] = categories[0]
                row["classification_source"] = source
                row["classification_status"] = "candidate"
                row["category_scores"] = scores
                path.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
            category_counts.update(row.get("categories") or ["분류검토"])
            _link_categories(
                output_dir,
                str(row.get("bill_no") or path.parent.name),
                row.get("categories") or ["분류검토"],
            )
        rows.append(row)
    manifest = output_dir / "manifest.jsonl"
    manifest.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    status_counts = Counter(str(row.get("status") or "unknown") for row in rows)
    summary = {
        "age": 22,
        "candidate_count_this_run": candidate_count,
        "stored_bill_directories": len(rows),
        "complete_pairs": status_counts["complete"],
        "incomplete": status_counts["incomplete"],
        "category_counts_multi_label": dict(category_counts),
        "run_counts": dict(run_counts),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return summary


def main() -> None:
    args = parse_args()
    if args.refresh_discovery:
        _refresh_discovery(args.discovery, args.concurrency)
    candidates = _load_candidates(args.discovery, set(args.bill_no), args.limit)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    already = sum(1 for row in candidates if _is_complete(args.output_dir, str(row.get("BILL_NO") or "")))
    print(f"후보 {len(candidates):,}건 / 이미 완결 {already:,}건 / 신규 확인 {len(candidates)-already:,}건")
    if args.dry_run:
        return

    tag_map = _load_tag_categories()
    if args.reindex_only:
        summary = _rebuild_indexes(args.output_dir, len(candidates), Counter(), tag_map)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    local_index = _local_pdf_index(args.output_dir)
    local_pairs = sum(
        1 for groups in local_index.values()
        if "cost_estimate" in groups and "bill_text" in groups
    )
    print(f"기존 로컬 PDF 쌍 {local_pairs:,}건 재사용 가능")
    run_counts: Counter[str] = Counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {
            pool.submit(
                _process, row, args.output_dir, args.timeout, tag_map, local_index,
                args.retry_incomplete,
            ): row
            for row in candidates
        }
        total = len(futures)
        for index, future in enumerate(as_completed(futures), 1):
            row = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "status": "worker_error",
                    "bill_no": row.get("BILL_NO"),
                    "error": repr(exc),
                }
            run_counts[result["status"]] += 1
            if result["status"] in {"download_error", "worker_error"}:
                print(f"ERROR {result.get('bill_no')}: {result.get('error')}")
            if index % 50 == 0 or index == total:
                print(f"진행 {index:,}/{total:,} {dict(run_counts)}", flush=True)

    summary = _rebuild_indexes(args.output_dir, len(candidates), run_counts, tag_map)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
