"""기준정보 원장: versioned, citable unit prices and reference values.

Modelled on how NABO and council budget offices keep "단가 및 기준정보":
each row names the indicator, its reference year, the exact document and
locator (고시번호, 쪽·표), when it became public, and how often it is renewed.
Rows are never overwritten; a new value is a new row that supersedes the old.
NABO forecast series mined from earlier estimates are exposed through the same
lookup so every number answers "몇 년도, 어디 근거인가".

  python3 -m backend.nabo_style.ledger list
  python3 -m backend.nabo_style.ledger show resident_population --cutoff 2024-06-18
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from backend.nabo_style.reference import forecast

LEDGER = Path(__file__).with_name("data") / "reference_ledger.json"
FORECASTS = {"civil_wage_growth": "공무원임금 평균상승률", "employer_rate": "공무원 기관부담금요율",
             "asset_per_person": "정부기관 1인당 자산취득비", "cpi": "소비자물가상승률",
             "nominal_wage_growth": "명목임금상승률"}


def rows() -> list[dict]:
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    ids = [r["id"] for r in data]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate ledger id")
    return data


ERCE_DB = Path(__file__).resolve().parents[1] / "generated/erce_variable_evidence.sqlite3"
_ERCE_GRADE = {"official_standard": "공식(법령·통계)", "precedent_assumption": "선례·기준정보",
               "calculated_estimate": "계산값", "target_current_actual": "대상사업 실적"}


def erce_rows() -> list[dict]:
    """Read-only view of ERCE evidence in ledger shape; bill-only rows are left out.

    ERCE's available_at often holds the reference date rather than the release
    date, so published_at is marked unconfirmed here. ERCE itself is untouched.
    """
    import sqlite3
    from contextlib import closing
    if not ERCE_DB.exists():
        return []
    from backend.nabo_style.reference import _texts
    replied = {d["bill_no"]: (d["reply_date"], d.get("estimate_no")) for d in _texts()}
    out = []
    with closing(sqlite3.connect(f"file:{ERCE_DB}?mode=ro", uri=True)) as db:
        for (raw,) in db.execute("SELECT row_json FROM erce_variable_evidence"):
            r = json.loads(raw)
            if r.get("reuse_policy") == "target_only":
                continue
            year = r.get("price_year") or r.get("valid_from_year") or (r.get("value_years") or [None])[0]
            # A precedent read off a NABO estimate became public on that estimate's reply date.
            reply = replied.get(str(r.get("source_bill_no")))
            published, confirmed = (reply[0], True) if reply else (r["available_at"], False)
            out.append(dict(
                id=f"erce:{r['evidence_key']}", indicator=f"erce:{r['variable_key']}",
                name=f"{r['variable_key']} — {r.get('scope', '')}", category=r.get("policy_domain", ""),
                value=r["value"], unit=r.get("unit", ""), reference_year=year, as_of=r.get("reference_date"),
                publisher=r.get("agency", ""), document=r.get("source_ref", ""),
                locator=f"ERCE {r['evidence_key']} (출처 의안 {r.get('source_bill_no')})",
                published_at=published, published_at_confirmed=confirmed,
                source_estimate=(f"{r.get('source_bill_no')} 비용추계서 {reply[1] or ''} (회답 {reply[0]})" if reply else ""),
                url=r.get("source_url", ""), grade=_ERCE_GRADE.get(r.get("source_class"), r.get("source_class")),
                update_cycle_years=None, supersedes=None,
                learned_from_answer=r.get("obtained_from") == "reviewed_answer",
                reuse_policy=r.get("reuse_policy"), note=r.get("limitation", "")))
        for year, schedule, name, table, grade, step, won, unit, url in db.execute(
                "SELECT year, schedule, schedule_name, regulation_table, grade, step, monthly_base_won, unit,"
                " source_url FROM erce_official_salary_rates"):
            out.append(dict(
                id=f"erce:salary:{year}:{schedule}:{grade}:{step}", indicator=f"civil_salary:{schedule}:{grade}급",
                name=f"{name} {grade}급 {step}호봉 월 봉급", category="인건비", value=won, unit=unit,
                reference_year=year, publisher="인사혁신처", document="공무원보수규정",
                locator=f"{table} {name}", published_at=f"{year - 1}-12-31", published_at_confirmed=False,
                url=url, grade="법령·고시", update_cycle_years=1, supersedes=None,
                learned_from_answer=False, note="ERCE 공식 봉급표(읽기 전용)"))
    return out


SUPPORT_EXTRACTED = Path(__file__).resolve().parents[1] / "generated/nabo_style/support/extracted"


def support_rows() -> list[dict]:
    """Variables read off NABO support-payment estimates (quote-verified extraction).

    Public from the estimate's reply date; the original source NABO cited is kept
    so a user can follow it to the primary document.
    """
    from backend.nabo_style.reference import _texts
    replied = {d["bill_no"]: (d["reply_date"], d.get("estimate_no"), d["bill_name"]) for d in _texts()}
    out = []
    for f in sorted(SUPPORT_EXTRACTED.glob("*.json")) if SUPPORT_EXTRACTED.exists() else []:
        data = json.loads(f.read_text(encoding="utf-8"))
        bill = data["bill_no"]
        reply, est, title = replied.get(bill, (None, None, ""))
        if not reply:
            continue
        for i, v in enumerate(data.get("variables") or []):
            out.append(dict(
                id=f"nabo_support:{bill}:{i}", indicator=f"support:{v.get('role')}",
                name=v.get("name", ""), category="지원금 선례", value=v.get("value"), unit=v.get("unit", ""),
                reference_year=None, as_of=str(v.get("as_of") or ""),
                publisher=v.get("source") or "국회예산정책처", document=f"{bill} {title} 비용추계서 {est or ''}".strip(),
                locator=(f"{v['source_locator']} · " if v.get("source_locator") else "")
                        + f"인용: “{(v.get('quote') or '')[:80]}”",
                published_at=reply, published_at_confirmed=True,
                url=v.get("source_url") or "",
                grade=f"NABO 인용·{v['source_type']}" if v.get("source_type") else "선례·기준정보",
                update_cycle_years=None, supersedes=None,
                learned_from_answer=True, quote=v.get("quote"), source_bill=bill,
                note=f"원 출처: {v.get('source') or '문서에 미기재'} / 기준시점 {v.get('as_of') or '미기재'}"))
    return out


WEB_LEDGER = Path(__file__).with_name("data") / "web_ledger.json"


def web_rows() -> list[dict]:
    """Rows a user added from a verified web search (원장 화면의 '원장에 추가')."""
    return json.loads(WEB_LEDGER.read_text(encoding="utf-8")) if WEB_LEDGER.exists() else []


def all_rows() -> list[dict]:
    return rows() + web_rows() + erce_rows() + support_rows()


def search(text: str, cutoff: str, *, limit: int = 10, exclude_bill: str | None = None) -> list[dict]:
    """Keyword search across curated + ERCE rows public on/before cutoff (never the target's own answer)."""
    terms = text.split()
    hits = [r for r in all_rows() if r["published_at"] <= cutoff and r.get("source_bill") != exclude_bill and all(
        t in f"{r['id']} {r['name']} {r['document']} {r.get('note', '')}" for t in terms)]
    hits.sort(key=lambda r: (r["grade"] != "공식(법령·통계)" and r["grade"] != "공식 통계"
                             and r["grade"] != "법령·고시", r["published_at"]), reverse=False)
    return hits[:limit]


def lookup(indicator: str, cutoff: str, *, reference_year: int | None = None) -> dict:
    """Newest row public on/before cutoff (optionally for a given reference year)."""
    if indicator in FORECASTS:
        fc = forecast(indicator, cutoff)
        return dict(id=f"nabo_forecast:{indicator}:{fc['newest_quote']}", indicator=indicator,
                    name=FORECASTS[indicator], category="NABO 전망", value=fc["values"],
                    unit="thousand KRW/person" if indicator == "asset_per_person" else "%",
                    reference_year=None, publisher="국회예산정책처",
                    document="비용추계서에 인용된 NABO 전망치(합의값)",
                    locator=f"인용 추계서 {', '.join(fc['sources'])}; 연도별 지지 {fc['support']}",
                    published_at=fc["newest_quote"], published_at_confirmed=True,
                    grade="NABO 전망", update_cycle_years=0.5, learned_from_answer=False,
                    note="최근 인용 추계서들의 최빈값. 원 전망 보고서 미대조")
    candidates = [r for r in rows() if r["indicator"] == indicator and r["published_at"] <= cutoff
                  and (reference_year is None or r["reference_year"] == reference_year)]
    if not candidates:
        raise LookupError(f"'{indicator}' 기준정보 없음 (공개일 ≤ {cutoff})")
    return max(candidates, key=lambda r: (r["published_at"], str(r.get("as_of") or r.get("reference_year") or "")))


def staleness(row: dict, cutoff: str) -> str:
    cycle = row.get("update_cycle_years")
    as_of = row.get("as_of") or (f"{row['reference_year']}-12-31" if row.get("reference_year") else None)
    if not cycle or not as_of:
        return ""
    age = (date.fromisoformat(cutoff) - date.fromisoformat(as_of)).days / 365.25
    return f"기준시점이 {age:.1f}년 전(갱신주기 {cycle}년) — 최신값 확인 필요" if age > cycle * 1.5 else ""


def provenance(row: dict, cutoff: str = "") -> str:
    """One line a user can verify: 몇 년도, 어느 기관, 어떤 문서, 어디, 언제 공개."""
    year = row.get("as_of") or row.get("reference_year") or "연도별"
    confirmed = "" if row.get("published_at_confirmed") else "(공개일 추정)"
    doc = row["document"] if "「" in row["document"] else f"「{row['document']}」"
    parts = [f"{row['name']} {year} 기준", f"{row['publisher']} {doc} {row['locator']}",
             f"공개 {row['published_at']}{confirmed}", f"[{row['grade']}]"]
    if row.get("learned_from_answer"):
        parts.append("NABO 추계서 인용값")
    if cutoff and (warn := staleness(row, cutoff)):
        parts.append(f"⚠{warn}")
    return " · ".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("stats")
    find = sub.add_parser("search")
    find.add_argument("text")
    find.add_argument("--cutoff", default=date.today().isoformat())
    show = sub.add_parser("show")
    show.add_argument("indicator")
    show.add_argument("--cutoff", default=date.today().isoformat())
    show.add_argument("--year", type=int)
    args = parser.parse_args()
    if args.cmd == "list":
        for r in sorted(rows(), key=lambda r: (r["category"], r["indicator"], r["published_at"])):
            print(f"{r['category']:6s} {r['id']:40s} {r['value']} {r['unit']}  ← {provenance(r)}")
        for key, name in FORECASTS.items():
            print(f"NABO전망 {key:38s} (추계서 인용 시계열, 시점별 조회)  {name}")
        return
    if args.cmd == "stats":
        from collections import Counter
        allr = all_rows()
        print("총", len(allr), "행 (원장", len(rows()), "+ ERCE 읽기전용", len(allr) - len(rows()), ") + NABO 전망", len(FORECASTS), "종")
        print("등급별", Counter(r["grade"] for r in allr).most_common())
        print("정답에서 처음 확인", sum(r["learned_from_answer"] for r in allr),
              "/ 공개일 확인됨", sum(bool(r.get("published_at_confirmed")) for r in allr))
        return
    if args.cmd == "search":
        for r in search(args.text, args.cutoff):
            print(f"- {r['value']} {r['unit']}  ← {provenance(r, args.cutoff)}")
        return
    row = lookup(args.indicator, args.cutoff, reference_year=args.year)
    print(json.dumps(row, ensure_ascii=False, indent=2))
    print("근거:", provenance(row, args.cutoff))


if __name__ == "__main__":
    main()
