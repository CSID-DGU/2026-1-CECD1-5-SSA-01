"""비용추계서 초안 (NABO 회답서 체계) — HTML, printable to PDF and openable in Word.

Layout follows NABO estimates: 머리표(의안번호·의뢰인·회답일·추계번호) → Ⅰ. 비용추계 결과
(❑ 요약문 + [표 1] 연도별, 단위 백만원) → Ⅱ. 재정수반요인 → Ⅲ. 비용추계의 전제와 상세내역
(추계 여부표, 총괄적 전제 + 각주 자료, 산식·연도별 상세) → Ⅳ. 검토 필요 사항.
Every sentence is generated from the verified run (no model call here), so the draft can
never state a number that is not in the calculation.
"""
from __future__ import annotations

import html
import re
import time

E = html.escape


def _won_text(won: float) -> str:
    """13,322,743,000,000 → '13조 3,227억 4,300만원' (NABO 본문 표기)."""
    n = round(won / 1e4)  # 만원
    jo, rest = divmod(n, 10 ** 8)
    eok, man = divmod(rest, 10 ** 4)
    parts = ([f"{jo:,}조"] if jo else []) + ([f"{eok:,}억"] if eok else []) + ([f"{man:,}만"] if man else [])
    return (" ".join(parts) or "0") + "원"


def _mil(won: float) -> str:
    return f"{round(won / 1e6):,}"


def _value(v, unit: str) -> str:
    if isinstance(v, dict) and "national" in v:
        return f"국가 {v['national']:.0%} · 지방자치단체 {v['local']:.0%}"
    if isinstance(v, dict):
        return ", ".join(f"{k}년 {x:,.0f}" for k, x in v.items()) + f" {unit}"
    if isinstance(v, list):
        return " ~ ".join(f"{x:,.0f}" for x in v) + f" {unit}"
    if isinstance(v, float) and abs(v) < 1:
        return f"{v:.2%}"
    return f"{abs(v):,.0f} {unit}" if isinstance(v, (int, float)) else f"{v} {unit}"


def build(case: dict, state: dict) -> str:
    design = state["design"]
    title = case["bill"]["title"] or design["bill_title"]
    kind = "개정안" if "개정" in title else "제정안"
    scen = list(case["scenarios"].items())
    main_name, main = scen[0]
    years = sorted(main["by_year"])
    span = f"{years[0]}년" if len(years) == 1 else f"{years[0]}년부터 {years[-1]}년까지 {len(years)}년간"
    groups = [g for g in design["groups"] if g["sign"] > 0]
    amount = groups[0] if groups else design["groups"][0]
    amt_txt = (f"{amount['amount_min_won']:,}원" if amount["amount_min_won"] == amount["amount_max_won"]
               else f"{amount['amount_min_won']:,}원~{amount['amount_max_won']:,}원")
    per = "매월 " if amount["times_per_year"] == 12 else ""
    single = "(단년도 추계)" if len(years) == 1 else f"(연평균 {_won_text(main['total'] / len(years))})"
    if len(scen) > 1 and scen[1][0] == "상한":
        total_txt = f"{_won_text(main['total'])}(하한) ~ {_won_text(scen[1][1]['total'])}(상한)"
    else:
        total_txt = f"총 {_won_text(main['total'])}{single}" if len(years) > 1 else f"{_won_text(main['total'])}{single}"
    lead = (f"{kind}에 따라 지급대상자에게 1인당 {per}{amt_txt}을 지급할 경우 추가재정소요는 "
            f"{span} {total_txt}으로 추계됨")
    split = main.get("national"), main.get("local")

    # Ⅰ [표 1]
    head = "".join(f"<th>{y}</th>" for y in years) + ("<th>합계</th>" if len(years) > 1 else "")
    rows = []
    for name, sc in scen:
        label = "추가재정소요" if len(scen) == 1 else f"추가재정소요({name})"
        cells = "".join(f"<td>{_mil(sc['by_year'][y])}</td>" for y in years)
        rows.append(f"<tr><th>{E(label)}</th>{cells}{f'<td>{_mil(sc['total'])}</td>' if len(years) > 1 else ''}</tr>")
    if split[1]:
        ratio = split[0] / main["total"] if main["total"] else 0
        for label, r in (("국비", ratio), ("지방비", 1 - ratio)):
            cells = "".join(f"<td>{_mil(main['by_year'][y] * r)}</td>" for y in years)
            tot = f"<td>{_mil(main['total'] * r)}</td>" if len(years) > 1 else ""
            rows.append(f"<tr class='sub'><th>{label}({r:.0%})</th>{cells}{tot}</tr>")

    # Ⅱ 재정수반요인
    fin = "".join(
        f"<tr><td>{i}</td><td>안 {E(c['id'])}</td><td>{E(c['quote'])}</td><td>{E(c.get('role') or '')}</td></tr>"
        for i, c in enumerate(case["clauses"], 1))

    # Ⅲ-1 추계 여부
    est_rows = [f"<tr><td>{i}</td><td>안 {E(c['id'])}</td><td class='c'>○</td><td>-</td></tr>"
                for i, c in enumerate([c for c in case["clauses"] if c.get("role") in ("지급대상", "지급액")], 1)]
    n0 = len(est_rows)
    est_rows += [f"<tr><td>{n0 + i}</td><td>{E(e['item'])}</td><td class='c'>×</td><td>{E(e['reason'])}</td></tr>"
                 for i, e in enumerate(case["not_estimated"], 1)]

    # Ⅲ-2 총괄적 전제 (+각주)
    notes, premises = [], []
    for s in case["sources"]:
        if s["grade_key"] == "bill":
            continue
        notes.append(f"자료: {s['origin']}" + (f" ({s['url']})" if s.get("url") else ""))
        why = re.split(r" · ((GPT|AI) 선택 이유|원장에 없어 (GPT|AI) 웹 검색)", s.get("why") or "")[0]
        why = re.sub(r"\s*·\s*한계:.*", "", why)
        limit = re.search(r"한계:\s*(.*)", s.get("why") or "")
        note = "" if "정답" in (s.get("note") or "") else s.get("note") or ""
        premises.append(
            f"<p class='q'>❑ {E(s['name'])}은(는) {E(_value(s['value'], s['unit'] if s['unit'] != 'ratio' else ''))}"
            f"<sup>{len(notes)})</sup>을 적용함</p>"
            + (f"<p class='d'>◦ {E(why)}</p>" if why else "")
            + (f"<p class='d'>－ 한계: {E(limit.group(1))}</p>" if limit else "")
            + (f"<p class='d'>－ 유의사항: {E(note)}</p>" if note else ""))
    premises.append(f"<p class='q'>❑ 추계기간은 {E(span)}으로 설정함</p>"
                    f"<p class='d'>◦ {E(design.get('payment_years_why', ''))}</p>")
    for e in case["not_estimated"]:
        premises.append(f"<p class='q'>❑ {E(e['item'])}은(는) 추계에서 제외함</p><p class='d'>◦ {E(e['reason'])}</p>")

    # Ⅲ-3 상세 계산
    detail = []
    for g in design["groups"]:
        src = next((s for s in case["sources"] if s["name"] == f"{g['name']} 대상자 수"), None)
        people = src["value"] if src else None
        lo, hi = g["amount_min_won"], g["amount_max_won"]
        detail.append(
            f"<tr><td>{'－' if g['sign'] < 0 else '＋'} {E(g['name'])}</td>"
            f"<td>{E(_value(people, '명')) if people is not None else '근거 없음'}</td>"
            f"<td>{lo:,}{'' if lo == hi else f'~{hi:,}'}원"
            f"{' × 12개월' if g['times_per_year'] == 12 else ''}</td><td>안 {E(g['amount_clause_id'])}</td></tr>")

    # Ⅳ 검토 필요
    review = [f"<li>{E(c['item'])}: {E(c['text'])}</li>" for c in case["ai"]["checks"] if not c["ok"]]
    review += [f"<li>{E(s['name'])}: 근거 등급 ‘{E(s['grade'])}’ — 원 통계로 대체 검토 필요</li>"
               for s in case["sources"] if s["grade_key"] in ("assumption", "missing")]
    review += [f"<li>{E(n['name'])}: 사용자 입력 필요 — {E(n['reason'])}</li>" for n in case["ai"]["needs_input"]]

    today = time.strftime("%Y. %-m. %-d.")
    draft_no = f"AI-{case['ai'].get('run_id', 'draft')}"
    foot = "".join(f"<li>{E(n)}</li>" for n in notes)
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>{E(title)} 비용추계서(초안)</title>
<style>
@page {{ size: A4; margin: 22mm 20mm; }}
body {{ font-family: 'Batang','Noto Serif KR','Malgun Gothic',serif; color:#111; max-width: 820px; margin: 24px auto; padding: 0 16px; line-height: 1.75; font-size: 14.5px; background:#fff; }}
.bar {{ position: sticky; top: 0; background:#fff; border-bottom:1px solid #ddd; padding:10px 0; display:flex; gap:8px; justify-content:flex-end; font-family: system-ui,sans-serif; }}
.bar button, .bar a {{ font: 600 13px system-ui; border:1px solid #1d3f8f; background:#1d3f8f; color:#fff; border-radius:8px; padding:7px 14px; cursor:pointer; text-decoration:none; }}
.bar a {{ background:#fff; color:#1d3f8f; }}
.draft {{ font-family: system-ui,sans-serif; font-size:12px; color:#b45309; border:1px solid #f59e0b; background:#fffbeb; padding:6px 10px; border-radius:6px; margin:12px 0; }}
table {{ border-collapse: collapse; width:100%; margin: 8px 0 4px; font-size: 13px; }}
th, td {{ border:1px solid #444; padding:5px 7px; vertical-align: top; }}
thead th, table.meta th {{ background:#eef1f6; }}
td {{ text-align: right; }} td:nth-child(n) {{ text-align: left; }} .num td {{ text-align:right; }} .num th {{ text-align:left; }}
tr.sub th {{ font-weight: normal; padding-left: 18px; }}
.c {{ text-align:center; }}
td:first-child {{ white-space: nowrap; }} table td:nth-child(2) {{ min-width: 84px; }} table td:last-child {{ min-width: 64px; }}
table.meta {{ width: auto; margin-left:auto; font-size: 12.5px; }}
h1 {{ text-align:center; font-size: 22px; margin: 26px 0 2px; }} .sub-t {{ text-align:center; margin:0 0 26px; letter-spacing: .3em; }}
h2 {{ font-size: 17px; margin: 30px 0 8px; }} h3 {{ font-size: 15px; margin: 20px 0 6px; }}
p.q {{ margin: 10px 0 2px; }} p.d {{ margin: 0 0 0 18px; }}
.cap {{ font-size: 13px; display:flex; justify-content:space-between; margin-top: 12px; }}
.note {{ font-size: 12px; color:#333; }}
ol.foot {{ font-size: 11.5px; color:#333; padding-left: 20px; border-top:1px solid #999; padding-top:8px; margin-top: 28px; }}
ol.foot li {{ word-break: break-all; }}
@media print {{ .bar {{ display:none; }} body {{ margin:0; max-width:none; }} }}
</style></head><body>
<div class="bar"><a href="?format=doc">Word로 받기(.doc)</a><button onclick="window.print()">PDF로 저장 / 인쇄</button></div>
<table class="meta"><tr><th>의안번호</th><td>{E(case['bill']['no'])}</td><th>의뢰인</th><td>{E((case['bill'].get('proposer') or '').split(' 등')[0].split(' 외')[0])}</td></tr>
<tr><th>작성일</th><td>{today}</td><th>추계번호</th><td>{E(draft_no)}</td></tr></table>
<h1>{E(title)}</h1><p class="sub-t">【비용추계서(초안)】</p>
<p class="draft">자동 생성 초안입니다. 모든 숫자는 의안 원문·기준정보 원장·원문을 확인한 자료에서만 왔으며, 담당자 검토 후 확정해야 합니다.</p>

<h2>Ⅰ. 비용추계 결과</h2>
<p class="q">❑ {E(lead)}</p>
{f"<p class='d'>◦ (국비) {_won_text(split[0])} · (지방비) {_won_text(split[1])}</p>" if split[1] else ""}
<div class="cap"><span>[표 1] {kind}에 따른 추가재정소요: {years[0]}{'' if len(years) == 1 else '~' + years[-1]}년</span><span>(단위: 백만원)</span></div>
<table class="num"><thead><tr><th>구분</th>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>
<p class="note">주: 본 추계 결과는 지급대상자 수 및 1인당 지급금액에 대한 가정을 바탕으로 작성한 것으로, 실제 지급대상자 수 및 지급금액에 따라 재정소요액은 달라질 수 있음</p>

<h2>Ⅱ. 재정수반요인</h2>
<table><thead><tr><th>연번</th><th>조·항</th><th>주요내용</th><th>비고</th></tr></thead><tbody>{fin}</tbody></table>

<h2>Ⅲ. 비용추계의 전제와 상세내역</h2>
<h3>1. 재정수반요인별 추계 여부</h3>
<table><thead><tr><th>연번</th><th>조·항(항목)</th><th>추계여부</th><th>비고(추계 미실시 사유)</th></tr></thead><tbody>{''.join(est_rows)}</tbody></table>
<h3>2. 비용추계의 총괄적 전제</h3>
{''.join(premises)}
<h3>3. 추계 산식 및 상세내역</h3>
<p class="q">❑ {E(case['formula']['text'])}</p>
<table><thead><tr><th>대상 그룹</th><th>대상자 수</th><th>1인당 지급액</th><th>근거 조문</th></tr></thead><tbody>{''.join(detail)}</tbody></table>

<h2>Ⅳ. 검토 필요 사항</h2>
{'<ul>' + ''.join(review) + '</ul>' if review else '<p>자동 검증에서 확인이 필요한 항목이 없음</p>'}
<ol class="foot">{foot}</ol>
<p class="note">작성: 비용추계 자동화 시스템 (조문 분석·근거 선택 AI {E(state.get('model', ''))}, 계산·검증 코드) · 검토자: ________</p>
</body></html>"""
