"""Cash support payment estimator with an evidence card for every number.

NABO conventions encoded (observed across support-payment estimates):
- an amount range in the bill → report lower- and upper-bound scenarios;
- no payer split in the bill → reuse the split of the most recent comparable
  executed program public before the cutoff, labelled as an assumption;
- recipients follow the bill's wording (전국민 → 주민등록인구).
Every clause quote is checked against the bill text, so the purpose
statement can never be mistaken for the operative clause.
Run: python3 -m backend.nabo_style.support_payment SPEC.json OUT_PREFIX
"""
from __future__ import annotations

import json
import re
import sys

import fitz

from backend.nabo_style.reference_facts import facts
from backend.nabo_style.reference_miner import ROOT

BILLS = ROOT / "generated/assembly_22_pdfs/by_bill"
GRADES = {"bill": "법안 명시", "official": "공식 통계", "precedent": "선례 준용", "assumption": "가정",
          "user": "사용자 입력", "missing": "근거 없음",
          "web": "공식 통계(웹 검색·원문 확인)", "web_press": "가정(언론보도·원문 확인)",
          "web_unverified": "가정(웹 검색·원문 미확인)"}
# ledger rows count people in mixed units; recipients are always converted to 명
UNIT_SCALE = {"천명": 1000, "만명": 10000, "천 명": 1000, "만 명": 10000}


def _bill_text(bill_no: str, raw: str | None = None) -> str:
    raw = raw if raw is not None else "".join(p.get_text() for p in fitz.open(BILLS / bill_no / "bill_text.pdf"))
    text = re.sub(r"\s+", "", raw)
    # operative text starts at "법률 제 호"; the purpose statement before it is not law
    return text.split("법률제", 1)[1] if "법률제" in text else text


def _check_quote(text: str, clause: dict) -> dict:
    found = re.sub(r"\s+", "", clause["quote"]) in text
    if not found:
        raise ValueError(f"quote not found in operative bill text: {clause['id']} '{clause['quote']}'")
    return {**clause, "verified_in_operative_text": True}


def _fact_card(topic: str, cutoff: str, *, reason: str, grade: str) -> tuple[dict, dict]:
    rows = facts(topic, cutoff)
    if not rows:
        raise LookupError(f"no '{topic}' fact public before {cutoff}")
    chosen = rows[0]
    card = dict(variable=topic, value=chosen["value"], unit=chosen["unit"], grade=GRADES[grade],
                source=f"{chosen['publisher']} 「{chosen['title']}」 (기준 {chosen['as_of']}, 공개 {chosen['available_at']})",
                url=chosen["url"], scope=chosen["scope"], why=reason,
                alternatives=[f"{r['title']} ({r['as_of']}): {r['value']}" for r in rows[1:]],
                learned_from_answer=chosen["learned_from_answer"], note=chosen.get("note", ""))
    return chosen, card


def estimate(spec: dict) -> dict:
    text = _bill_text(spec["bill_no"], spec.get("bill_text"))
    clauses = {c["id"]: _check_quote(text, c) for c in spec["clauses"]}
    cards, groups, seen_amounts = [], [], set()
    for g in spec["groups"]:
        if "indicator" in g["recipients"]:
            from backend.nabo_style import ledger
            try:
                row = ledger.lookup(g["recipients"]["indicator"], spec["cutoff"])
            except LookupError:
                if not g["recipients"].get("optional"):
                    raise
                cards.append(dict(variable=f"{g['name']} 대상자 수", value=0, unit="명", grade="근거 없음",
                                  source=f"발의일 {spec['cutoff']} 이전 공개 기준정보 없음 → 반영하지 않음",
                                  why=g["recipients"]["why"] + " (소규모라 미반영 표시 후 진행)", alternatives=[],
                                  learned_from_answer=False))
                groups.append((g["name"], 0, g["amount"]))
                continue
            recipients = row["value"] * g["recipients"].get("sign", 1)
            card = dict(variable=f"{g['name']} 대상자", value=recipients, unit=row["unit"], grade=row["grade"],
                        source=ledger.provenance(row, spec["cutoff"]), url=row.get("url", ""),
                        why=g["recipients"]["why"], alternatives=[],
                        learned_from_answer=row.get("learned_from_answer", False), note=row.get("note", ""))
        elif "ledger_id" in g["recipients"]:
            from backend.nabo_style import ledger
            row = next(r for r in ledger.all_rows() if r["id"] == g["recipients"]["ledger_id"])
            if row["published_at"] > spec["cutoff"] or row.get("source_bill") == spec["bill_no"]:
                raise LookupError(f"{row['id']} not usable at {spec['cutoff']} for {spec['bill_no']}")
            value = row["value"]
            k = UNIT_SCALE.get(row["unit"], 1) * g["recipients"].get("sign", 1)
            recipients = ({y: v * k for y, v in value.items()} if isinstance(value, dict) else value * k)
            card = dict(variable=f"{g['name']} 대상자", value=value, unit=row["unit"], grade=row["grade"],
                        source=ledger.provenance(row, spec["cutoff"]), url=row.get("url", ""),
                        why=g["recipients"]["why"], alternatives=[], quote=row.get("quote"),
                        learned_from_answer=row.get("learned_from_answer", False), note=row.get("note", ""))
        elif "fact_topic" in g["recipients"]:
            fact, card = _fact_card(g["recipients"]["fact_topic"], spec["cutoff"],
                                    reason=g["recipients"]["why"], grade="official")
            recipients = fact["value"]
        else:
            recipients = g["recipients"]["value"]
            card = dict(variable=f"{g['name']} 대상자", value=recipients, unit="명",
                        grade=GRADES[g["recipients"]["grade"]], source=g["recipients"]["source"],
                        why=g["recipients"]["why"], alternatives=[], learned_from_answer=False,
                        **{k: g["recipients"][k] for k in ("quote", "url", "note") if k in g["recipients"]})
        cards.append({**card, "variable": f"{g['name']} 대상자 수"})
        if g.get("rate"):
            from backend.nabo_style import ledger
            row = next(r for r in ledger.all_rows() if r["id"] == g["rate"]["ledger_id"])
            if row["published_at"] > spec["cutoff"] or row.get("source_bill") == spec["bill_no"]:
                raise LookupError(f"{row['id']} not usable at {spec['cutoff']} for {spec['bill_no']}")
            rate = row["value"] / 100 if row["unit"] == "%" else row["value"]
            cards.append(dict(variable=f"{g['name']} 지급률", value=rate, unit="ratio", grade=row["grade"],
                              source=ledger.provenance(row, spec["cutoff"]), url=row.get("url", ""),
                              why=g["rate"]["why"], alternatives=[], quote=row.get("quote"),
                              learned_from_answer=row.get("learned_from_answer", False), note=row.get("note", "")))
            recipients = ({y: v * rate for y, v in recipients.items()} if isinstance(recipients, dict)
                          else recipients * rate)
        amount = g["amount"]
        key = (amount["min"], amount["max"], amount["clause"], amount.get("times", 1))
        if key not in seen_amounts:
            seen_amounts.add(key)
            ranged = amount["min"] != amount["max"]
            cards.append(dict(variable="1인당 지급액" if len(seen_amounts) == 1 else f"1인당 지급액({g['name']})",
                              value=[amount["min"], amount["max"]] if ranged else amount["min"],
                              unit="원", grade=GRADES["bill"], source=f"원문 {amount['clause']}",
                              quote=clauses[amount["clause"]]["quote"],
                              why=(("범위로 정해지고 세부 기준은 하위법령 위임 → 하한·상한 시나리오" if ranged
                                    else "법안에 정액으로 명시")
                                   + (f" · 연 {amount['times']}회 지급" if amount.get("times", 1) > 1 else "")),
                              alternatives=[], learned_from_answer=False))
        groups.append((g["name"], recipients, amount))
    years = spec["payment_years"]
    options = {g["name"]: g for g in spec["groups"]}

    def people(name: str, n, year: int, variant: dict | None) -> float:
        g = options[name]
        if "years" in g and year not in g["years"]:
            return 0
        n = n.get(str(year), 0) if isinstance(n, dict) else n
        share = (variant or {}).get("share", {}).get(name, {})
        return n * share.get(str(year), 1)

    ranged = any(a["min"] != a["max"] for _, _, a in groups)
    picks = [("하한" if ranged else "기본", "min", None)] + ([("상한", "max", None)] if ranged else [])
    picks += [(v["name"], "min", v) for v in spec.get("variants", [])]
    scenarios = {}
    for label, pick, variant in picks:
        per_year = {str(y): sum(people(name, n, y, variant) * a[pick] * a.get("times", 1) for name, n, a in groups)
                    for y in years}
        scenarios[label] = {"per_year_won": per_year, "total_won": sum(per_year.values()),
                            **({"assumption": variant["why"]} if variant else {})}
    split = spec.get("split") or {}
    if split.get("ledger_id"):
        from backend.nabo_style import ledger
        row = next(r for r in ledger.all_rows() if r["id"] == split["ledger_id"])
        if row["published_at"] > spec["cutoff"] or row.get("source_bill") == spec["bill_no"]:
            raise LookupError(f"{row['id']} not usable at {spec['cutoff']} for {spec['bill_no']}")
        share = {"national": split["national"], "local": 1 - split["national"]}
        cards.append(dict(variable="국가·지자체 분담비율", value=share, unit="ratio", grade=GRADES["precedent"],
                          source=ledger.provenance(row, spec["cutoff"]), quote=row.get("quote"),
                          why=split["why"], alternatives=[], learned_from_answer=True, note=row.get("note", "")))
    elif split.get("national") is None:
        fact, card = _fact_card("현금지원금 재원분담", spec["cutoff"], grade="precedent",
                                reason="원문에 국가·지자체 분담비율이 없어 가장 최근의 동종 현금지원 사업 기준을 가정으로 준용")
        share = fact["value"]
        cards.append({**card, "variable": "국가·지자체 분담비율"})
    else:
        share = {"national": split["national"], "local": 1 - split["national"]}
        cards.append(dict(variable="국가·지자체 분담비율", value=share, unit="ratio", grade=GRADES["bill"],
                          source=f"원문 {split['clause']}", quote=clauses[split["clause"]]["quote"],
                          why="법안 명시", alternatives=[], learned_from_answer=False))
    for s in scenarios.values():
        s["national_won"] = round(s["total_won"] * share["national"])
        s["local_won"] = s["total_won"] - s["national_won"]
    return dict(bill_no=spec["bill_no"], cutoff=spec["cutoff"], title=spec["bill_title"],
                scenarios=scenarios, evidence=cards, clauses=list(clauses.values()),
                excluded=spec.get("excluded", []))


def _eok(won: float) -> str:
    return f"{won / 1e8:,.0f}억원"


def render(result: dict) -> str:
    lines = [f"# {result['title']} ({result['bill_no']}) 추계 초안", "",
             f"- 기준 시점: 발의일 {result['cutoff']} 이전 공개자료만 사용", "", "## 결과", "",
             "| 시나리오 | 총액 | 국가 | 지자체 |", "|---|---:|---:|---:|"]
    for name, s in result["scenarios"].items():
        lines.append(f"| {name} | {_eok(s['total_won'])} | {_eok(s['national_won'])} | {_eok(s['local_won'])} |")
    lines += ["", "## 근거 카드", ""]
    for c in result["evidence"]:
        flag = " · NABO 추계서 인용값(공개된 추계서에서 가져옴)" if c.get("learned_from_answer") else ""
        lines += [f"### {c['variable']} — {c['grade']}{flag}",
                  f"- 값: {c['value']} {c['unit']}", f"- 출처: {c['source']}"]
        if c.get("quote"):
            lines.append(f"- 원문 인용(개정문에서 확인됨): “{c['quote']}”")
        if c.get("url"):
            lines.append(f"- 링크: {c['url']}")
        lines.append(f"- 선택 이유: {c['why']}")
        if c.get("alternatives"):
            lines.append(f"- 검토한 다른 값: {'; '.join(c['alternatives'])}")
        if c.get("note"):
            lines.append(f"- 주의: {c['note']}")
        lines.append("")
    if result["excluded"]:
        lines += ["## 추계하지 않은 항목", ""] + [f"- {e['item']}: {e['reason']}" for e in result["excluded"]]
    return "\n".join(lines) + "\n"


def main() -> None:
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    result = estimate(spec)
    prefix = sys.argv[2]
    json.dump(result, open(prefix + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(prefix + ".md", "w", encoding="utf-8").write(render(result))
    for name, s in result["scenarios"].items():
        print(f"{name}: 총 {_eok(s['total_won'])} (국가 {_eok(s['national_won'])}, 지자체 {_eok(s['local_won'])})")


if __name__ == "__main__":
    main()
