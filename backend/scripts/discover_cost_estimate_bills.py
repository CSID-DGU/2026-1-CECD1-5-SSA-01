"""discover_cost_estimate_bills.py

빠른 디스커버리 모드 — ZIP 다운로드만 해서 첨부파일 종류만 확인.

목적:
  국회 의안 전체에서 "비용추계서" 또는 "미첨부사유서" 가
  실제로 첨부된 의안만 골라내서 리스트 저장.

이 리스트가 다음 단계 본 파이프라인의 입력이 된다.

사용법:
    python -m backend.scripts.discover_cost_estimate_bills --age 22
    python -m backend.scripts.discover_cost_estimate_bills --age 21 --age 22
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import GENERATED_DIR, get_env

API_URL = "https://open.assembly.go.kr/portal/openapi/nzmimeepazxkubdpn"
ZIP_URL = "http://likms.assembly.go.kr/bill/bi/bill/detail/downloadDtlZip.do"
UA = "Mozilla/5.0"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="추계서 있는 의안만 골라내는 디스커버리")
    p.add_argument("--age", action="append", required=True,
                   help="국회 대수. 여러 번 지정 가능: --age 22 --age 21")
    p.add_argument("--max-bills", type=int, default=0,
                   help="대수별 최대 의안 수 (0 = 전체)")
    p.add_argument("--concurrency", type=int, default=12)
    p.add_argument("--output", type=Path,
                   default=GENERATED_DIR / "cost_estimate_discovery.json")
    return p.parse_args()


def _api_get(url: str, retries: int = 3, timeout: int = 30) -> Any:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def fetch_total_count(age: str, api_key: str) -> int:
    q = {"KEY": api_key, "Type": "json", "pIndex": "1", "pSize": "1", "AGE": age}
    data = _api_get(API_URL + "?" + urllib.parse.urlencode(q))
    for it in data.get("nzmimeepazxkubdpn", []):
        if "head" in it:
            for h in it["head"]:
                if "list_total_count" in h:
                    return int(h["list_total_count"])
    return 0


def fetch_bills_for_age(age: str, api_key: str, max_n: int = 0) -> list[dict]:
    total = fetch_total_count(age, api_key)
    if max_n:
        total = min(total, max_n)
    print(f"  AGE {age}: 총 {total}건 메타 수집...", flush=True)
    bills: list[dict] = []
    per_page = 100
    pages = (total + per_page - 1) // per_page
    for page in range(1, pages + 1):
        q = {"KEY": api_key, "Type": "json",
             "pIndex": str(page), "pSize": str(per_page), "AGE": age}
        data = _api_get(API_URL + "?" + urllib.parse.urlencode(q))
        for it in data.get("nzmimeepazxkubdpn", []):
            if "row" in it:
                bills.extend(it["row"])
        print(f"  메타 수집: {min(len(bills), total)}/{total}건 (페이지 {page}/{pages})", flush=True)
        if len(bills) >= total:
            break
    return bills[:total]


LIKMS_BASE   = "http://likms.assembly.go.kr/bill"
LIKMS_DETAIL = LIKMS_BASE + "/billDetail.do"
LIKMS_AJAX   = LIKMS_BASE + "/bi/bill/detail/billInfo.do"

import html as _html
import re as _re

def _scrape_doc_names(bill_id: str) -> list[str]:
    """LIKMS 상세 HTML → AJAX 한 번 → 첨부 파일명 목록 반환 (ZIP 다운로드 없음)."""
    detail_url = f"{LIKMS_DETAIL}?billId={bill_id}"
    req = urllib.request.Request(detail_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        detail_html = r.read().decode("utf-8", errors="replace")

    # hidden input 추출
    form: dict[str, str] = {}
    for m in _re.finditer(r"<input\b([^>]*)>", detail_html, _re.IGNORECASE):
        attrs: dict[str, str] = {}
        for a in _re.finditer(
            r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))""",
            m.group(1), _re.IGNORECASE
        ):
            attrs[a.group(1).lower()] = _html.unescape(a.group(2) or a.group(3) or a.group(4) or "")
        name = attrs.get("name") or attrs.get("id")
        if name:
            form[name] = attrs.get("value", "")
    form.setdefault("billId", bill_id)
    form.setdefault("billKindCd", "법률안")

    body = urllib.parse.urlencode(form).encode()
    req2 = urllib.request.Request(
        LIKMS_AJAX, data=body,
        headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req2, timeout=15) as r:
        frag = r.read().decode("utf-8", errors="replace")

    # <span> 텍스트 + <a title=...> 에서 파일명 추출
    names: list[str] = []
    for m in _re.finditer(r"<span[^>]*>(.*?)</span>", frag, _re.IGNORECASE | _re.DOTALL):
        t = _re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if t: names.append(t)
    for m in _re.finditer(r'title=["\']([^"\']+)["\']', frag, _re.IGNORECASE):
        names.append(_html.unescape(m.group(1)))
    return names


def inspect_zip(bill: dict) -> dict:
    """HTML 스크래핑으로 첨부 파일명 확인 (ZIP 다운로드 없음 → 빠름)."""
    base = {
        "BILL_ID":    bill["BILL_ID"],
        "BILL_NO":    bill.get("BILL_NO"),
        "BILL_NAME":  bill.get("BILL_NAME"),
        "AGE":        bill.get("AGE"),
        "PROPOSER":   bill.get("PROPOSER"),
        "PROPOSE_DT": bill.get("PROPOSE_DT"),
        "COMMITTEE":  bill.get("COMMITTEE"),
        "PROC_RESULT": bill.get("PROC_RESULT"),
    }
    try:
        names = _scrape_doc_names(bill["BILL_ID"])
        has_ce = has_na = has_bt = False
        for name in names:
            flat = name.replace(" ", "")
            if "미첨부" in flat: has_na = True
            elif "비용추계" in flat or "추계서" in flat: has_ce = True
            elif "의안원문" in flat: has_bt = True
        return {**base,
                "has_cost_estimate": has_ce,
                "has_non_attachment": has_na,
                "has_bill_text": has_bt}
    except Exception as e:
        return {**base, "error": type(e).__name__}


def main() -> None:
    args = parse_args()
    api_key = get_env("OPEN_ASSEMBLY_API_KEY")
    if not api_key:
        raise SystemExit("OPEN_ASSEMBLY_API_KEY 가 .env에 필요합니다.")

    print(f"[1] 의안 메타데이터 수집 (대수: {', '.join(args.age)})")
    all_bills: list[dict] = []
    for age in args.age:
        bills = fetch_bills_for_age(age, api_key, args.max_bills)
        all_bills.extend(bills)
        print(f"     AGE {age}: {len(bills)}건")
    print(f"   합계: {len(all_bills)}건")
    print()

    print(f"[2] ZIP 검사 (concurrency={args.concurrency})...")
    t0 = time.time()
    results: list[dict] = []
    successes = errors = ce_cnt = na_cnt = bt_only = 0

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futs = {pool.submit(inspect_zip, b): b for b in all_bills}
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            results.append(r)
            if r.get("error"):
                errors += 1
            else:
                successes += 1
                if r["has_cost_estimate"]:  ce_cnt += 1
                if r["has_non_attachment"]: na_cnt += 1
                if r["has_bill_text"] and not (r["has_cost_estimate"] or r["has_non_attachment"]):
                    bt_only += 1
            if i % 100 == 0:
                rate = i / (time.time() - t0)
                eta = (len(all_bills) - i) / rate
                print(f"   {i}/{len(all_bills)}  "
                      f"💰{ce_cnt}  📋{na_cnt}  err{errors}  "
                      f"({rate:.1f}건/s, ETA {eta/60:.1f}분)")

    elapsed = time.time() - t0
    print()
    print(f"=== 디스커버리 완료 ({elapsed/60:.1f}분) ===")
    print(f"  처리:        {successes}/{len(all_bills)}")
    print(f"  실패:        {errors}")
    print(f"  💰 추계서:    {ce_cnt}건")
    print(f"  📋 미첨부:    {na_cnt}건")
    print(f"  의안원문만:   {bt_only}건")
    print()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "ages":            args.age,
        "totalChecked":    len(all_bills),
        "successes":       successes,
        "errors":          errors,
        "withCostEstimate":  ce_cnt,
        "withNonAttachment": na_cnt,
        "billTextOnly":      bt_only,
        "elapsedMinutes":  round(elapsed/60, 1),
        "results":         results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {args.output}")


if __name__ == "__main__":
    main()
