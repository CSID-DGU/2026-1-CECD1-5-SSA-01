"""form_renderer.py

analyzer_v2 결과를 경기도/국회 비용추계서 양식 HTML로 렌더링.

사용:
    from .form_renderer import render_form
    html = render_form(result, format="gyeonggi")
    html = render_form(result, format="assembly")
"""
from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any


# ── 공통 헬퍼 ─────────────────────────────────────────────────────────────────

def _fmt_amount(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{int(value):,}"


def _safe(text: Any) -> str:
    return escape(str(text or ""))


# ── 경기도 별지 제1호서식 ─────────────────────────────────────────────────────

def render_gyeonggi(result: dict[str, Any]) -> str:
    """경기도 의안의 비용 추계에 관한 조례 [별지 제1호서식]."""
    bill_name = _safe(result.get("billName"))
    today = datetime.now().strftime("%Y년 %m월 %d일")

    estimate = result.get("estimate") or {}
    items    = estimate.get("items") or []
    years    = estimate.get("year_estimates") or []
    non_at   = result.get("nonAttachment")
    verdict  = result.get("verdict", {})
    articles = result.get("articles", [])

    # 비용유발 조문만
    triggers = [a for a in articles if a.get("cost_trigger")]
    trigger_rows = "".join(
        f"<tr><td>{_safe(a.get('no'))}</td>"
        f"<td>{_safe(a.get('trigger_type'))}</td>"
        f"<td>{_safe(a.get('reason'))}</td></tr>"
        for a in triggers
    ) or "<tr><td colspan='3' class='empty'>해당 조문 없음</td></tr>"

    # 항목별
    item_rows = "".join(
        f"<tr>"
        f"<td>{i+1}</td>"
        f"<td>{_safe(it.get('name'))}</td>"
        f"<td>{_safe(it.get('category'))}</td>"
        f"<td>{_safe(it.get('formula'))}</td>"
        f"<td>{_safe(it.get('trigger_ref'))}</td>"
        f"</tr>"
        for i, it in enumerate(items)
    ) or "<tr><td colspan='5' class='empty'>비용 항목 없음</td></tr>"

    # 연도별
    year_rows = "".join(
        f"<tr><td>{_safe(y.get('year'))}차년도</td>"
        f"<td>{_fmt_amount(y.get('amount_thousand'))}</td>"
        f"<td>{_safe(y.get('note'))}</td></tr>"
        for y in years
    ) or "<tr><td colspan='3' class='empty'>—</td></tr>"

    # 미첨부 사유서 섹션
    non_attach_block = ""
    if non_at:
        non_attach_block = f"""
        <section class="block">
          <h3>비용추계서 미첨부 사유</h3>
          <p><strong>{_safe(non_at.get('type'))}유형</strong></p>
          <p>{_safe(non_at.get('reason_text'))}</p>
        </section>
        """

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>{bill_name} - 비용추계서 (경기도)</title>
<style>
  @page {{ size: A4; margin: 18mm; }}
  body {{ font-family: 'Noto Sans KR', sans-serif; color:#111; line-height:1.6; font-size:11pt; }}
  .header {{ text-align:center; margin-bottom: 20px; }}
  .header h1 {{ font-size: 16pt; margin: 0; letter-spacing: -0.02em; }}
  .header .subtitle {{ color: #555; font-size: 9pt; margin-top: 4px; }}
  .meta {{ display: flex; justify-content: space-between; margin-bottom: 16px; font-size: 10pt; }}
  .block {{ margin: 18px 0; }}
  .block h3 {{ font-size: 12pt; border-bottom: 2px solid #333; padding-bottom: 4px; margin-bottom: 8px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 10pt; }}
  th, td {{ border: 1px solid #999; padding: 6px 8px; text-align: left; vertical-align: top; }}
  th {{ background: #f3f4f6; font-weight: 700; }}
  td.amount {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.empty {{ text-align: center; color: #999; padding: 12px; }}
  .verdict-box {{ background: #f9fafb; border-left: 4px solid #4f46e5; padding: 12px 16px; margin: 12px 0; }}
  .verdict-box .label {{ font-weight: 700; font-size: 11pt; }}
  .signature {{ margin-top: 40px; text-align: right; font-size: 10pt; }}
  .footnote {{ font-size: 8.5pt; color: #666; margin-top: 4px; }}
</style></head>
<body>

<div class="header">
  <div class="subtitle">[별지 제1호서식] 경기도 의안의 비용 추계에 관한 조례</div>
  <h1>비 용 추 계 서</h1>
</div>

<div class="meta">
  <div><strong>의안명:</strong> {bill_name}</div>
  <div>{today}</div>
</div>

<section class="block">
  <h3>1. 종합 판단</h3>
  <div class="verdict-box">
    <div class="label">{_safe(verdict.get('label'))}</div>
    <div>{_safe(verdict.get('summary'))}</div>
    <div class="footnote">AI 분석 신뢰도: {round((verdict.get('confidence') or 0) * 100)}%</div>
  </div>
</section>

<section class="block">
  <h3>2. 재정수반요인 (비용 유발 조문)</h3>
  <table>
    <thead><tr><th style="width:18%">조항</th><th style="width:22%">유형</th><th>판단 근거</th></tr></thead>
    <tbody>{trigger_rows}</tbody>
  </table>
</section>

<section class="block">
  <h3>3. 비용항목 산출 근거</h3>
  <table>
    <thead><tr><th style="width:6%">번호</th><th>항목명</th><th style="width:12%">분류</th><th>산식</th><th style="width:18%">근거 조문</th></tr></thead>
    <tbody>{item_rows}</tbody>
  </table>
</section>

<section class="block">
  <h3>4. 5개년 추계 (단위: 천원)</h3>
  <table>
    <thead><tr><th style="width:18%">연도</th><th style="width:25%">금액</th><th>비고</th></tr></thead>
    <tbody>{year_rows}</tbody>
  </table>
</section>

{non_attach_block}

<div class="signature">
  경 기 도 의 회<br/>
  {today}
</div>

</body></html>"""


# ── 국회 별지 제2호서식 ─────────────────────────────────────────────────────────

def render_assembly(result: dict[str, Any]) -> str:
    """국회 의안의 비용추계 등에 관한 규칙 [별지 제2호서식] 비용추계서."""
    bill_name = _safe(result.get("billName"))
    today = datetime.now().strftime("%Y년 %m월 %d일")

    estimate = result.get("estimate") or {}
    items    = estimate.get("items") or []
    years    = estimate.get("year_estimates") or []
    total_years = len(years) if years else 5
    non_at   = result.get("nonAttachment")
    verdict  = result.get("verdict", {})
    articles = result.get("articles", [])

    triggers = [a for a in articles if a.get("cost_trigger")]
    trigger_rows = "".join(
        f"<tr><td>{i+1}</td>"
        f"<td>{_safe(a.get('no'))}</td>"
        f"<td>{_safe(a.get('trigger_type'))}</td>"
        f"<td>{_safe(a.get('text'))[:200]}</td></tr>"
        for i, a in enumerate(triggers)
    ) or "<tr><td colspan='4' class='empty'>해당 없음</td></tr>"

    # 항목 + 변수
    detail_rows = []
    for i, it in enumerate(items):
        vars_ = ", ".join(it.get("variables_needed") or [])
        detail_rows.append(
            f"<tr><td>{i+1}</td>"
            f"<td>{_safe(it.get('name'))}</td>"
            f"<td>{_safe(it.get('category'))}</td>"
            f"<td>{_safe(it.get('trigger_ref'))}</td>"
            f"<td>{_safe(it.get('formula'))}</td>"
            f"<td>{_safe(vars_)}</td></tr>"
        )
    detail_html = "".join(detail_rows) or "<tr><td colspan='6' class='empty'>비용 항목 없음</td></tr>"

    # 연도별
    year_header = "".join(f"<th>{y.get('year')}차년도</th>" for y in years)
    year_cells  = "".join(f"<td class='amount'>{_fmt_amount(y.get('amount_thousand'))}</td>" for y in years)
    year_notes  = "".join(f"<td>{_safe(y.get('note'))[:80]}</td>" for y in years)

    non_attach_block = ""
    if non_at:
        non_attach_block = f"""
        <section class="block">
          <h3>비용추계서 미첨부 사유</h3>
          <p><strong>{_safe(non_at.get('type'))}유형</strong></p>
          <p>{_safe(non_at.get('reason_text'))}</p>
        </section>
        """

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>{bill_name} - 비용추계서 (국회)</title>
<style>
  @page {{ size: A4; margin: 18mm; }}
  body {{ font-family: 'Noto Sans KR', sans-serif; color:#111; line-height:1.6; font-size:11pt; }}
  .header {{ text-align:center; margin-bottom: 24px; border-bottom: 3px double #333; padding-bottom: 12px; }}
  .header h1 {{ font-size: 18pt; margin: 0; letter-spacing: 0.2em; }}
  .header .subtitle {{ color: #555; font-size: 9pt; margin-top: 4px; }}
  .meta {{ display: grid; grid-template-columns: auto 1fr; gap: 6px 16px; margin-bottom: 18px; font-size: 10pt; }}
  .meta dt {{ font-weight: 700; }}
  .block {{ margin: 18px 0; }}
  .block h3 {{
    font-size: 12pt;
    border-left: 5px solid #333;
    padding-left: 8px;
    margin-bottom: 8px;
    background: #f9f9f9;
    padding: 6px 10px;
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 10pt; }}
  th, td {{ border: 1px solid #555; padding: 6px 8px; text-align: left; vertical-align: top; }}
  th {{ background: #e5e7eb; font-weight: 700; text-align: center; }}
  td.amount {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.empty {{ text-align: center; color: #999; padding: 12px; }}
  .verdict-box {{ background: #fafafa; border: 1px solid #999; padding: 12px 16px; margin: 12px 0; }}
  .verdict-box .label {{ font-weight: 700; font-size: 11pt; color: #4f46e5; }}
  .signature {{ margin-top: 40px; text-align: center; font-size: 10pt; }}
  .footnote {{ font-size: 8.5pt; color: #666; margin-top: 4px; }}
</style></head>
<body>

<div class="header">
  <div class="subtitle">[별지 제2호서식] 의안의 비용추계 등에 관한 규칙</div>
  <h1>비 용 추 계 서</h1>
</div>

<dl class="meta">
  <dt>의안명</dt><dd>{bill_name}</dd>
  <dt>작성일</dt><dd>{today}</dd>
  <dt>추계기간</dt><dd>{total_years}개년</dd>
</dl>

<section class="block">
  <h3>Ⅰ. 종합 판단</h3>
  <div class="verdict-box">
    <div class="label">{_safe(verdict.get('label'))}</div>
    <div>{_safe(verdict.get('summary'))}</div>
    <div class="footnote">AI 분석 신뢰도: {round((verdict.get('confidence') or 0) * 100)}%</div>
  </div>
</section>

<section class="block">
  <h3>Ⅱ. 재정수반요인</h3>
  <table>
    <thead><tr><th style="width:6%">연번</th><th style="width:18%">조·항</th><th style="width:18%">유형</th><th>주요 내용</th></tr></thead>
    <tbody>{trigger_rows}</tbody>
  </table>
</section>

<section class="block">
  <h3>Ⅲ. 비용추계 상세내역</h3>
  <table>
    <thead><tr>
      <th style="width:5%">번호</th>
      <th>항목명</th>
      <th style="width:10%">분류</th>
      <th style="width:14%">근거 조항</th>
      <th>산식</th>
      <th style="width:18%">필요 변수</th>
    </tr></thead>
    <tbody>{detail_html}</tbody>
  </table>
</section>

<section class="block">
  <h3>Ⅳ. 연도별 비용 추계 (단위: 천원)</h3>
  <table>
    <thead><tr>{year_header}</tr></thead>
    <tbody>
      <tr>{year_cells}</tr>
      <tr>{year_notes}</tr>
    </tbody>
  </table>
</section>

{non_attach_block}

<div class="signature">
  국 회 사 무 처 작 성<br/>
  {today}
</div>

</body></html>"""


# ── 진입점 ────────────────────────────────────────────────────────────────────

def render_form(result: dict[str, Any], format: str = "gyeonggi") -> str:
    """양식 선택해서 HTML 반환."""
    if format == "assembly":
        return render_assembly(result)
    return render_gyeonggi(result)
