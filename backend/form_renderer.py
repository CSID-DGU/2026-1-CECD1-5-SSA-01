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

    # 항목별 + KOSIS 자동조회값
    def _kosis_html(it):
        lookups = it.get("kosis_lookups") or []
        if not lookups:
            return ""
        rows = []
        for k in lookups:
            yvs = " · ".join(
                f"{yv.get('year')}: {yv.get('value')}{k.get('unit','')}"
                for yv in (k.get("year_values") or [])
            )
            rows.append(
                f"<div style='margin-top:4px'><b>{_safe(k.get('variable'))}</b> "
                f"<span style='color:#666;font-size:9pt'>({_safe(k.get('source'))})</span>"
                f"<div style='font-size:9pt;color:#333'>{_safe(yvs)}</div></div>"
            )
        return "<div style='margin-top:6px;padding:6px;background:#f0fdf4;border-left:3px solid #16a34a;font-size:9pt'><b>📊 KOSIS</b>" + "".join(rows) + "</div>"

    item_rows = "".join(
        f"<tr>"
        f"<td>{i+1}</td>"
        f"<td>{_safe(it.get('name'))}{_kosis_html(it)}</td>"
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
    """국회 비용추계서 원문 흐름에 가깝게 렌더링한다."""
    bill_name = _safe(result.get("billName"))
    today = datetime.now().strftime("%Y년 %m월 %d일")

    estimate = result.get("estimate") or {}
    items    = estimate.get("items") or []
    years    = estimate.get("year_estimates") or []
    non_at   = result.get("nonAttachment")
    articles = result.get("articles", [])
    workflow = ((result.get("workflow") or {}).get("issues") or [])

    def _million(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(round(float(value) / 1000))
        except (TypeError, ValueError):
            return None

    def _fmt_million(value: Any) -> str:
        amount = _million(value)
        return "—" if amount is None else f"{amount:,}"

    def _year_label(row: dict[str, Any]) -> str:
        return str(row.get("year_label") or row.get("calendar_year") or row.get("year") or "")

    def _article_ref(text: Any) -> str:
        raw = str(text or "")
        if raw.startswith("안 "):
            return raw
        if raw.startswith("제"):
            return f"안 {raw}"
        return raw

    def _plain(text: Any, limit: int = 240) -> str:
        cleaned = " ".join(str(text or "").split())
        return _safe(cleaned[:limit])

    def _trigger_ref_key(text: Any) -> str:
        raw = str(text or "")
        return raw.split("(")[0].replace("안", "").strip()

    def _article_reason(article: dict[str, Any], *, estimated: bool) -> str:
        rule = article.get("rule_cost_trigger") or {}
        if estimated:
            return (
                rule.get("review_reason")
                or rule.get("reason")
                or "산식과 전제값을 적용할 수 있어 비용추계 대상으로 보았습니다."
            )
        if article.get("estimate_feasibility") == "non_attachment_review":
            return (
                rule.get("review_reason")
                or "재량규정, 자료 부족 또는 구체 사업계획 미확정으로 현 단계에서 합리적 추계가 곤란합니다."
            )
        if article.get("cost_candidate_strength") == "weak":
            return "계획·조사·행정절차 성격이 강해 직접적인 추가재정소요 산정 대상에서 제외 검토합니다."
        return rule.get("review_reason") or rule.get("reason") or "추가 전제값 확인이 필요합니다."

    def _item_formula_reason(item: dict[str, Any]) -> str:
        committee = item.get("committee_formula") or {}
        if committee:
            return (
                f"회의횟수 {committee.get('meeting_count')}회 × "
                f"수당지급대상 {committee.get('paid_members')}명 × "
                f"회의수당 단가 {int(committee.get('allowance_won') or 0):,}원 = "
                f"{_fmt_million(committee.get('amount_thousand'))}백만원"
            )
        calc = item.get("calculation") or {}
        source_note = calc.get("source_note")
        if source_note:
            return str(source_note)
        template = item.get("formula_template") or {}
        return template.get("notes") or "구조화 산식과 전제값을 적용했습니다."

    def _assumption_value(item: dict[str, Any], name: str) -> Any:
        for assumption in item.get("assumptions") or []:
            if assumption.get("name") == name:
                return assumption.get("value")
        return None

    def _general_assumption_paragraphs() -> list[str]:
        if not items:
            return []
        paragraphs: list[str] = []
        special = estimate.get("applied_special_template") or {}
        if special.get("template_key") == "assembly_constitution_special_committee":
            staff_total = ((special.get("staffing") or {}).get("total")) or _assumption_value(items[0], "소요인력")
            paragraphs.append(
                "헌법특별위원회 신설에 따른 증원인력은 현 시점에서 업무량 등을 알 수 없으므로 "
                "타 상임위원회 인력 현황을 참고하여 추정함."
            )
            paragraphs.append(
                f"개정안에 따르면 헌법특별위원회 위원 정수는 30명으로, 위원 정수가 30명인 "
                f"국토교통위원회 및 산업통상자원중소벤처기업위원회 인력현황 등을 참고하여 "
                f"특별위원회 소요인력을 {staff_total}명으로 가정함."
            )
            paragraphs.append(
                "특별위원회 신설에 따라 회의 및 사무실 공간, 회의장 마련을 위한 공사비 및 비품 등이 "
                "소요될 수 있으나 국회 내 유휴공간 및 기존 예산 범위에서 충당 가능한 것으로 보아 "
                "본 추계 대상에서 제외함."
            )
            paragraphs.append(f"추계기간은 {first_year_text}부터 {last_year_text}까지 5년으로 함.")
            return paragraphs

        committee_item = next((item for item in items if item.get("committee_formula")), None)
        if committee_item:
            committee = committee_item.get("committee_formula") or {}
            meeting_count = committee.get("meeting_count")
            paid_members = committee.get("paid_members")
            allowance = committee.get("allowance_won")
            paragraphs.append(
                f"{_article_ref(committee_item.get('trigger_ref'))}에 따라 위원회를 설치·운영하는 경우 "
                "회의 참석수당 등 추가재정소요가 발생할 것으로 보아 이를 추계 대상으로 함."
            )
            if excluded_reason_html:
                paragraphs.append(
                    "다른 재정수반요인은 지원 대상, 지원 규모, 설치·운영 방식 등 구체적인 사업계획이 "
                    "확정되지 않아 합리적인 추계에 한계가 있으므로 일부 재정수반요인만 추계함."
                )
            paragraphs.append(
                f"위원회는 연 {meeting_count}회 개최하고, 수당지급대상 인원은 {paid_members}명으로 가정하며, "
                f"회의수당 단가는 1인당 {int(allowance or 0):,}원으로 가정함."
            )
            paragraphs.append(f"추계기간은 {first_year_text}부터 {last_year_text}까지 5년으로 함.")
            return paragraphs

        paragraphs.append(f"추계기간은 {first_year_text}부터 {last_year_text}까지 5년으로 함.")
        return paragraphs

    triggers = [a for a in articles if a.get("cost_trigger")]
    estimated_refs = {_trigger_ref_key(it.get("trigger_ref")) for it in items}
    year_labels = [_year_label(y) for y in years]
    year_labels = [label if len(label) == 4 else str(2025 + idx) for idx, label in enumerate(year_labels)]
    year_amounts = [_million(y.get("amount_thousand")) for y in years]
    total_million = _million(estimate.get("total_amount_thousand"))
    if total_million is None and year_amounts:
        total_million = sum(v for v in year_amounts if v is not None)
    average_million = _million(estimate.get("average_amount_thousand"))
    if average_million is None and year_amounts:
        available = [v for v in year_amounts if v is not None]
        average_million = int(round(sum(available) / len(available))) if available else None

    first_year = year_labels[0] if year_labels else "1차년도"
    last_year = year_labels[-1] if year_labels else "5차년도"
    first_year_text = f"{first_year}년" if str(first_year).isdigit() else str(first_year)
    last_year_text = f"{last_year}년" if str(last_year).isdigit() else str(last_year)
    first_amount = f"{year_amounts[0]:,}백만원" if year_amounts and year_amounts[0] is not None else "산정 불가"
    last_amount = f"{year_amounts[-1]:,}백만원" if year_amounts and year_amounts[-1] is not None else "산정 불가"
    total_text = f"{total_million:,}백만원" if total_million is not None else "산정 불가"
    avg_text = f"{average_million:,}백만원" if average_million is not None else "산정 불가"

    primary_trigger = next((a for a in triggers if a.get("cost_candidate_strength") == "strong"), triggers[0] if triggers else {})
    primary_title = str(primary_trigger.get("no") or items[0].get("trigger_ref") if items else "")
    primary_name = primary_title.split("(")[1].split(")")[0] if "(" in primary_title and ")" in primary_title else (items[0].get("name") if items else "추가재정소요")
    partial = any(
        issue.get("category") == "미첨부 가능 후보 분리"
        for issue in workflow
    )
    prefix = "(일부추계) " if partial else ""
    result_sentence = (
        f"❑{prefix}{bill_name}에 따라 {primary_name} 관련 추가재정소요는 "
        f"{first_year_text} {first_amount}, {last_year_text} {last_amount} 등 "
        f"{first_year_text}부터 {last_year_text}까지 총 {total_text}(연평균 {avg_text})으로 추계됨"
    )
    result_reason = (
        f"◦{_safe(_article_ref(primary_trigger.get('no') or (items[0].get('trigger_ref') if items else '')))}는 "
        "위원회·조직 설치 또는 운영에 관한 직접 근거로서 회의수당, 인건비 또는 운영비 발생 가능성이 있어 추계 대상으로 보았습니다."
        if primary_trigger or items else ""
    )

    cost_row_label = (
        f"{primary_name}<br><span class='small'>({_safe(_article_ref(items[0].get('trigger_ref') if items else primary_trigger.get('no')) )})</span>"
        if items or primary_trigger else "추가재정소요"
    )
    cost_table_header = "".join(f"<th>{_safe(label)}</th>" for label in year_labels)
    cost_table_cells = "".join(
        f"<td class='amount'>{'—' if value is None else f'{value:,}'}</td>"
        for value in year_amounts
    )

    trigger_rows = []
    for idx, article in enumerate(triggers, 1):
        feasibility = article.get("estimate_feasibility")
        strength = article.get("cost_candidate_strength")
        if _trigger_ref_key(article.get("no")) in estimated_refs:
            note = "의무규정"
        elif feasibility == "non_attachment_review" or strength == "weak":
            note = "추계 제외 검토"
        else:
            note = "재정수반요인"
        trigger_rows.append(
            f"<tr><td>{idx}</td>"
            f"<td>{_safe(_article_ref(article.get('no')))}</td>"
            f"<td>{_plain(article.get('text'), 360)}</td>"
            f"<td>{_safe(note)}</td></tr>"
        )
    trigger_html = "".join(trigger_rows) or "<tr><td colspan='4' class='empty'>해당 없음</td></tr>"

    estimate_review_rows = []
    for idx, article in enumerate(triggers, 1):
        is_estimated = _trigger_ref_key(article.get("no")) in estimated_refs
        if is_estimated:
            mark = "○"
            reason = _article_reason(article, estimated=True)
        elif article.get("estimate_feasibility") == "non_attachment_review":
            mark = "△"
            reason = _article_reason(article, estimated=False)
        else:
            mark = "검토"
            reason = _article_reason(article, estimated=False)
        estimate_review_rows.append(
            f"<tr><td>{idx}</td><td>{_safe(_article_ref(article.get('no')))}</td>"
            f"<td class='center'>{mark}</td><td>{_safe(reason)}</td></tr>"
        )
    estimate_review_html = "".join(estimate_review_rows) or "<tr><td colspan='4' class='empty'>해당 없음</td></tr>"

    assumption_rows = []
    for item in items:
        for assumption in item.get("assumptions") or []:
            value = assumption.get("value")
            unit = assumption.get("unit") or ""
            value_text = "확인 필요" if value is None else f"{value:,}{unit}" if isinstance(value, int) else f"{value}{unit}"
            assumption_rows.append(
                f"<tr><td>{_safe(item.get('name'))}</td>"
                f"<td>{_safe(assumption.get('name'))}</td>"
                f"<td>{_safe(value_text)}</td>"
                f"<td>{_safe(assumption.get('basis'))}</td></tr>"
            )
    assumption_html = "".join(assumption_rows) or "<tr><td colspan='4' class='empty'>전제값 없음</td></tr>"

    excluded_reason_rows = []
    for article in triggers:
        if _trigger_ref_key(article.get("no")) in estimated_refs:
            continue
        if article.get("estimate_feasibility") != "non_attachment_review" and article.get("cost_candidate_strength") != "weak":
            continue
        excluded_reason_rows.append(
            f"<tr><td>{_safe(_article_ref(article.get('no')))}</td>"
            f"<td>{_plain(article.get('text'), 220)}</td>"
            f"<td>{_safe(_article_reason(article, estimated=False))}</td></tr>"
        )
    excluded_reason_html = "".join(excluded_reason_rows)
    general_assumptions = "".join(
        f"<p class='bullet'>❑{_safe(paragraph)}</p>"
        for paragraph in _general_assumption_paragraphs()
    )

    detail_blocks = []
    for item in items:
        item_years = item.get("year_amounts_thousand") or []
        item_cells = "".join(f"<td class='amount'>{_fmt_million(v)}</td>" for v in item_years[:len(year_labels)])
        item_total = sum((_million(v) or 0) for v in item_years[:len(year_labels)]) if item_years else None
        block = [
            f"<h4>{_safe(item.get('name'))} <span class='small'>({_safe(_article_ref(item.get('trigger_ref')) )})</span></h4>",
            f"<p class='formula'>산식: {_safe(item.get('formula'))}</p>",
            f"<p class='reason'>추계 근거: {_safe(_item_formula_reason(item))}</p>",
            "<table><thead><tr>"
            + cost_table_header
            + "<th>합계</th></tr></thead><tbody><tr>"
            + item_cells
            + f"<td class='amount'>{'—' if item_total is None else f'{item_total:,}'}</td></tr></tbody></table>",
        ]
        detail_amounts = item.get("detail_amounts") or {}
        if detail_amounts:
            rows = []
            for name, values in detail_amounts.items():
                cells = "".join(f"<td class='amount'>{_safe(values.get(label, '—'))}</td>" for label in year_labels)
                rows.append(f"<tr><td>{_safe(name)}</td>{cells}</tr>")
            block.append(
                "<table class='subtable'><thead><tr><th>구분</th>"
                + cost_table_header
                + "</tr></thead><tbody>"
                + "".join(rows)
                + "</tbody></table>"
            )
        detail_blocks.append("<div class='detail-block'>" + "".join(block) + "</div>")
    detail_html = "".join(detail_blocks) or "<p class='empty'>비용 항목 없음</p>"

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
  body {{ font-family: 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif; color:#111; line-height:1.55; font-size:10.5pt; }}
  .doc-title {{ text-align:center; margin: 12px 0 18px; }}
  .doc-title .bill {{ font-size: 15pt; font-weight: 700; margin-bottom: 6px; }}
  .doc-title .label {{ font-size: 13pt; font-weight: 700; }}
  .block {{ margin: 18px 0 22px; page-break-inside: avoid; }}
  h3 {{ font-size: 12pt; margin: 0 0 8px; }}
  h4 {{ font-size: 10.5pt; margin: 12px 0 4px; }}
  .result {{ margin: 6px 0 10px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 9.5pt; margin-top: 6px; }}
  th, td {{ border: 1px solid #555; padding: 5px 6px; text-align: left; vertical-align: top; }}
  th {{ background: #f1f5f9; font-weight: 700; text-align: center; }}
  td.amount {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.center {{ text-align: center; }}
  td.empty {{ text-align: center; color: #999; padding: 12px; }}
  .unit {{ text-align:right; font-size:8.5pt; color:#444; margin-top: 2px; }}
  .small {{ font-size: 8.5pt; color:#444; font-weight: 400; }}
  .formula {{ margin: 3px 0 6px; }}
  .bullet {{ margin: 5px 0; }}
  .detail-block {{ margin-top: 10px; }}
  .subtable {{ margin-top: 6px; font-size: 9pt; }}
  .signature {{ margin-top: 40px; text-align: center; font-size: 10pt; }}
  .footnote {{ font-size: 8.5pt; color: #555; margin-top: 4px; }}
</style></head>
<body>

<div class="doc-title">
  <div class="bill">{bill_name}</div>
  <div class="label">【비용추계서】</div>
</div>

<section class="block">
  <h3>Ⅰ. 비용추계 결과</h3>
  <p class="result">{result_sentence}</p>
  <p class="reason">{result_reason}</p>
  <div class="unit">(단위: 백만원)</div>
  <table>
    <thead><tr><th>구분</th>{cost_table_header}<th>합계</th><th>연평균</th></tr></thead>
    <tbody>
      <tr><td>{cost_row_label}</td>{cost_table_cells}<td class="amount">{'—' if total_million is None else f'{total_million:,}'}</td><td class="amount">{'—' if average_million is None else f'{average_million:,}'}</td></tr>
    </tbody>
  </table>
  <p class="footnote">주: 본 추계 결과는 유사사례 및 구조화 산식 전제에 따른 것으로 실제 운영 규모 등에 따라 달라질 수 있음</p>
</section>

<section class="block">
  <h3>Ⅱ. 재정수반요인</h3>
  <table>
    <thead><tr><th style="width:6%">연번</th><th style="width:24%">조·항(조제목)</th><th>주요내용</th><th style="width:16%">비고</th></tr></thead>
    <tbody>{trigger_html}</tbody>
  </table>
</section>

<section class="block">
  <h3>Ⅲ. 비용추계의 전제와 상세내역</h3>
  <h4>1. 재정수반요인별 추계 여부</h4>
  <table>
    <thead><tr><th style="width:6%">연번</th><th>조·항(조제목)</th><th style="width:12%">추계여부</th><th>비고(추계 미실시 사유)</th></tr></thead>
    <tbody>{estimate_review_html}</tbody>
  </table>

  <h4>2. 비용추계의 총괄적 전제</h4>
  {general_assumptions}
  <table>
    <thead><tr><th style="width:24%">비용항목</th><th style="width:18%">전제</th><th style="width:18%">값</th><th>근거</th></tr></thead>
    <tbody>{assumption_html}</tbody>
  </table>

  {f'''
  <h4>2-1. 추계 제외 또는 일부추계 사유</h4>
  <table>
    <thead><tr><th style="width:24%">조·항(조제목)</th><th>주요내용</th><th>추계 제외 사유</th></tr></thead>
    <tbody>{excluded_reason_html}</tbody>
  </table>
  ''' if excluded_reason_html else ''}

  <h4>3. 재정수반요인별 상세 추계내역</h4>
  <div class="unit">(단위: 백만원)</div>
  {detail_html}
</section>

{non_attach_block}

<div class="signature">
  국회예산정책처 작성 형식 참고<br/>
  {today}
</div>

</body></html>"""


# ── 진입점 ────────────────────────────────────────────────────────────────────

def render_form(result: dict[str, Any], format: str = "gyeonggi") -> str:
    """양식 선택해서 HTML 반환."""
    if format == "assembly":
        return render_assembly(result)
    return render_gyeonggi(result)
