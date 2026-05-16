from __future__ import annotations

import argparse
import getpass
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import GENERATED_DIR, get_env


OPEN_ASSEMBLY_API_URL = "https://open.assembly.go.kr/portal/openapi/nzmimeepazxkubdpn"
LIKMS_BASE_URL = "http://likms.assembly.go.kr/bill"
LIKMS_AJAX_URL = f"{LIKMS_BASE_URL}/bi/bill/detail/billInfo.do"
LIKMS_ZIP_URL = f"{LIKMS_BASE_URL}/bi/bill/detail/downloadDtlZip.do"
USER_AGENT = "Mozilla/5.0 cost-estimation-system/0.1"

COST_KEYWORDS = (
    "비용추계",
    "비용 추계",
    "추계서",
    "재정수반",
    "예산조치",
    "미첨부",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect cost-estimate document links from Open Assembly bills."
    )
    parser.add_argument("--age", default="21", help="National Assembly term, e.g. 21.")
    parser.add_argument("--page", type=int, default=1, help="Start page.")
    parser.add_argument("--pages", type=int, default=1, help="Number of pages to fetch.")
    parser.add_argument("--size", type=int, default=10, help="Rows per page.")
    parser.add_argument("--max-bills", type=int, default=10, help="Maximum bills to inspect.")
    parser.add_argument("--sleep", type=float, default=0.2, help="Delay between bills.")
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download matched cost-estimate HWP/PDF files.",
    )
    parser.add_argument(
        "--zip-fallback",
        action="store_true",
        help="Download and inspect LIKMS detail ZIP when direct cost links are not found.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=GENERATED_DIR / "open_assembly_cost_docs",
        help="Directory for JSON index and downloaded files.",
    )
    return parser.parse_args()


def get_api_key() -> str:
    key = get_env("OPEN_ASSEMBLY_API_KEY")
    if key:
        return key

    entered = getpass.getpass("OPEN_ASSEMBLY_API_KEY: ").strip()
    if not entered:
        raise SystemExit("OPEN_ASSEMBLY_API_KEY is required.")
    return entered


def request_bytes(
    url: str,
    *,
    data: dict[str, str] | None = None,
    timeout: int = 30,
) -> bytes:
    encoded_data = None
    headers = {
        "Accept": "*/*",
        "User-Agent": USER_AGENT,
    }
    if data is not None:
        encoded_data = urllib.parse.urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    request = urllib.request.Request(url, data=encoded_data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def request_text(url: str, *, data: dict[str, str] | None = None) -> str:
    body = request_bytes(url, data=data)
    return body.decode("utf-8", errors="replace")


def fetch_bill_rows(api_key: str, args: argparse.Namespace) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(args.page, args.page + args.pages):
        query = {
            "KEY": api_key,
            "Type": "json",
            "pIndex": str(page),
            "pSize": str(args.size),
            "AGE": args.age,
        }
        url = f"{OPEN_ASSEMBLY_API_URL}?{urllib.parse.urlencode(query)}"
        payload = json.loads(request_text(url))
        root = payload.get("nzmimeepazxkubdpn", [])
        for item in root:
            if "row" in item:
                rows.extend(item["row"])

        if len(rows) >= args.max_bills:
            break

    return rows[: args.max_bills]


def extract_hidden_inputs(detail_html: str) -> dict[str, str]:
    inputs: dict[str, str] = {}
    for attrs_text in re.findall(r"<input\b([^>]*)>", detail_html, flags=re.IGNORECASE):
        attrs = parse_attrs(attrs_text)
        name = attrs.get("name") or attrs.get("id")
        if not name:
            continue
        inputs[name] = html.unescape(attrs.get("value", ""))
    return inputs


def parse_attrs(attrs_text: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    attr_re = re.compile(
        r"""([:\w-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))""",
        flags=re.IGNORECASE,
    )
    for match in attr_re.finditer(attrs_text):
        attrs[match.group(1).lower()] = html.unescape(
            match.group(2) or match.group(3) or match.group(4) or ""
        )
    return attrs


def clean_html(fragment: str) -> str:
    text = re.sub(r"<script\b.*?</script>", " ", fragment, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_file_url(raw_href: str) -> str | None:
    href = html.unescape(raw_href).strip()
    if not href or href == "javascript:;":
        return None

    script_match = re.search(r"goDownload\(['\"]([^'\"]+)['\"]\)", href)
    if script_match:
        href = script_match.group(1)

    if "FileGate" not in href:
        return None

    return urllib.parse.urljoin(LIKMS_BASE_URL, href)


def extract_report_docs(fragment_html: str) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    report_blocks = re.findall(
        r"<div\s+class=[\"']report[\"'][^>]*>(.*?)</div>",
        fragment_html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    for block in report_blocks:
        block_text = clean_html(block)
        span_match = re.search(r"<span[^>]*>(.*?)</span>", block, flags=re.IGNORECASE | re.DOTALL)
        document_name = clean_html(span_match.group(1)) if span_match else block_text
        for anchor_match in re.finditer(
            r"<a\b([^>]*)>(.*?)</a>",
            block,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            attrs = parse_attrs(anchor_match.group(1))
            url = normalize_file_url(attrs.get("href", ""))
            if not url:
                continue

            anchor_text = clean_html(anchor_match.group(2))
            title = attrs.get("title", "")
            link_class = attrs.get("class", "")
            label = " ".join(part for part in [document_name, title, anchor_text] if part)
            file_type = detect_file_type(url, link_class, title, anchor_text)
            docs.append(
                {
                    "documentName": document_name,
                    "label": label,
                    "fileType": file_type,
                    "url": url,
                    "isCostRelated": is_cost_related(label),
                }
            )
    return dedupe_docs(docs)


def detect_file_type(url: str, link_class: str, title: str, text: str) -> str:
    haystack = f"{url} {link_class} {title} {text}".lower()
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    if query.get("type") == ["0"] or "icon_hwp" in haystack or "hwp" in haystack:
        return "hwp"
    if query.get("type") == ["1"] or "icon_pdf" in haystack or "pdf" in haystack:
        return "pdf"
    return "unknown"


def is_cost_related(text: str) -> bool:
    normalized = text.replace(" ", "")
    return any(keyword.replace(" ", "") in normalized for keyword in COST_KEYWORDS)


def dedupe_docs(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for doc in docs:
        key = (doc["url"], doc["label"])
        if key in seen:
            continue
        seen.add(key)
        result.append(doc)
    return result


def extract_memo(detail_html: str, fragment_html: str) -> str:
    memos: list[str] = []
    for source in (detail_html, fragment_html):
        for pattern in (
            r'id=["\']headMemoInfo["\'][^>]*value=["\']([^"\']*)',
            r'<pre\s+class=["\']bill_memo["\'][^>]*>(.*?)</pre>',
        ):
            for match in re.finditer(pattern, source, flags=re.IGNORECASE | re.DOTALL):
                value = clean_html(match.group(1))
                if value:
                    memos.append(value)
    return " / ".join(dict.fromkeys(memos))


def inspect_zip(bill: dict[str, Any], output_dir: Path) -> dict[str, Any] | None:
    bill_id = str(bill.get("BILL_ID", ""))
    bill_kind = str(bill.get("BILL_KIND_CD") or "법률안")
    if not bill_id:
        return None

    zip_dir = output_dir / "zips"
    zip_dir.mkdir(parents=True, exist_ok=True)
    zip_path = zip_dir / f"{safe_filename(bill.get('BILL_NO') or bill_id)}.zip"
    body = request_bytes(
        LIKMS_ZIP_URL,
        data={"billId": bill_id, "billKindCd": bill_kind, "dwFileGbn": "B"},
        timeout=60,
    )
    zip_path.write_bytes(body)

    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
    except zipfile.BadZipFile:
        return {
            "path": str(zip_path),
            "isZip": False,
            "costRelatedFiles": [],
        }

    cost_names = [name for name in names if is_cost_related(name)]
    return {
        "path": str(zip_path),
        "isZip": True,
        "fileCount": len(names),
        "costRelatedFiles": cost_names,
    }


def download_docs(bill: dict[str, Any], docs: list[dict[str, Any]], output_dir: Path) -> None:
    bill_no = safe_filename(bill.get("BILL_NO") or bill.get("BILL_ID") or "bill")
    bill_dir = output_dir / "files" / bill_no
    bill_dir.mkdir(parents=True, exist_ok=True)

    for index, doc in enumerate(docs, start=1):
        suffix = doc["fileType"] if doc["fileType"] != "unknown" else "bin"
        name = safe_filename(doc["documentName"] or doc["label"] or f"document_{index}")
        path = bill_dir / f"{index:02d}_{name}.{suffix}"
        path.write_bytes(request_bytes(doc["url"], timeout=60))
        doc["downloadedTo"] = str(path)


def safe_filename(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[\\/:*?\"<>|]+", "_", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:120] or "untitled"


def collect_for_bill(bill: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    detail_url = str(bill.get("DETAIL_LINK") or "")
    detail_html = request_text(detail_url)
    form = extract_hidden_inputs(detail_html)
    form.setdefault("billId", str(bill.get("BILL_ID", "")))
    form.setdefault("billNo", str(bill.get("BILL_NO", "")))
    form.setdefault("billKindCd", "법률안")

    fragment_html = request_text(LIKMS_AJAX_URL, data=form)
    docs = extract_report_docs(fragment_html)
    cost_docs = [doc for doc in docs if doc["isCostRelated"]]
    memo = extract_memo(detail_html, fragment_html)

    zip_info = None
    if args.zip_fallback and not cost_docs and is_cost_related(memo):
        zip_info = inspect_zip(bill, args.output_dir)

    if args.download and cost_docs:
        download_docs(bill, cost_docs, args.output_dir)

    return {
        "billId": bill.get("BILL_ID"),
        "billNo": bill.get("BILL_NO"),
        "billName": bill.get("BILL_NAME"),
        "proposer": bill.get("PROPOSER"),
        "proposeDate": bill.get("PROPOSE_DT"),
        "committee": bill.get("COMMITTEE"),
        "processResult": bill.get("PROC_RESULT"),
        "detailLink": detail_url,
        "memo": memo,
        "allDocumentCount": len(docs),
        "costDocumentCount": len(cost_docs),
        "costDocuments": cost_docs,
        "zipFallback": zip_info,
    }


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    api_key = get_api_key()
    bills = fetch_bill_rows(api_key, args)

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for index, bill in enumerate(bills, start=1):
        try:
            result = collect_for_bill(bill, args)
            results.append(result)
            print(
                f"[{index}/{len(bills)}] {result['billNo']} "
                f"costDocs={result['costDocumentCount']} memo={bool(result['memo'])}"
            )
        except Exception as exc:  # noqa: BLE001 - collector should continue on bad bills.
            errors.append(
                {
                    "billId": str(bill.get("BILL_ID", "")),
                    "billNo": str(bill.get("BILL_NO", "")),
                    "error": repr(exc),
                }
            )
            print(f"[{index}/{len(bills)}] ERROR {bill.get('BILL_NO')}: {exc}", file=sys.stderr)
        time.sleep(args.sleep)

    payload = {
        "age": args.age,
        "inspectedBills": len(bills),
        "matchedBills": sum(1 for item in results if item["costDocumentCount"] > 0),
        "memoOnlyBills": sum(
            1
            for item in results
            if item["costDocumentCount"] == 0 and is_cost_related(item.get("memo", ""))
        ),
        "results": results,
        "errors": errors,
    }
    index_path = args.output_dir / "cost_docs_index.json"
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("inspectedBills", "matchedBills", "memoOnlyBills")}, ensure_ascii=False))
    print(f"saved: {index_path}")


if __name__ == "__main__":
    main()
