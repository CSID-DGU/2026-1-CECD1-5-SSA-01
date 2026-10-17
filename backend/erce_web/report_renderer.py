from __future__ import annotations

from html import escape
from pathlib import Path

from .config import GENERATED_DIR
from .knowledge_base import YEARS


def _format_amount(value: int) -> str:
    return f"{value:,}"


def render_report_html(result: dict[str, object], report_title: str) -> str:
    sections = result["sections"]
    yearly_totals = result["yearlyTotals"]
    funding_plan = result["fundingPlan"]
    items = result["items"]

    item_rows = []
    for item in items:
        year_cells = "".join(
            f"<td>{_format_amount(amount)}</td>" for amount in item["yearlyAmounts"]
        )
        item_rows.append(
            "<tr>"
            f"<td>{escape(item['category'])}</td>"
            f"<td>{escape(item['item'])}</td>"
            f"<td>{escape(item['formula'])}</td>"
            f"<td>{escape(item['legalBasis'])}</td>"
            f"{year_cells}"
            f"<td>{_format_amount(item['amount'])}</td>"
            "</tr>"
        )

    funding_rows = []
    for row in funding_plan["rows"]:
        year_cells = "".join(f"<td>{_format_amount(amount)}</td>" for amount in row["amounts"])
        funding_rows.append(
            "<tr>"
            f"<td>{escape(row['label'])}</td>"
            f"{year_cells}"
            f"<td>{_format_amount(row['total'])}</td>"
            "</tr>"
        )

    evidence_rows = []
    for ev in result["evidences"]:
        evidence_rows.append(
            "<tr>"
            f"<td>{escape(ev['tag'])}</td>"
            f"<td>{escape(ev['source'])}</td>"
            f"<td>{escape(ev['detail'])}</td>"
            f"<td>{escape(ev['highlight'])}</td>"
            "</tr>"
        )

    year_headers = "".join(f"<th>{year}</th>" for year in YEARS)
    total_cells = "".join(f"<td>{_format_amount(amount)}</td>" for amount in yearly_totals)

    factors = "".join(f"<li>{escape(text)}</li>" for text in sections["financialFactors"])
    assumptions = "".join(f"<li>{escape(text)}</li>" for text in sections["assumptions"])
    cooperation = "".join(f"<li>{escape(text)}</li>" for text in sections["cooperationNotes"])

    html = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(report_title)}</title>
  <style>
    body {{
      font-family: "Noto Sans KR", "Apple SD Gothic Neo", sans-serif;
      margin: 32px;
      color: #111827;
      line-height: 1.6;
      background: #f8fafc;
    }}
    .page {{
      max-width: 1120px;
      margin: 0 auto;
      background: white;
      padding: 40px 44px;
      box-shadow: 0 20px 60px rgba(15, 23, 42, 0.08);
      border: 1px solid #e5e7eb;
    }}
    h1 {{
      font-size: 28px;
      margin-bottom: 8px;
    }}
    h2 {{
      font-size: 20px;
      margin: 28px 0 12px;
      padding-bottom: 6px;
      border-bottom: 2px solid #111827;
    }}
    p.meta {{
      color: #475569;
      font-size: 14px;
      margin-top: 0;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 12px;
    }}
    th, td {{
      border: 1px solid #cbd5e1;
      padding: 8px 10px;
      font-size: 13px;
      vertical-align: top;
    }}
    th {{
      background: #e2e8f0;
      text-align: center;
    }}
    ul {{
      margin: 10px 0 0 20px;
      padding: 0;
    }}
    .small {{
      color: #64748b;
      font-size: 12px;
    }}
    .total-row {{
      font-weight: 700;
      background: #f8fafc;
    }}
    .writer {{
      margin-top: 24px;
      padding: 16px;
      background: #f8fafc;
      border: 1px solid #cbd5e1;
    }}
    @media print {{
      body {{
        margin: 0;
        background: white;
      }}
      .page {{
        box-shadow: none;
        border: none;
        max-width: none;
        padding: 18mm 16mm;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <div class="small">■ 경기도 의안의 비용 추계에 관한 조례 [별지 제1호서식] 기반 MVP 출력</div>
    <h1>{escape(report_title)}</h1>
    <p class="meta">{escape(result['billName'])} / 생성시각 {escape(result['generatedAt'])}</p>

    <h2>1. 재정수반요인</h2>
    <ul>{factors}</ul>

    <h2>2. 비용추계의 전제</h2>
    <ul>{assumptions}</ul>

    <h2>3. 비용추계의 결과</h2>
    <table>
      <thead>
        <tr>
          <th>구분</th>
          <th>비용 항목</th>
          <th>산출식</th>
          <th>관련 조문</th>
          {year_headers}
          <th>합계</th>
        </tr>
      </thead>
      <tbody>
        {''.join(item_rows)}
        <tr class="total-row">
          <td colspan="4">총 비용</td>
          {total_cells}
          <td>{_format_amount(result['totalCost'])}</td>
        </tr>
      </tbody>
    </table>

    <h2>4. 비용추계의 상세내역</h2>
    <p>{escape(sections['detailedBreakdown'])}</p>

    <h2>5. 재원조달 방안</h2>
    <table>
      <thead>
        <tr>
          <th>구분</th>
          {year_headers}
          <th>합계</th>
        </tr>
      </thead>
      <tbody>
        {''.join(funding_rows)}
      </tbody>
    </table>
    <p><strong>2) 재원조달의 구체적 방안</strong><br />{escape(funding_plan['detail'])}</p>
    <p><strong>3) 협의사항</strong></p>
    <ul>{cooperation}</ul>

    <h2>근거 추적</h2>
    <table>
      <thead>
        <tr>
          <th>유형</th>
          <th>출처</th>
          <th>설명</th>
          <th>하이라이트</th>
        </tr>
      </thead>
      <tbody>
        {''.join(evidence_rows)}
      </tbody>
    </table>

    <div class="writer">
      <strong>6. 작성자</strong><br />
      {escape(result['writer']['department'])} / {escape(result['writer']['name'])} / {escape(result['writer']['contact'])}
    </div>
  </div>
</body>
</html>
"""
    return html


def save_report_html(filename: str, html: str) -> Path:
    output_path = GENERATED_DIR / filename
    output_path.write_text(html, encoding="utf-8")
    return output_path

