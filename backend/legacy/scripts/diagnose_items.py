"""항목단위 진단 하네스.

공식 비용추계서의 조문별 비용 라인아이템을 파싱하고,
analyzer_v2(eval_v2/{bill}.json)의 항목과 조문번호로 매칭해서
 - 공식에만 있음(시스템 누락)
 - 시스템에만 있음(과잉/환각 의심)
 - 양쪽 다 있음(금액/산식 비교)
를 항목 단위로 보여준다. "어디서 틀렸는지"를 총액이 아니라 항목에서 본다.

사용: python3 -m backend.legacy.scripts.diagnose_items <bill_no>
전제: 먼저 run_one_v2로 eval_v2/{bill}.json 생성돼 있어야 함.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import fitz

FILES = Path("backend/generated/assembly_rag_seed_age21_50/files")
V2_DIR = Path("backend/generated/eval_v2")

# "라벨 ... (안 제7조) 12 12 12 12 12 ― ―"  형태의 조문별 비용 라인
_ARTICLE_IN_LABEL = re.compile(r"\(\s*안\s*제?\s*(\d+)\s*조(?:\s*의\s*\d+)?\s*\)")
_VALUE_TOKEN = re.compile(r"(?:\d[\d,]*(?:\.\d+)?|[―–\-])")


def _pdf_text(path: Path) -> str:
    with fitz.open(path) as doc:
        return "\n".join(p.get_text() for p in doc)


def _num(tok: str) -> float | None:
    if tok in {"―", "–", "-"}:
        return None
    try:
        return float(tok.replace(",", ""))
    except ValueError:
        return None


def parse_official_items(text: str) -> list[dict]:
    """조문별 비용 라인아이템 추출. 라벨에 (안 N조)가 있고 뒤에 연도값이 오는 행."""
    compact = re.sub(r"[ \t]+", " ", text)
    items: list[dict] = []
    for m in _ARTICLE_IN_LABEL.finditer(compact):
        art = m.group(1)
        # 라벨: 조문참조 앞 ~40자
        label_start = max(0, m.start() - 40)
        label = compact[label_start:m.start()].split("\n")[-1].strip(" ,·")
        # 값: 조문참조 뒤 120자에서 숫자/대시 토큰 최대 7개(5연도+합계+평균)
        tail = compact[m.end(): m.end() + 120]
        toks = _VALUE_TOKEN.findall(tail)[:7]
        vals = [_num(t) for t in toks]
        year_vals = [v for v in vals[:5]]
        if not any(v is not None for v in year_vals):
            continue
        items.append({
            "article": f"제{art}조",
            "label": label[-30:],
            "year_million": year_vals,
            "annual_first": next((v for v in year_vals if v is not None), None),
        })
    # 같은 조문 중복 라벨 정리(첫 등장 우선)
    seen = set()
    uniq = []
    for it in items:
        if it["article"] in seen:
            continue
        seen.add(it["article"])
        uniq.append(it)
    return uniq


def _system_items(bill: str) -> list[dict]:
    p = V2_DIR / f"{bill}.json"
    if not p.exists():
        raise SystemExit(f"analyzer_v2 결과 없음: {p} — 먼저 run_one_v2 실행")
    est = json.load(open(p, encoding="utf-8"))["full"].get("estimate") or {}
    out = []
    for it in est.get("items") or []:
        ref = str(it.get("trigger_ref") or "")
        arts = re.findall(r"제(\d+)조", ref)
        # 금액: assumptions로 계산 가능한지
        assum = it.get("assumptions") or []
        null_vars = [a.get("name") for a in assum if a.get("value") is None]
        var_vals = {a.get("name"): a.get("value") for a in assum}
        computed = all(a.get("value") is not None for a in assum) if assum else False
        out.append({
            "name": it.get("name"),
            "articles": [f"제{a}조" for a in arts],
            "formula": it.get("formula"),
            "amount_thousand": it.get("amount_thousand"),
            "null_vars": null_vars,
            "var_vals": var_vals,
            "computed": computed,
        })
    return out


def main() -> None:
    bill = sys.argv[1] if len(sys.argv) > 1 else "2126679"
    official = parse_official_items(_pdf_text(FILES / bill / "cost_estimate_비용추계서.pdf"))
    system = _system_items(bill)
    sys_by_art = {}
    for s in system:
        for a in s["articles"]:
            sys_by_art.setdefault(a, []).append(s)

    print("=" * 70)
    print(f"[{bill}] 항목단위 진단  (공식 {len(official)}항목 / 시스템 {len(system)}항목)")
    print("=" * 70)
    matched_arts = set()
    print("\n▶ 공식 항목 기준:")
    for o in official:
        hit = sys_by_art.get(o["article"])
        if hit:
            matched_arts.add(o["article"])
            for s in hit:
                state = "계산됨" if s["computed"] else f"미확정({s['null_vars']})"
                print(f"  [O] {o['article']} 공식 {o['year_million']}백만/년  ↔  시스템 [{state}]")
                print(f"      공식라벨: {o['label']}  |  시스템: {s['name']}")
                print(f"      시스템변수: {s['var_vals']}")
        else:
            print(f"  [X] {o['article']} 공식 {o['year_million']}백만/년 ({o['label']})  → 시스템 누락")
    print("\n▶ 시스템에만 있는 항목(공식 조문 매칭 안 됨, 과잉/환각 의심):")
    extra = [s for s in system if not any(a in matched_arts for a in s["articles"])]
    if not extra:
        print("  (없음)")
    for s in extra:
        print(f"  ? {s['articles']} {s['name']} | {s['formula']}")


if __name__ == "__main__":
    main()
