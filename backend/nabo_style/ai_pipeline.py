"""Upload a bill PDF → GPT reads it → code verifies → ledger fills numbers → support_payment computes.

Division of labour (the point of the design):
- GPT decides what the law says: which clauses create cost, who is paid, how much,
  for which years, and which ledger row best fits each variable.
- Code never trusts those answers blindly: every quote must be found in the operative
  bill text, every amount must literally appear in its quoted clause, every ledger row
  must be public on/before the proposal date and must not come from this bill's own
  estimate. GPT never writes a number that is not in the bill or in the ledger.
- The arithmetic is done by support_payment.estimate, not by the model.

  python3 -m backend.nabo_style.ai_pipeline 2211090      # run on a local bill
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Callable
from urllib import error, request

import fitz

from backend.nabo_style import ledger
from backend.nabo_style.support_payment import BILLS, UNIT_SCALE, _bill_text, estimate

MODEL = os.getenv("NABO_AI_MODEL", "gpt-6.1-sol")
EFFORT = os.getenv("NABO_AI_EFFORT", "medium")
ENV = Path(__file__).resolve().parents[1] / ".env"
EXTRACTED = Path(__file__).resolve().parents[1] / "generated/nabo_style/support/extracted"
ANSWERS = Path(__file__).resolve().parents[2] / "docs/nabo_style/ai_answers.json"
PEOPLE_UNITS = ("명", "인", "person", "가구", "세대", "호", "개소")

Log = Callable[[str, str, str, dict | None], None]


# ---------------------------------------------------------------- GPT

def _api_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key and ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENAI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise RuntimeError("OPENAI_API_KEY가 없습니다 (backend/.env).")
    return key


def gpt(name: str, instruction: str, schema: dict, *, web: bool = False) -> tuple[dict, dict]:
    body = {"model": MODEL, "reasoning": {"effort": EFFORT}, "input": instruction,
            "text": {"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}}}
    if web:
        body["tools"] = [{"type": "web_search"}]
    req = request.Request("https://api.openai.com/v1/responses",
                          data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                          headers={"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"})
    for attempt in range(2):  # long reasoning calls occasionally time out; one retry
        try:
            with request.urlopen(req, timeout=600) as res:
                data = json.load(res)
            break
        except error.HTTPError as exc:
            raise RuntimeError(f"GPT API 오류 {exc.code}: {exc.read()[:300].decode('utf-8', 'replace')}") from exc
        except (TimeoutError, error.URLError) as exc:
            if attempt:
                raise RuntimeError(f"GPT 응답 지연으로 실패했어요({type(exc).__name__}). 다시 실행해 주세요.") from exc
    text = "".join(p.get("text", "") for o in data.get("output", []) if o.get("type") == "message"
                   for p in o.get("content", []) if p.get("type") == "output_text")
    searches = [o.get("action", {}).get("query") for o in data.get("output", []) if o.get("type") == "web_search_call"]
    return json.loads(text), dict(model=data.get("model"), usage=data.get("usage", {}), searches=searches)


def _obj(props: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "properties": props, "required": list(props)}


S, I, N, B = {"type": "string"}, {"type": "integer"}, {"type": "number"}, {"type": "boolean"}
ARR = lambda item: {"type": "array", "items": item}  # noqa: E731

READ_SCHEMA = _obj({
    "bill_title": S,
    "is_cash_support": B,
    "not_supported_reason": S,
    "summary": S,
    "clauses": ARR(_obj({"id": S, "quote": S, "role": {"type": "string", "enum": [
        "지급대상", "지급액", "제외대상", "추가대상", "재원분담", "지급기간", "시행일", "기타"]}})),
    "groups": ARR(_obj({
        "name": S, "sign": {"type": "integer", "enum": [1, -1]}, "who": S,
        "amount_min_won": I, "amount_max_won": I, "amount_clause_id": S,
        "times_per_year": I, "only_years": ARR(I),
        "search_queries": ARR(S), "needs_rate": B, "rate_queries": ARR(S), "why": S})),
    "payment_years": ARR(I),
    "payment_years_why": S,
    "split": _obj({"in_bill": B, "national_ratio": N, "clause_id": S, "search_queries": ARR(S), "why": S}),
    "not_estimated": ARR(_obj({"item": S, "reason": S})),
})

def _named(schema: dict, names: list[str]) -> dict:
    """Pin the 'name' field of each group to the exact group names so answers map back 1:1."""
    out = json.loads(json.dumps(schema))
    out["properties"]["groups"]["items"]["properties"]["name"] = {"type": "string", "enum": names}
    return out


WEB_SCHEMA = _obj({"groups": ARR(_obj({
    "name": S, "found": B, "value": N, "unit": S, "url": S, "quote": S, "publisher": S, "document": S,
    "as_of": S, "published_at": S, "why": S, "caveat": S}))})

PICK_SCHEMA = _obj({
    "groups": ARR(_obj({"name": S, "ledger_id": S, "why": S, "caveat": S, "rate_ledger_id": S, "rate_why": S})),
    "split": _obj({"ledger_id": S, "national_ratio": N, "why": S}),
})


# ---------------------------------------------------------------- bill text

def bill_pages(pdf: bytes) -> list[str]:
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        return [p.get_text() for p in doc]


def bill_identity(pages: list[str]) -> dict:
    flat = re.sub(r"\s+", "", "".join(pages))
    no = re.search(r"의안번호(\d{1,7})", flat)
    no = no.group(1) if no else ""
    if no and len(no) <= 5:
        no = "22" + no.zfill(5)  # 22대 국회 의안은 앞자리 '22'와 0이 생략되어 인쇄됨
    when = re.search(r"발의연월일:?(\d{4})\.(\d{1,2})\.(\d{1,2})", flat)
    proposed = date(*map(int, when.groups())).isoformat() if when else ""
    meta = BILLS / no / "metadata.json"
    meta = json.loads(meta.read_text(encoding="utf-8")) if no and meta.exists() else {}
    return dict(bill_no=no, propose_date=proposed or meta.get("propose_date", ""),
                proposer=meta.get("proposer", ""), committee=meta.get("committee", ""),
                title=meta.get("bill_name", ""))


def _won_values(quote: str) -> set[int]:
    """Every money amount literally written in a clause: 25만원, 1인당 300,000원, 연 360만원 …"""
    out = set()
    for num, unit in re.findall(r"(\d[\d,]*(?:\.\d+)?)\s*(억|천만|백만|만|천)?\s*원", quote):
        out.add(round(float(num.replace(",", "")) * {"억": 1e8, "천만": 1e7, "백만": 1e6, "만": 1e4,
                                                     "천": 1e3}.get(unit, 1)))
    return out


def _ratio_in(text: str, ratio: float) -> bool:
    flat = re.sub(r"\s+", "", text)
    if ratio == 1 and ("전액" in flat or "100분의100" in flat):
        return True
    pct = round(ratio * 100, 2)
    hits = [float(x) for x in re.findall(r"100분의(\d+(?:\.\d+)?)", flat)]
    hits += [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)%", flat)]
    hits += [float(x) * 100 for x in re.findall(r"(?<![\d.])(0\.\d+)(?![\d])", flat)]
    return any(abs(h - pct) < 0.01 for h in hits)


# ---------------------------------------------------------------- ledger

@lru_cache(maxsize=1)
def _rows() -> tuple[dict, ...]:
    return tuple(ledger.all_rows())


def _row(rid: str) -> dict | None:
    return next((r for r in _rows() if r["id"] == rid), None)


def candidates(queries: list[str], cutoff: str, bill_no: str, limit: int = 14) -> list[dict]:
    seen, out = set(), []
    for q in queries:
        terms = q.split()
        for r in _rows():
            if r["id"] in seen or r["published_at"] > cutoff or r.get("source_bill") == bill_no:
                continue
            if r["id"].startswith("erce:salary:"):
                continue
            hay = f"{r['id']} {r['name']} {r['document']} {r.get('note', '')}"
            if all(t in hay for t in terms):
                seen.add(r["id"])
                out.append(r)
    official = ("공식", "법령", "통계")
    # official sources first, newest first inside each bucket
    out.sort(key=lambda r: r["published_at"], reverse=True)
    out.sort(key=lambda r: not any(w in (r.get("grade") or "") for w in official))
    return out[:limit]


def _brief(r: dict) -> dict:
    from backend.nabo_style.display import as_of_ko, by_year, clean_name, unit_ko
    v = by_year(r)
    if isinstance(v, dict):
        v = dict(list(v.items())[:6])
    as_of = r.get("as_of") or r.get("reference_year")
    return dict(id=r["id"], name=r["name"][:80], label=clean_name(r["name"]), value=v, unit=r.get("unit"),
                unit_ko=unit_ko(r.get("unit")), as_of=as_of, as_of_ko=as_of_ko(as_of),
                publisher=r.get("publisher") or "", source=f"{r.get('publisher', '')} {r['document']}"[:90],
                published_at=r["published_at"], grade=r.get("grade"), note=(r.get("note") or "")[:90])


def _usable_people(r: dict) -> str:
    v = r["value"]
    nums = list(v.values()) if isinstance(v, dict) else [v]
    if not nums or not all(isinstance(x, (int, float)) for x in nums):
        return "값이 숫자가 아님"
    unit = r.get("unit") or ""
    if "원" in unit or "%" in unit:
        return f"인원 단위가 아님({unit})"
    if unit and not any(u in unit for u in PEOPLE_UNITS):
        return f"인원 단위가 아님({unit})"
    return ""


# ---------------------------------------------------------------- pipeline

READ_PROMPT = """당신은 국회예산정책처(NABO) 비용추계 담당자입니다. 아래 의안 원문을 읽고 현금 지원금(수당·지원금·기본소득 등 사람에게 정액 지급) 비용추계 설계를 JSON으로 작성하세요.

규칙
- 제안이유가 아니라 '법률 제 호' 이후의 개정 조문(본문·부칙)을 근거로 합니다.
- clauses.quote는 원문에서 글자 그대로 복사하되, 읽기 좋게 띄어쓰기만 넣으세요(검증은 공백을 무시합니다). 요약·의역 금지. 20~120자.
- clauses.id는 '제5조①', '제3조②2호', '부칙 제1조'처럼 씁니다.
- groups는 '대상자 수 × 1인당 지급액'으로 계산되는 대상 그룹입니다. 제외 대상은 sign=-1, 추가 대상은 sign=1.
  · 그룹끼리 겹치면 안 됩니다. 하위 자격(예: 결혼이민자, 난민)이 더 큰 통계 집단(예: 장기체류 외국인)에 이미 포함되면 별도 그룹을 만들지 말고 큰 그룹의 why에 포함 사실을 적으세요.
  · 공식 통계로 셀 수 없을 만큼 작거나 측정 불가능한 그룹은 groups가 아니라 not_estimated에 넣으세요.
  · amount_min_won/max_won은 지급액 조문에 적힌 금액(원)입니다. 범위면 하한·상한, 정액이면 같은 값.
  · 월 지급이면 amount는 월액, times_per_year=12. 1회성이면 1. 연액이면 1.
  · only_years: 특정 연도에만 지급되는 그룹이면 그 연도들, 아니면 빈 배열.
  · search_queries: 기준정보 원장에서 이 그룹의 인원을 찾을 짧은 검색어 3~6개(공백으로 구분된 단어는 모두 포함되어야 검색됨). 예: "주민등록인구", "65세 이상 인구", "농가인구", "장기체류 외국인", "독립유공자".
  · needs_rate: NABO가 보통 지급률·수급률을 곱하는 사업(신청주의 수당 등)이면 true, 그리고 rate_queries 작성.
- payment_years: 1회성이면 그 해. 매년 지급이면 시행일(부칙)이 속한 해부터 5년(NABO 관행). 시행일이 공포 후 n개월이면 발의일 기준으로 판단해 이유를 적으세요.
- split: 국가·지자체 분담이 조문에 비율로 있으면 in_bill=true와 national_ratio(0~1), clause_id. 없으면 in_bill=false, national_ratio=0, 선례 검색어(search_queries: 예 "국고보조율", "분담")를 쓰세요.
- not_estimated: 비용이 생기지만 이번 추계에서 다루지 않는 항목(위원회 운영, 실태조사, 행정비용, 하위법령 위임으로 규모를 알 수 없는 것 등)과 이유.
- 현금 지원금 법안이 아니면 is_cash_support=false와 이유를 쓰고 groups는 빈 배열.
- 숫자를 만들어내지 마세요. 인원 수는 쓰지 않습니다(원장에서 찾음).
- summary는 이 법안이 무엇을 하는지 2문장.

의안번호: {bill_no} / 발의일: {cutoff}
=== 의안 원문 ===
{text}"""

PICK_PROMPT = """당신은 NABO 비용추계 담당자입니다. 각 대상 그룹의 인원(또는 지급률)으로 쓸 기준정보 원장 행을 후보 중에서 하나 고르세요.

규칙
- 반드시 아래 후보 id 중에서만 고릅니다. 맞는 행이 없으면 ledger_id=""로 두고 why에 무엇이 부족한지 쓰세요. 숫자를 만들지 마세요.
- 대상 범위가 조문과 같은지(연령·자격·지역), 기준시점이 발의일에 가장 가까운지, 단위가 인원인지 확인하세요.
- NABO도 완벽히 일치하는 통계가 없으면 가장 가까운 공식 자료를 근사치로 쓰고 한계를 밝힙니다. 범위·시점이 다소 어긋나도 같은 집단을 가리키는 가장 가까운 행을 고르고 caveat에 한계를 적으세요. 전혀 다른 집단만 있을 때만 비워 두세요.
- 단, 후보가 조문 집단의 일부(예: 특정 사업의 연차별 지급인원, 한 지역, 한 연령대)만 가리키면 고르지 말고 비워 두세요. 비운 그룹은 다음 단계에서 웹 검색으로 공식 통계를 찾습니다.
- 차감 그룹(sign -1)은 기본 그룹보다 작아야 합니다.
- 연도별 값(dict)은 추계연도를 덮는 것을 선호하세요.
- caveat: 범위가 정확히 맞지 않거나 오래된 값이면 그 한계를 한 문장으로.
- split: 조문에 분담비율이 없을 때만 선례 행을 고르고, 그 행의 값/인용에 적힌 국고 비율을 national_ratio(0~1)로 씁니다. 적절한 행이 없으면 ledger_id="" 와 national_ratio=0.

발의일: {cutoff}
지급연도: {years}
=== 그룹과 후보 ===
{groups}
=== 분담비율 후보 ===
{split}"""


WEB_PROMPT = """당신은 NABO 비용추계 담당자입니다. 기준정보 원장에 아래 그룹의 인원 자료가 없습니다. 웹 검색으로 공식 통계를 찾아 주세요.

규칙
- 발의일 {cutoff} 이전에 공표된 자료만 씁니다(published_at은 YYYY-MM-DD, 공표일을 모르면 found=false).
- 통계청(KOSIS)·정부부처·공공기관 보도자료/통계표를 우선합니다. 언론보도는 최후 수단이며 caveat에 적으세요.
- 개인에게 지급하는 돈이면 반드시 사람 수(명)를 찾으세요. 가구 수·농가 수·경영주 수는 사람 수가 아닙니다.
- 행정 등록자료(예: 농어업경영체 등록정보, 수급자 현황)가 조문 대상에 더 가까우면 표본조사보다 우선합니다.
- value는 사람 수 그대로, unit은 '명' '천명' 등 원문 단위. 범위가 조문과 다르면 가장 가까운 집단을 쓰고 caveat에 한계를 적으세요.
- url은 값이 실제로 적힌 페이지/PDF 주소, quote는 그 페이지에 적힌 숫자를 포함한 원문 문장(그대로 복사).
- 찾지 못하면 found=false, value=0.

발의일: {cutoff}
=== 그룹 ===
{groups}"""


def _fetch_text(url: str) -> str:
    req = request.Request(url, headers={"User-Agent": "Mozilla/5.0 (cost-estimate verifier)"})
    with request.urlopen(req, timeout=25) as res:
        data, ctype = res.read(8_000_000), res.headers.get("Content-Type", "")
    if data[:4] == b"%PDF" or "pdf" in ctype:
        with fitz.open(stream=data, filetype="pdf") as doc:
            return "".join(p.get_text() for p in doc)
    html = data.decode(res.headers.get_content_charset() or "utf-8", "replace")
    return re.sub(r"<[^>]+>", " ", re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", html))


def _official_url(url: str) -> bool:
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
    return host.endswith((".go.kr", "kosis.kr", ".re.kr", ".or.kr", "nabo.go.kr", "law.go.kr"))


def _number_on_page(page: str, value: float) -> bool:
    for token in re.findall(r"\d[\d,]*(?:\.\d+)?", page):
        try:
            if abs(float(token.replace(",", "")) - value) < 1e-9:
                return True
        except ValueError:
            continue
    return False


def verify_web(hit: dict, cutoff: str) -> tuple[bool, str]:
    """Open the cited page ourselves; the number must be printed there."""
    if hit["published_at"] > cutoff:
        return False, f"공표일 {hit['published_at']}이 발의일 이후"
    try:
        page = _fetch_text(hit["url"])
    except Exception as exc:  # noqa: BLE001 — any fetch failure just means "not verified"
        return False, f"원문을 열지 못함({type(exc).__name__})"
    if not _number_on_page(page, hit["value"]):
        return False, "원문에서 숫자를 찾지 못함"
    quoted = re.sub(r"\s+", "", hit["quote"]) in re.sub(r"\s+", "", page)
    if not quoted and abs(hit["value"]) < 1000:  # small numbers appear by chance; demand the sentence too
        return False, "작은 숫자라 인용문 일치가 필요한데 원문에 같은 문장이 없음"
    return True, "원문에서 숫자 확인" + (" · 인용문 일치" if quoted else "")


def _dedupe_clauses(design: dict) -> None:
    """Same article cited twice (본문 + 단서) → unique ids; point each amount at the clause holding it."""
    seen: dict[str, int] = {}
    for c in design["clauses"]:
        n = seen[c["id"]] = seen.get(c["id"], 0) + 1
        c["base"] = c["id"]
        if n > 1:
            c["id"] = f"{c['id']}({n})"
    for g in design["groups"]:
        same = [c for c in design["clauses"] if c["base"] == g["amount_clause_id"]]
        holding = [c for c in same if g["amount_min_won"] in _won_values(c["quote"])]
        if holding:
            g["amount_clause_id"] = holding[0]["id"]
    for c in design["clauses"]:
        c.pop("base")


def _locate_pages(design: dict, pages: list[str]) -> None:
    """PDF page (1-based) where each quote starts, so the page can open the bill at that spot."""
    flat = [re.sub(r"\s+", "", re.sub(r"-\s*\d{1,3}\s*-", "", p)) for p in pages]
    joined, starts, pos = "".join(flat), [], 0
    for f in flat:
        starts.append(pos)
        pos += len(f)
    for c in design["clauses"]:
        at = joined.rfind(re.sub(r"\s+", "", c["quote"]))  # last hit: operative text, not the 제안이유
        c["page"] = max(i for i, st in enumerate(starts) if st <= at) + 1 if at >= 0 else None


def _check_read(design: dict, operative: str) -> list[str]:
    problems = []
    ids = set()
    for c in design["clauses"]:
        ids.add(c["id"])
        if re.sub(r"\s+", "", c["quote"]) not in operative:
            problems.append(f"조문 인용이 개정 조문 원문에 없음: {c['id']} “{c['quote']}”")
    by_id = {c["id"]: c for c in design["clauses"]}
    for g in design["groups"]:
        clause = by_id.get(g["amount_clause_id"])
        if not clause:
            problems.append(f"{g['name']}: 지급액 조문 id '{g['amount_clause_id']}'가 clauses에 없음")
            continue
        found = _won_values(clause["quote"])
        for v in {g["amount_min_won"], g["amount_max_won"]}:
            if v not in found:
                problems.append(f"{g['name']}: 금액 {v:,}원이 인용 “{clause['quote']}”에 글자로 없음")
    sp = design["split"]
    if sp["in_bill"]:
        clause = by_id.get(sp["clause_id"])
        if not clause or not _ratio_in(clause["quote"], sp["national_ratio"]):
            problems.append(f"분담비율 {sp['national_ratio']}가 조문 '{sp['clause_id']}' 인용에 없음")
    return problems


def run(pdf: bytes, *, filename: str = "bill.pdf", log: Log | None = None, overrides: dict | None = None) -> dict:
    events: list[dict] = []
    sink = log or (lambda *_a: None)
    t0 = time.time()

    def log(step: str, status: str, text: str, data: dict | None) -> None:
        events.append(dict(t=round(time.time() - t0, 1), step=step, status=status, text=text, data=data))
        sink(step, status, text, data)

    out = _run(pdf, log, overrides or {}, t0)
    out["events"] = events
    out["filename"] = filename
    return out


def _run(pdf: bytes, log: Log, overrides: dict, t0: float) -> dict:

    # 1. 문서 읽기 -------------------------------------------------------
    log("read", "running", "PDF에서 텍스트와 의안번호·발의일을 읽는 중", None)
    pages = bill_pages(pdf)
    ident = bill_identity(pages)
    raw = re.sub(r"\n\s*-\s*\d{1,3}\s*-\s*\n", "\n", "".join(pages))  # page numbers split clauses
    operative = _bill_text(ident["bill_no"], raw)
    if not ident["propose_date"]:
        raise ValueError("발의일을 PDF에서 찾지 못했어요.")
    cutoff = ident["propose_date"]
    log("read", "done", f"{len(pages)}쪽 · 의안번호 {ident['bill_no'] or '미확인'} · 발의일 {cutoff} → "
        f"이 날짜 이전에 공개된 자료만 사용", dict(pages=len(pages), **ident))

    # 2. GPT: 조문 분석 -------------------------------------------------
    log("clauses", "running", f"AI({MODEL})가 개정 조문을 읽고 지급대상·지급액·지급연도를 설계하는 중", None)
    text = "\n".join(f"[p.{i + 1}]\n{p}" for i, p in enumerate(pages))[:60000]
    prompt = READ_PROMPT.format(bill_no=ident["bill_no"], cutoff=cutoff, text=text)
    design, info = gpt("bill_design", prompt, READ_SCHEMA)
    _dedupe_clauses(design)
    problems = _check_read(design, operative)
    retried = False
    if problems:
        log("clauses", "running", f"검증 실패 {len(problems)}건 → AI에 되돌려 다시 작성시키는 중", dict(problems=problems))
        design, info = gpt("bill_design", prompt + "\n\n=== 이전 답의 검증 실패(고쳐서 다시 작성) ===\n"
                           + "\n".join(problems), READ_SCHEMA)
        _dedupe_clauses(design)
        problems, retried = _check_read(design, operative), True
    if not design["is_cash_support"]:
        log("clauses", "error", f"현금 지원금 법안이 아니에요: {design['not_supported_reason']}", dict(design=design))
        return dict(status="unsupported", reason=design["not_supported_reason"], design=design, ident=ident)
    bad = {p.split(":")[0] for p in problems}
    design["clauses"] = [c for c in design["clauses"] if re.sub(r"\s+", "", c["quote"]) in operative]
    _locate_pages(design, pages)
    kept = {c["id"] for c in design["clauses"]}
    design["groups"] = [g for g in design["groups"] if g["name"] not in bad and g["amount_clause_id"] in kept]
    if design["split"]["in_bill"] and (design["split"]["clause_id"] not in kept or "분담비율" in bad):
        design["split"]["in_bill"] = False
    if not design["groups"]:
        log("clauses", "error", "검증을 통과한 지급 그룹이 없어요", dict(problems=problems))
        return dict(status="failed", problems=problems, design=design, ident=ident)
    log("clauses", "done",
        f"조문 {len(design['clauses'])}개 원문 확인 · 대상 그룹 {len(design['groups'])}개 · "
        f"지급연도 {design['payment_years'][0]}~{design['payment_years'][-1]}" + (" (1회 재작성)" if retried else ""),
        dict(design=design, problems=problems, usage=info))

    # 3. 원장 검색 ------------------------------------------------------
    log("search", "running", "기준정보 원장 3,204행에서 발의일 이전 공개 자료를 검색하는 중", None)
    found = {}
    for g in design["groups"]:
        found[g["name"]] = dict(people=candidates(g["search_queries"], cutoff, ident["bill_no"]),
                                rate=candidates(g["rate_queries"], cutoff, ident["bill_no"]) if g["needs_rate"] else [])
    split_cands = ([] if design["split"]["in_bill"]
                   else candidates(design["split"]["search_queries"] + ["재원분담", "국고보조율", "분담비율"],
                                   cutoff, ident["bill_no"], 10))
    log("search", "done", " · ".join(f"{k} 후보 {len(v['people'])}개" for k, v in found.items()),
        dict(found={k: dict(queries=next(g for g in design["groups"] if g["name"] == k)["search_queries"],
                            people=[_brief(r) for r in v["people"]], rate=[_brief(r) for r in v["rate"]])
                    for k, v in found.items()},
             split=[_brief(r) for r in split_cands]))

    # 4. GPT: 근거 선택 -------------------------------------------------
    log("pick", "running", "AI가 후보 중에서 조문 범위·기준시점이 맞는 근거를 고르는 중", None)
    groups_txt = "\n\n".join(
        f"[그룹] {g['name']} (sign {g['sign']}) — {g['who']}\n인원 후보:\n"
        + ("\n".join(json.dumps(_brief(r), ensure_ascii=False) for r in found[g["name"]]["people"]) or "(없음)")
        + (("\n지급률 후보:\n" + ("\n".join(json.dumps(_brief(r), ensure_ascii=False)
                                     for r in found[g["name"]]["rate"]) or "(없음)")) if g["needs_rate"] else "")
        for g in design["groups"])
    split_txt = ("조문에 분담비율 있음 — 고르지 마세요" if design["split"]["in_bill"]
                 else "\n".join(json.dumps(_brief(r), ensure_ascii=False) for r in split_cands) or "(없음)")
    picks, info2 = gpt("evidence_pick", PICK_PROMPT.format(cutoff=cutoff, years=design["payment_years"],
                                                          groups=groups_txt, split=split_txt),
                       _named(PICK_SCHEMA, [g["name"] for g in design["groups"]]))
    log("pick", "done", "근거 선택 완료 — 코드가 공개일·단위·자기 의안 여부를 재검증", dict(picks=picks, usage=info2))

    # 4b. 원장에 없으면 GPT 웹 검색 → 코드가 원문을 직접 열어 숫자 확인 --------------------
    web_hits = {}
    empty = [g for g in design["groups"] if not next((p for p in picks["groups"] if p["name"] == g["name"]), {})
             .get("ledger_id") and g["name"] not in (overrides or {})]
    if empty:
        log("web", "running", f"원장에 없는 {len(empty)}개 값을 AI가 웹에서 찾는 중 (발의일 이전 공표 자료만)", None)
        web_prompt = WEB_PROMPT.format(cutoff=cutoff, groups="\n".join(f"- {g['name']}: {g['who']}" for g in empty))
        for attempt in range(2):
            hits, info3 = gpt("web_lookup", web_prompt, _named(WEB_SCHEMA, [g["name"] for g in empty]), web=True)
            rejected = []
            for h in hits["groups"]:
                if not (h["found"] and h["value"] > 0):
                    continue
                if any(w in h["unit"] for w in ("가구", "농가", "어가", "세대")):
                    rejected.append(f"{h['name']}: {h['value']:,.0f}{h['unit']}는 사람 수가 아님 → 사람 수(명) 자료를 찾으세요")
                    continue
                ok, note = verify_web(h, cutoff)
                web_hits[h["name"]] = {**h, "verified": ok, "verify_note": note}
                if not ok:
                    rejected.append(f"{h['name']}: {h['url']} — {note}")
            if not rejected or attempt:
                break
            log("web", "running", f"검증 실패 {len(rejected)}건 → AI에 되돌려 다시 찾게 하는 중", dict(problems=rejected))
            web_prompt += "\n\n=== 이전 답의 검증 실패(다른 자료를 찾으세요) ===\n" + "\n".join(rejected)
        log("web", "done", " · ".join(f"{k}: {v['value']:,.0f}{v['unit']} ({v['verify_note']})"
                                      for k, v in web_hits.items()) or "웹에서도 찾지 못함",
            dict(hits=web_hits, searches=info3.get("searches"), usage=info3.get("usage")))

    # 5. 검증 + 계산 ----------------------------------------------------
    log("calc", "running", "선택된 근거를 검증하고 산식에 값을 넣어 계산하는 중", None)
    state = dict(design=design, picks=picks, ident=ident, cutoff=cutoff, raw=raw, web_hits=web_hits,
                 found={k: dict(people=[_brief(r) for r in v["people"]], rate=[_brief(r) for r in v["rate"]])
                        for k, v in found.items()},
                 split_cands=[_brief(r) for r in split_cands], model=MODEL,
                 usage=[info.get("usage"), info2.get("usage")])
    out = compute(state, overrides)
    log("calc", "done", f"계산 완료 ({time.time() - t0:.0f}초)"
        + (f" · 근거 없는 값 {len(out['needs_input'])}개" if out["needs_input"] else ""), dict(checks=out["checks"]))
    return out


def compute(state: dict, overrides: dict | None = None) -> dict:
    """Deterministic part only: verify GPT's picks, apply user inputs, calculate. No model call."""
    design, cutoff = state["design"], state["cutoff"]
    spec, checks, needs = build_spec(design, state["picks"], state["found"], state["split_cands"], state["ident"],
                                     cutoff, state["raw"], overrides or {}, state["web_hits"])
    result = estimate(spec)
    for name, sc in result["scenarios"].items():
        bad_years = [y for y, v in sc["per_year_won"].items() if v <= 0]
        if bad_years:
            checks.append(dict(item=f"합계 점검({name})", ok=False,
                               text=f"{', '.join(bad_years)}년 합계가 0 이하 — 차감 그룹이 기본 그룹보다 크거나 기본 대상 근거가 없음"))
            needs = needs or [dict(name=g["name"], who=g["who"], reason="합계가 0 이하라 대상 근거 재확인 필요",
                                   sign=g["sign"], queries=g["search_queries"])
                              for g in design["groups"] if g["sign"] > 0]
            break
    return dict(status="needs_input" if needs else "done", spec=spec, result=result, checks=checks,
                needs_input=needs, state=state, overrides=overrides or {})


def build_spec(design: dict, picks: dict, found: dict, split_cands: list, ident: dict, cutoff: str, raw: str,
               overrides: dict, web_hits: dict | None = None) -> tuple[dict, list, list]:
    web_hits = web_hits or {}
    checks, needs, groups = [], [], []
    pick_by = {p["name"]: p for p in picks["groups"]}
    allowed = {k: {r["id"] for r in v["people"]} for k, v in found.items()}
    allowed_rate = {k: {r["id"] for r in v["rate"]} for k, v in found.items()}
    years = sorted(set(design["payment_years"]))
    for g in design["groups"]:
        p = pick_by.get(g["name"], {})
        amount = dict(min=g["amount_min_won"], max=g["amount_max_won"], clause=g["amount_clause_id"],
                      times=max(1, g["times_per_year"]))
        out = dict(name=g["name"], amount=amount)
        if g["only_years"]:
            out["years"] = g["only_years"]
        user = overrides.get(g["name"])
        rid, reason = p.get("ledger_id", ""), ""
        row = _row(rid) if rid else None
        if user:
            out["recipients"] = dict(value=user["value"] * g["sign"], grade="user",
                                     source=f"사용자 입력: {user.get('source') or '출처 미기재'}",
                                     why=f"원장에 근거가 없어 사용자가 입력 · {g['who']}")
            checks.append(dict(item=g["name"], ok=True, text="사용자가 입력한 값 사용"))
        elif rid and rid not in allowed.get(g["name"], set()):
            reason = f"AI가 후보에 없는 id를 냄({rid}) → 거부"
        elif row and row["published_at"] > cutoff:
            reason = f"발의일 이후 공개({row['published_at']}) → 거부"
        elif row and row.get("source_bill") == ident["bill_no"]:
            reason = "이 의안 자신의 추계서 값 → 거부"
        elif row and (bad := _usable_people(row)):
            reason = f"{bad} → 거부"
        elif row:
            out["recipients"] = dict(ledger_id=rid, sign=g["sign"],
                                     why=f"{g['why']} · AI 선택 이유: {p['why']}"
                                         + (f" · 한계: {p['caveat']}" if p.get("caveat") else ""))
            if isinstance(row["value"], dict):
                gap = [y for y in years if str(y) not in row["value"]]
                if gap:
                    reason = f"연도별 값에 {gap} 없음 → 해당 연도 0이 되므로 거부"
                    out.pop("recipients")
            if "recipients" in out:
                checks.append(dict(item=g["name"], ok=True,
                                   text=f"{rid} · 공개 {row['published_at']} ≤ 발의일 {cutoff} · 단위 {row['unit']}"
                                        + (f" (×{UNIT_SCALE[row['unit']]:,} 환산)" if row["unit"] in UNIT_SCALE else "")))
        else:
            reason = p.get("why") or "후보 없음"
        if "recipients" not in out and (h := web_hits.get(g["name"])):
            value = h["value"] * UNIT_SCALE.get(h["unit"], 1) * g["sign"]
            out["recipients"] = dict(
                value=value, grade=("web_unverified" if not h["verified"] else
                                    "web" if _official_url(h["url"]) else "web_press"),
                source=f"{h['publisher']} 「{h['document']}」 (기준 {h['as_of']}, 공개 {h['published_at']}) {h['url']}",
                why=f"원장에 없어 AI 웹 검색 · {h['why']}" + (f" · 한계: {h['caveat']}" if h.get("caveat") else ""),
                quote=h["quote"], url=h["url"], note=h["verify_note"])
            checks.append(dict(item=g["name"], ok=h["verified"],
                               text=f"웹 {h['url']} · {h['verify_note']}" + ("" if h["verified"] else " → 가정으로 표시")))
        if "recipients" not in out:
            checks.append(dict(item=g["name"], ok=False, text=reason))
            needs.append(dict(name=g["name"], who=g["who"], reason=reason, sign=g["sign"],
                              queries=g["search_queries"]))
            out["recipients"] = dict(value=0, grade="missing", source=f"근거 없음 — {reason}",
                                     why=f"{g['who']} · 값을 입력하면 다시 계산합니다")
        rate_id = p.get("rate_ledger_id", "")
        if g["needs_rate"] and rate_id and "user" not in (out["recipients"].get("grade") or ""):
            rrow = _row(rate_id)
            ok = (rate_id in allowed_rate.get(g["name"], set()) and rrow and rrow["published_at"] <= cutoff
                  and rrow.get("source_bill") != ident["bill_no"] and isinstance(rrow["value"], (int, float))
                  and 0 < (rrow["value"] / 100 if rrow["unit"] == "%" else rrow["value"]) <= 1)
            if ok:
                out["rate"] = dict(ledger_id=rate_id, why=p.get("rate_why", ""))
            checks.append(dict(item=f"{g['name']} 지급률", ok=bool(ok),
                               text=f"{rate_id} 사용" if ok else f"{rate_id} 부적합(후보 밖·비율 아님·공개일) → 지급률 미적용"))
        groups.append(out)

    split = {}
    sp = design["split"]
    if sp["in_bill"]:
        split = dict(national=sp["national_ratio"], clause=sp["clause_id"])
    elif (sid := picks["split"]["ledger_id"]):
        srow = _row(sid)
        ratio = picks["split"]["national_ratio"]
        nums = (list(srow["value"].values()) if isinstance(srow["value"], dict) else [srow["value"]]) if srow else []
        pcts = " ".join(f"{v}%" for v in nums if isinstance(v, (int, float))) if srow and srow["unit"] == "%" else ""
        text = f"{json.dumps(srow['value'], ensure_ascii=False)} {pcts} {srow.get('quote') or ''} {srow['name']}" if srow else ""
        if srow and sid in {r["id"] for r in split_cands} and 0 < ratio <= 1 and _ratio_in(text, ratio):
            split = dict(ledger_id=sid, national=ratio, why=picks["split"]["why"])
            checks.append(dict(item="분담비율", ok=True, text=f"{sid} 국고 {ratio:.0%} (값이 근거 행에 있음)"))
        else:
            checks.append(dict(item="분담비율", ok=False,
                               text=f"{sid} 비율 {ratio}이 근거 행에서 확인되지 않음 → 기본 선례(재난지원금 분담) 사용"))
    spec = dict(bill_no=ident["bill_no"] or "upload", cutoff=cutoff, bill_title=design["bill_title"], bill_text=raw,
                clauses=[dict(id=c["id"], quote=c["quote"], page=c.get("page")) for c in design["clauses"]],
                groups=groups, payment_years=years, split=split,
                excluded=[dict(item=e["item"], reason=e["reason"]) for e in design["not_estimated"]])
    return spec, checks, needs


def answer_for(bill_no: str) -> dict | None:
    """NABO's own estimate for the reveal (never fed to the pipeline)."""
    if ANSWERS.exists():
        keyed = json.loads(ANSWERS.read_text(encoding="utf-8"))
        if bill_no in keyed:
            return keyed[bill_no]
    path = EXTRACTED / f"{bill_no}.json"
    if path.exists():
        d = json.loads(path.read_text(encoding="utf-8"))
        r = d.get("result") or {}
        if r.get("total_million"):
            by_year = {k: v * 1e6 for k, v in (r.get("by_year_million") or {}).items()}
            return dict(total=r["total_million"] * 1e6, by_year=by_year, formula=d.get("formula"),
                        quote=r.get("quote"), split=(d.get("payer_split") or {}).get("basis"))
    return None


def main() -> None:
    target = sys.argv[1]
    path = Path(target) if target.endswith(".pdf") else BILLS / target / "bill_text.pdf"
    out = run(path.read_bytes(), filename=path.name,
              log=lambda step, status, text, _d: print(f"[{step}:{status}] {text}", flush=True))
    for name, s in (out.get("result") or {}).get("scenarios", {}).items():
        print(f"{name}: {s['total_won'] / 1e8:,.0f}억원")
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
