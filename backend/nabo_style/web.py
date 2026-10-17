"""Small JSON API for the demo page (frontend/nabo.html).

Kept separate from backend/server.py so the existing ERCE web flow is untouched.
Every case is normalised to one shape so the page can show, for any number,
where it came from (기관·문서·위치·기준시점·공개일) and whether it was public
before the bill was proposed.
  GET /api/nabo/cases                      → case list
  GET /api/nabo/case/{id}                  → full case (clauses, formula tokens, sources, results, ERCE, NABO answer)
  GET /api/nabo/ledger?q=TEXT&cutoff=DATE  → reference-ledger rows public on/before cutoff
  POST /api/nabo/ai/run {bill_no | pdf_b64, filename} → job id (GPT pipeline, ai_pipeline.py)
  GET /api/nabo/ai/job/{id}                → step events + normalised case when finished
  POST /api/nabo/ai/recompute {job|run_id, overrides} → recalculated case, no model call
  GET /api/nabo/ai/samples · /api/nabo/ai/run/{run_id} → sample bills, saved runs for replay
Run: python3 -m backend.nabo_style.web   (port NABO_WEB_PORT, default 8010)
"""
from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from backend.nabo_style import ledger
from backend.nabo_style.reference_miner import ROOT
from backend.nabo_style.support_payment import BILLS, estimate

DOCS = ROOT.parent / "docs/nabo_style"

GRADE_KEYS = (("법안", "bill"), ("NABO", "nabo"), ("선례", "precedent"), ("공식", "official"),
              ("법령", "official"), ("가정", "assumption"), ("근거 없음", "missing"))


def _grade_key(grade: str) -> str:
    return next((key for word, key in GRADE_KEYS if word in (grade or "")), "assumption")


def _date(text: str) -> str | None:
    m = re.search(r"공개\s*(\d{4}-\d{2}-\d{2})", text or "") or re.search(r"(\d{4}-\d{2}-\d{2})", text or "")
    return m.group(1) if m else None


def _meta(bill: str) -> dict:
    if not bill:
        return {}
    path = BILLS / bill / "metadata.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _read(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _source(sid: str, name: str, value, unit: str, grade: str, *, origin: str, published_at: str | None,
            as_of=None, quote: str | None = None, url: str = "", note: str = "", why: str = "") -> dict:
    from backend.nabo_style.display import clean_name, short_origin, unit_ko
    short = short_origin(origin)
    return dict(id=sid, name=clean_name(name), value=value, unit=unit_ko(unit), grade=grade, grade_key=_grade_key(grade),
                origin=origin, where=short["where"], as_of_ko=short["as_of"], published_at=published_at,
                as_of=as_of, quote=quote, url=url, note=note, why=why)


def _support_case(spec_path, *, case_id: str) -> dict:
    """Case computed by support_payment from an AI-written spec (clauses verified in the bill text)."""
    spec = _read(spec_path)
    result = estimate(spec)
    sources, tokens = [], []
    for i, card in enumerate(result["evidence"]):
        sid = f"s{i}"
        sources.append(_source(sid, card["variable"], card["value"], card["unit"], card["grade"],
                               origin=card["source"], published_at=_date(card["source"]),
                               quote=card.get("quote"), url=card.get("url", ""), note=card.get("note", ""),
                               why=card.get("why", "")))
    by_var = {s["name"]: s["id"] for s in sources}
    for g in spec["groups"]:
        sid = by_var.get(f"{g['name']} 대상자 수")
        sign = g["recipients"].get("sign", 1)
        if tokens:
            tokens.append(dict(op="−" if sign < 0 else "+"))
        tokens.append(dict(label=g["name"], source=sid, abs=sign < 0))
    amount = next(s["id"] for s in sources if s["name"] == "1인당 지급액")
    tokens = [dict(op="(")] + tokens + [dict(op=")"), dict(op="×"), dict(label="1인당 지급액", source=amount)]
    years = spec["payment_years"]
    if len(years) > 1:
        tokens += [dict(op="×"), dict(label=f"{years[0]}~{years[-1]}년", source=None)]
    split = next((s["id"] for s in sources if s["name"] == "국가·지자체 분담비율"), None)
    scenarios = {name: dict(total=s["total_won"], by_year={y: int(v) for y, v in s["per_year_won"].items()},
                            national=s["national_won"], local=s["local_won"], assumption=s.get("assumption"))
                 for name, s in result["scenarios"].items()}
    return dict(clauses=[dict(id=c["id"], quote=c["quote"], verified=True)
                         for c in result["clauses"]],
                not_estimated=[dict(item=e["item"], reason=e["reason"]) for e in result["excluded"]],
                formula=dict(text="지원금 = Σ(대상 그룹 인원 × 1인당 지급액) × 지급연도", tokens=tokens,
                             split_source=split),
                sources=sources, scenarios=scenarios, cutoff=spec["cutoff"])


_PENSION_NAMES = {
    "pop65": "65세 이상 인구", "base_pension_2024": "2024 기준연금액", "cpi": "소비자물가상승률 전망",
    "special_base_amount": "특례 기준연금액(법안)", "take_up_vs_70pct": "수급률 보정(67.5%÷70%)",
    "couple_both_share": "부부 2인 수급자 비율", "couple_reduction": "부부 감액률",
    "national_share": "국고보조율", "start_year": "시행연도", "post2027_indexing": "2028년 이후 특례액 물가연동",
}
_GRADE_LABEL = {"공식통계": "공식 통계", "NABO인용": "NABO 추계서 인용값", "법안명시": "법안 명시", "가정": "가정"}


def _pension_case() -> dict:
    """기초연금 2203602: computed by a fresh agent that never saw the answer (own calc script)."""
    run = _read(DOCS / "compare_2203602/nabo_blind_run.json")
    sources = []
    for v in run["variables"]:
        sources.append(_source(v["name"], _PENSION_NAMES.get(v["name"], v["name"]), v["value"], v["unit"],
                               _GRADE_LABEL.get(v["grade"], v["grade"]),
                               origin=f"{v['source']} · {v['ref']}", published_at=_date(v.get("published_at")),
                               as_of=v.get("as_of"), note=v.get("note", "")))
        sources[-1]["published_label"] = v.get("published_at")
    t = lambda label, sid: dict(label=label, source=sid)  # noqa: E731
    tokens = [t("65세 이상 인구", "pop65"), dict(op="×"), t("구간비율 30%·20%", "special_base_amount"), dict(op="×"),
              t("수급률 보정", "take_up_vs_70pct"), dict(op="×"), dict(op="("), t("특례 40만원", "special_base_amount"),
              dict(op="−"), t("현행 기준연금액(물가연동)", "base_pension_2024"), dict(op=")"), dict(op="×"),
              t("12개월", None), dict(op="×"), dict(op="("), t("1", None), dict(op="−"),
              t("부부감액 20%", "couple_reduction"), dict(op="×"), t("부부 2인 비율", "couple_both_share"), dict(op=")")]
    years = {y: r["total"] for y, r in run["results_by_year_won"].items() if r["total"]}
    clauses = [dict(id=c["id"], quote=c["quote"], verified=True, effect=c.get("effect")) for c in run["clauses"]]
    return dict(clauses=clauses,
                not_estimated=[dict(item=e["id"], reason=e["reason"]) for e in run["not_estimated"]],
                formula=dict(text=run["formula"], tokens=tokens, split_source="national_share"),
                sources=sources, cutoff=run["cutoff"],
                scenarios={"기본": dict(total=run["total_2026_2030_won"], by_year=years,
                                       national=run["total_national_won"], local=run["total_local_won"]),
                           "2028년 이후 40만원 고정": dict(
                               total=run["sensitivity_fixed_400k_after_2027"]["total"],
                               by_year={y: v for y, v in run["sensitivity_fixed_400k_after_2027"]["by_year"].items() if v},
                               assumption="법안에 2026·2027 금액만 있으므로 이후 명목 고정으로 해석한 민감도")})


CASES = {
    "2200563": dict(
        label="민생회복지원금", sub="서영교 의원 등 10인 · 1인당 25만원",
        blind=dict(nabo_style="정답 미열람 실행", erce="정답 미열람 첫 실행(2026-09-28)"),
        build=lambda: _support_case(DOCS / "compare_2200563/support_spec_ledger.json", case_id="2200563"),
        erce=dict(status="partial", total=12_819_336_750_000,
                  note="국민 기준액만 산출. 수용자 제외·외국인 포함 근거가 DB에 없어 반영 못함",
                  formula="대상자 수 × 참여율 × 1인당 지급액 × 지급횟수"),
        nabo=dict(no="24D0967", reply="2024-07-11", scenarios={"기본": 13_322_743_000_000},
                  by_year={"2024": 13_322_743_000_000}),
        comparison=DOCS / "compare_2200563/comparison.json"),
    "2203602": dict(
        label="기초연금 40만원 인상", sub="주호영 의원 등 14인 · 저소득층 단계 인상",
        blind=dict(nabo_style="새 에이전트, 정답 미열람", erce="정답 확인 후 보강된 엔진으로 재실행"),
        build=_pension_case,
        erce=dict(status="needs_input", total=None,
                  note="산식(기존급여 인상차액)은 선택했으나 소득구간별 수급자 수·현행 기준연금액·감액비율 근거 없음 → 중단",
                  formula="기존 대상자 수 × 지급률 × (신규 지급액 − 현행 지급액) × 연간 지급횟수"),
        nabo=dict(no="24C3532", reply="2024-11-12", scenarios={"기본": 11_100_000_000_000},
                  by_year={"2026": 1.1e12, "2027": 2.2e12, "2028": 2.4e12, "2029": 2.6e12, "2030": 2.8e12}),
        comparison=DOCS / "compare_2203602/comparison.json"),
    "2212323": dict(
        label="농어촌기본소득", sub="용혜인·신정훈 의원 등 29인 · 연 360만원",
        blind=dict(nabo_style="정답 미열람 실행(평가용 보관 의안)", erce="정답 미열람 첫 실행"),
        build=lambda: _support_case(DOCS / "compare_2212323/support_spec.json", case_id="2212323"),
        erce=dict(status="needs_input", total=None, note="산식은 선택했으나 읍·면 인구 근거 0건 → 중단",
                  formula="대상자 수 × 참여율 × 1인당 지급액 × 연간 지급횟수"),
        nabo=dict(no="25B4641", reply="2025-10-30", scenarios={"기본": 173_535_200_000_000},
                  by_year={"2026": 34_808_500_000_000, "2027": 34_758_200_000_000, "2028": 34_707_900_000_000,
                           "2029": 34_656_700_000_000, "2030": 34_603_900_000_000}),
        comparison=DOCS / "compare_2212323/comparison.json"),
    "2200037": dict(
        label="전국민 민생회복지원금", sub="이재명 의원 외 170인 · 25~35만원",
        blind=dict(nabo_style="재현 사례(이 의안 정답을 보고 규칙 작성)", erce="첫 실행"),
        build=lambda: _support_case(DOCS / "compare_2200037/support_spec.json", case_id="2200037"),
        erce=dict(status="partial", total=12_937_766_000_000,
                  note="KOSIS 추계인구(외국인 포함) 사용, 35만원 상한·국가/지자체 분담 누락",
                  formula="대상자 수 × 참여율 × 1인당 지급액 × 지급횟수"),
        nabo=dict(no="24D0385", reply="2024-06-25",
                  scenarios={"하한": 12_819_337_000_000, "상한": 17_947_071_000_000}, by_year={}),
        comparison=DOCS / "compare_2200037/comparison.json"),
}


def case(case_id: str) -> dict:
    cfg = CASES[case_id]
    meta = _meta(case_id)
    body = cfg["build"]()
    comp = _read(cfg["comparison"]) if cfg["comparison"].exists() else {}
    ours = next(iter(body["scenarios"].values()))["total"]
    nabo_total = next(iter(cfg["nabo"]["scenarios"].values()))
    for s in body["sources"]:
        if s["grade_key"] == "missing":
            s["published_at"] = None
        elif s["grade_key"] == "bill":
            s["published_at"] = s["published_at"] or body["cutoff"]
        s["before_cutoff"] = (s["published_at"] <= body["cutoff"]) if s["published_at"] else None
    return dict(
        id=case_id, label=cfg["label"], sub=cfg["sub"], blind=cfg["blind"],
        bill=dict(no=case_id, title=meta.get("bill_name"), proposer=meta.get("proposer"),
                  propose_date=meta.get("propose_date"), committee=meta.get("committee"),
                  result=meta.get("process_result")),
        **body,
        erce={**cfg["erce"], "error_pct": ((cfg["erce"]["total"] - nabo_total) / nabo_total * 100
                                           if cfg["erce"]["total"] else None)},
        answer=dict(**cfg["nabo"], error_pct=(ours - nabo_total) / nabo_total * 100,
                    judgement_match=comp.get("judgement_match"), gap=comp.get("gap")),
    )


# ---------------------------------------------------------------- AI pipeline (upload → GPT → estimate)

RUNS = ROOT / "generated/nabo_style/ai_runs"
JOBS: dict[str, dict] = {}
SAMPLES = (("2200563", "민생회복지원금 지급 특별법안", "1인당 25만원 · 전국민"),
           ("2211090", "청년농어민기본소득법안", "40세 미만 농어민 월 30만원"),
           ("2212323", "농어촌기본소득법안", "읍·면 주민 연 360만원"),
           ("2200037", "전국민 민생회복지원금 특별조치법안", "1인당 25~35만원"))


def _ai_tokens(spec: dict, sources: list[dict]) -> list[dict]:
    by_var = {s["name"]: s["id"] for s in sources}
    amounts = {(g["amount"]["min"], g["amount"]["max"], g["amount"].get("times", 1)) for g in spec["groups"]}
    tokens: list[dict] = []
    for g in spec["groups"]:
        sign = g["recipients"].get("sign", 1) if "ledger_id" in g["recipients"] else (
            -1 if (g["recipients"].get("value") or 0) < 0 else 1)
        if tokens:
            tokens.append(dict(op="−" if sign < 0 else "+"))
        part = [dict(label=g["name"], source=by_var.get(f"{g['name']} 대상자 수"), abs=sign < 0)]
        if g.get("rate"):
            part += [dict(op="×"), dict(label="지급률", source=by_var.get(f"{g['name']} 지급률"))]
        if len(amounts) > 1:
            amt = by_var.get(f"1인당 지급액({g['name']})") or by_var.get("1인당 지급액")
            part += [dict(op="×"), dict(label="1인당 지급액", source=amt)]
            if g["amount"].get("times", 1) > 1:
                part += [dict(op="×"), dict(label=f"연 {g['amount']['times']}회", source=None)]
        tokens += part
    if len(amounts) == 1:
        times = next(iter(amounts))[2]
        tokens = ([dict(op="(")] + tokens + [dict(op=")")] if len(spec["groups"]) > 1 else tokens)
        tokens += [dict(op="×"), dict(label="1인당 지급액", source=by_var.get("1인당 지급액"))]
        if times > 1:
            tokens += [dict(op="×"), dict(label=f"연 {times}회", source=None)]
    years = spec["payment_years"]
    if len(years) > 1:
        tokens += [dict(op="×"), dict(label=f"{years[0]}~{years[-1]}년", source=None)]
    return tokens


def ai_case(out: dict) -> dict:
    """Normalise a pipeline result into the same shape as the curated cases."""
    from backend.nabo_style.ai_pipeline import answer_for
    spec, result, state = out["spec"], out["result"], out["state"]
    ident = state["ident"]
    sources = []
    for i, card in enumerate(result["evidence"]):
        sources.append(_source(f"s{i}", card["variable"], card["value"], card["unit"], card["grade"],
                               origin=card["source"], published_at=_date(card["source"]),
                               quote=card.get("quote"), url=card.get("url", ""), note=card.get("note", ""),
                               why=card.get("why", "")))
    cutoff = spec["cutoff"]
    for s in sources:
        if s["grade_key"] == "missing":
            s["published_at"] = None
        elif s["grade_key"] == "bill" or s["grade"] == "사용자 입력":
            s["published_at"] = s["published_at"] or cutoff
        s["before_cutoff"] = (s["published_at"] <= cutoff) if s["published_at"] else None
    split = next((s["id"] for s in sources if s["name"] == "국가·지자체 분담비율"), None)
    scenarios = {name: dict(total=sc["total_won"], by_year={y: int(v) for y, v in sc["per_year_won"].items()},
                            national=sc["national_won"], local=sc["local_won"], assumption=sc.get("assumption"))
                 for name, sc in result["scenarios"].items()}
    ours = next(iter(scenarios.values()))["total"]
    ans = answer_for(ident["bill_no"]) if ident["bill_no"] else None
    design = state["design"]
    return dict(
        id=f"ai:{ident['bill_no'] or 'upload'}", label=ident.get("title") or _meta(ident["bill_no"]).get("bill_name") or design["bill_title"], sub="AI 파이프라인 실행",
        blind=dict(nabo_style=f"GPT({state['model']})가 이 의안 추계서를 보지 않고 실행", erce="—"),
        bill=dict(no=ident["bill_no"] or "업로드",
                  title=ident.get("title") or _meta(ident["bill_no"]).get("bill_name") or design["bill_title"],
                  proposer=ident.get("proposer"), propose_date=cutoff, committee=ident.get("committee")),
        clauses=[dict(id=c["id"], quote=c["quote"], verified=True, page=c.get("page"), role=next(
            (d["role"] for d in design["clauses"] if d["id"] == c["id"]), None)) for c in result["clauses"]],
        not_estimated=[dict(item=e["item"], reason=e["reason"]) for e in result["excluded"]],
        formula=dict(text="지원금 = Σ(대상 그룹 인원 × 1인당 지급액 × 연간 지급횟수) × 지급연도",
                     tokens=_ai_tokens(spec, sources), split_source=split),
        sources=sources, scenarios=scenarios, cutoff=cutoff, erce=None,
        answer=(dict(no=ans.get("no", "NABO 추계서"), reply=ans.get("reply", ""), scenarios={"기본": ans["total"]},
                     by_year=ans.get("by_year", {}), error_pct=(ours - ans["total"]) / ans["total"] * 100,
                     formula=ans.get("formula"), quote=ans.get("quote"), split=ans.get("split"),
                     judgement_match=None, gap=None) if ans else None),
        ai=dict(summary=design["summary"], payment_years_why=design["payment_years_why"], checks=out["checks"],
                needs_input=out["needs_input"], overrides=out.get("overrides", {}), model=state["model"],
                status=out["status"]))


def _summary(out: dict) -> dict:
    scen = out["result"]["scenarios"]
    first = next(iter(scen.values()))
    return dict(total=first["total_won"], upper=scen["상한"]["total_won"] if "상한" in scen else None,
                years=sorted(first["per_year_won"]), status=out["status"], needs=len(out["needs_input"]))


def _save_run(out: dict, pdf: bytes | None = None) -> str:
    RUNS.mkdir(parents=True, exist_ok=True)
    run_id = f"{out['state']['ident']['bill_no'] or 'upload'}_{time.strftime('%Y%m%d-%H%M%S')}"
    keep = {k: out[k] for k in ("events", "state", "overrides", "filename") if k in out}
    keep["summary"] = _summary(out)
    (RUNS / f"{run_id}.json").write_text(json.dumps(dict(keep, created=time.strftime("%Y-%m-%d %H:%M")),
                                                    ensure_ascii=False, default=str), encoding="utf-8")
    if pdf:
        (RUNS / f"{run_id}.pdf").write_bytes(pdf)
    return run_id


def _start_job(pdf: bytes, filename: str) -> str:
    from backend.nabo_style.ai_pipeline import run
    job_id = uuid.uuid4().hex[:10]
    job = JOBS[job_id] = dict(status="running", events=[], case=None, error=None, run_id=None, out=None)
    t0 = time.time()

    def log(step, status, text, data):
        job["events"].append(dict(t=round(time.time() - t0, 1), step=step, status=status, text=text, data=data))

    def work():
        try:
            out = run(pdf, filename=filename, log=log)
            if "state" not in out:
                job.update(status=out["status"], error=out.get("reason") or "; ".join(out.get("problems", [])))
                return
            run_id = _save_run(out, pdf)
            case = ai_case(out)
            case["ai"]["run_id"] = run_id
            job.update(out=out, case=case, run_id=run_id, status=out["status"])
        except Exception as exc:  # noqa: BLE001 — shown on the page
            job.update(status="error", error=f"{type(exc).__name__}: {exc}")

    threading.Thread(target=work, daemon=True).start()
    return job_id


def _load_run(run_id: str) -> dict:
    from backend.nabo_style.ai_pipeline import compute
    saved = _read(RUNS / f"{run_id}.json")
    out = compute(saved["state"], saved.get("overrides"))
    case = ai_case(out)
    case["ai"]["run_id"] = run_id
    return dict(events=saved["events"], case=case, run_id=run_id, created=saved.get("created"),
                reconstructed=saved.get("reconstructed", False))


def ai_runs() -> list[dict]:
    from backend.nabo_style.ai_pipeline import compute
    out = []
    for f in sorted(RUNS.glob("*.json"), key=lambda p: p.stem.split("_")[-1], reverse=True) if RUNS.exists() else []:
        d = _read(f)
        st = d["state"]
        if "summary" not in d:  # runs saved before summaries existed
            d["summary"] = _summary(compute(st, d.get("overrides")))
            f.write_text(json.dumps(d, ensure_ascii=False, default=str), encoding="utf-8")
        out.append(dict(run_id=f.stem, bill_no=st["ident"]["bill_no"],
                        title=(st["ident"].get("title") or _meta(st["ident"]["bill_no"]).get("bill_name")
                               or st["design"]["bill_title"]),
                        proposer=st["ident"].get("proposer"), propose_date=st["cutoff"],
                        created=d.get("created"), reconstructed=d.get("reconstructed", False),
                        model=st.get("model"), **d["summary"]))
    return out


def ledger_rows(rows: list[dict], cutoff: str) -> list[dict]:
    from backend.nabo_style.display import as_of_ko, by_year, clean_name, unit_ko
    return [dict(id=r["id"], name=clean_name(r["name"]), value=by_year(r), unit=unit_ko(r.get("unit")),
                 as_of=r.get("as_of") or r.get("reference_year"),
                 as_of_ko=as_of_ko(r.get("as_of") or r.get("reference_year")),
                 where=f"{r.get('publisher') or ''} {r.get('document') or ''}".strip()[:80],
                 grade=r.get("grade"), grade_key=_grade_key(r.get("grade")), published_at=r.get("published_at"),
                 quote=r.get("quote"), url=r.get("url"), note=r.get("note"),
                 provenance=ledger.provenance(r, cutoff)) for r in rows]


STATIC = ROOT.parent / "frontend/dist-nabo"
ACCESS_KEY = os.getenv("NABO_ACCESS_KEY", "")
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
         ".json": "application/json", ".png": "image/png", ".ico": "image/x-icon"}
LOGIN = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>법안 비용추계 자동화</title><style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:linear-gradient(135deg,#0b1b3f,#1d3f8f);font-family:system-ui,'Noto Sans KR',sans-serif}
form{background:#fff;border-radius:16px;padding:32px 28px;width:min(360px,calc(100vw - 32px));box-sizing:border-box;box-shadow:0 20px 50px rgba(0,0,0,.3)}
h1{font-size:20px;margin:0 0 6px}p{color:#5f6775;font-size:14px;margin:0 0 18px}
input{width:100%;box-sizing:border-box;padding:12px;border:1px solid #e2e6ee;border-radius:10px;font-size:15px}
button{margin-top:12px;width:100%;padding:12px;border:0;border-radius:10px;background:#2563eb;color:#fff;font-weight:700;font-size:15px;cursor:pointer}
.err{color:#dc2626;font-size:13px;margin:10px 0 0}</style></head><body>
<form method="post" action="/login"><h1>₩ 법안 비용추계 자동화</h1><p>접속 비밀번호를 입력하세요.</p>
<input type="password" name="key" autofocus placeholder="비밀번호">__ERR__<button>들어가기</button></form></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _authed(self) -> bool:
        if not ACCESS_KEY:
            return True
        cookies = dict(c.strip().split("=", 1) for c in (self.headers.get("Cookie") or "").split(";") if "=" in c)
        bearer = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        return ACCESS_KEY in (cookies.get("nabo_key"), self.headers.get("X-Access-Key"), bearer)

    def _html(self, body: str, status: int = 200, headers: dict | None = None) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _static(self, path: str) -> None:
        rel = path.lstrip("/") or "nabo.html"
        target = (STATIC / rel).resolve()
        if not str(target).startswith(str(STATIC.resolve())) or not target.is_file():
            target = STATIC / "nabo.html"
        if not target.exists():
            return self._json({"error": "화면 빌드가 없습니다: cd frontend && npx vite build --config vite.nabo.config.js"}, 404)
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", TYPES.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _gate(self, url) -> bool:
        """True when the request may proceed; otherwise answers with login page / 401."""
        if self._authed():
            return True
        if url.path.startswith("/api/"):
            self._json({"error": "로그인이 필요합니다."}, 401)
        else:
            self._html(LOGIN.replace("__ERR__", ""))
        return False

    def end_headers(self) -> None:
        if not ACCESS_KEY:  # local dev: vite on another port
            self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def _json(self, payload: object, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Access-Key")
        self.end_headers()

    def do_POST(self) -> None:
        from backend.nabo_style.ai_pipeline import compute
        url = urlparse(self.path)
        if url.path == "/login":
            form = parse_qs(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
            if ACCESS_KEY and form.get("key", [""])[0] == ACCESS_KEY:
                return self._html("", 303, {"Location": "/",
                                            "Set-Cookie": f"nabo_key={ACCESS_KEY}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000"})
            return self._html(LOGIN.replace("__ERR__", '<p class="err">비밀번호가 맞지 않아요.</p>'), 401)
        if not self._gate(url):
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if url.path == "/api/nabo/ai/run":
                if body.get("bill_no"):
                    path = BILLS / str(body["bill_no"]) / "bill_text.pdf"
                    if not path.exists():
                        return self._json({"error": "그 의안번호의 PDF가 없습니다."}, 404)
                    pdf, name = path.read_bytes(), path.name
                else:
                    raw = body.get("pdf_b64", "")
                    pdf, name = base64.b64decode(raw.split(",", 1)[-1]), body.get("filename", "bill.pdf")
                    if pdf[:4] != b"%PDF":
                        return self._json({"error": "PDF 파일이 아닙니다."}, 400)
                self._json({"job": _start_job(pdf, name)})
            elif url.path == "/api/nabo/ledger/ai":
                from backend.nabo_style.ledger_search import ask_ai
                cutoff = body.get("cutoff") or "9999-12-31"
                rows, how = ask_ai(body.get("q", ""), cutoff)
                self._json(dict(total=len(ledger.all_rows()), how=how, rows=ledger_rows(rows, cutoff)))
            elif url.path == "/api/nabo/ledger/web":
                from backend.nabo_style.ledger_search import web_search
                hits, how = web_search(body.get("q", ""), body.get("cutoff") or time.strftime("%Y-%m-%d"))
                self._json(dict(hits=hits, how=how))
            elif url.path == "/api/nabo/ledger/add":
                from backend.nabo_style.ledger_search import add_web_row
                row = add_web_row(body["hit"])
                self._json(dict(row=ledger_rows([row], "9999-12-31")[0]))
            elif url.path == "/api/nabo/ai/recompute":
                if body.get("job") in JOBS and JOBS[body["job"]].get("out"):
                    state = JOBS[body["job"]]["out"]["state"]
                elif body.get("run_id"):
                    state = _read(RUNS / f"{body['run_id']}.json")["state"]
                else:
                    return self._json({"error": "실행 결과를 찾지 못했습니다."}, 404)
                overrides = {k: dict(value=float(v["value"]), source=v.get("source", ""))
                             for k, v in (body.get("overrides") or {}).items() if str(v.get("value", "")).strip()}
                out = compute(state, overrides)
                run_id = body.get("run_id") or JOBS.get(body.get("job"), {}).get("run_id")
                if run_id and (RUNS / f"{run_id}.json").exists():
                    saved = _read(RUNS / f"{run_id}.json")
                    saved.update(overrides=overrides, summary=_summary(out))
                    (RUNS / f"{run_id}.json").write_text(json.dumps(saved, ensure_ascii=False, default=str),
                                                         encoding="utf-8")
                case = ai_case(out)
                case["ai"]["run_id"] = run_id
                self._json(case)
            else:
                self._json({"error": "지원하지 않는 경로입니다."}, 404)
        except Exception as exc:  # demo server: surface the reason to the page
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_GET(self) -> None:
        url = urlparse(self.path)
        if not self._gate(url):
            return
        if not url.path.startswith("/api/"):
            return self._static(url.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        tail = url.path.rsplit("/", 1)[-1]
        try:
            if url.path == "/api/nabo/cases":
                self._json([dict(id=k, label=v["label"], sub=v["sub"]) for k, v in CASES.items()])
            elif url.path.startswith("/api/nabo/case/") and tail in CASES:
                self._json(case(tail))
            elif url.path == "/api/nabo/ai/runs":
                self._json(ai_runs())
            elif url.path == "/api/nabo/ai/samples":
                self._json(dict(samples=[dict(bill_no=b, title=t, sub=d) for b, t, d in SAMPLES
                                         if (BILLS / b / "bill_text.pdf").exists()], runs=ai_runs()))
            elif url.path.startswith("/api/nabo/ai/job/"):
                job = JOBS.get(tail)
                if not job:
                    return self._json({"error": "작업을 찾지 못했습니다."}, 404)
                self._json({k: v for k, v in job.items() if k != "out"})
            elif url.path.startswith("/api/nabo/ai/pdf/"):
                path = RUNS / f"{tail}.pdf"
                if not re.fullmatch(r"[\w-]+", tail) or not path.exists():
                    return self._json({"error": "PDF가 없습니다."}, 404)
                data = path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif url.path.startswith("/api/nabo/ai/report/"):
                from backend.nabo_style.ai_pipeline import compute
                from backend.nabo_style.report import build
                if not re.fullmatch(r"[\w-]+", tail) or not (RUNS / f"{tail}.json").exists():
                    return self._json({"error": "실행 결과가 없습니다."}, 404)
                saved = _read(RUNS / f"{tail}.json")
                case = ai_case(compute(saved["state"], saved.get("overrides")))
                case["ai"]["run_id"] = tail
                data = build(case, saved["state"]).encode("utf-8")
                doc = query.get("format") == "doc"
                self.send_response(200)
                self.send_header("Content-Type", "application/msword" if doc else "text/html; charset=utf-8")
                if doc:
                    self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(f"{case['bill']['title'] or tail}_비용추계서_초안.doc"))
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif url.path.startswith("/api/nabo/ai/run/"):
                self._json(_load_run(tail))
            elif url.path == "/api/nabo/ledger":
                from backend.nabo_style.ledger_search import search
                cutoff = query.get("cutoff", "9999-12-31")
                rows, how = search(query.get("q", ""), cutoff)
                self._json(dict(total=len(ledger.all_rows()), how=how, rows=ledger_rows(rows, cutoff)))
            else:
                self._json({"error": "지원하지 않는 경로입니다."}, 404)
        except Exception as exc:  # demo server: surface the reason to the page
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def log_message(self, *_args) -> None:
        pass


def main() -> None:
    port = int(os.getenv("NABO_WEB_PORT", "8010"))
    print(f"nabo_style service on http://127.0.0.1:{port}" + (" (비밀번호 사용)" if ACCESS_KEY else ""))
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
