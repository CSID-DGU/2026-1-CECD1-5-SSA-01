"""A4 cost-estimate draft, recalculated server-side and never copied from gold."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from html import escape
import io
import os
from pathlib import Path
import re

import fitz

from backend.erce.draft_report import generate_draft

PAGE_BREAK = "<!-- ERCE_PAGE -->"
CSS = """
body { font-family: EstimateText, serif; font-size: 12pt; line-height: 1.6; color: #202020; margin: 0; padding: 0; }
h1 { font-size: 21pt; text-align: center; line-height: 1.6; }
h2 { font-size: 18pt; margin-top: 18pt; margin-bottom: 10pt; break-after: avoid; }
h3 { font-size: 12.5pt; margin-top: 18pt; break-after: avoid; }
p { margin-top: 7pt; margin-bottom: 7pt; }
table { width: 100%; border-collapse: collapse; font-size: 9pt; margin: 10pt 0; }
th, td { border-bottom: .5pt solid #b5b5b5; padding: 6pt 4pt; vertical-align: middle; }
th { background: #f0f2f4; font-weight: bold; border-top: 1pt solid #555; }
td { text-align: right; }
.left { text-align: left; }
.note { font-size: 8.5pt; color: #555; }
.caption { font-size: 9pt; text-align: center; margin-top: 10pt; break-after: avoid; }
.unit { font-size: 8pt; text-align: right; margin: 3pt 0; }
.source { font-size: 8pt; color: #555; }
.cover-table { margin-bottom: 110pt; }
.cover-table td { text-align: left; }
.cover-kind { font-size: 18pt; text-align: center; margin-top: 24pt; }
.cover-footer { margin-top: 130pt; text-align: center; color: #555; font-size: 9pt; }
tr { break-inside: avoid; }
"""


def e(value):
    return escape(str(value or ""))


def rounded(value):
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def million_won(value):
    return f"{rounded(Decimal(str(value)) / 1000000):,}"


def short_sources(values):
    numbers = list(dict.fromkeys(number for value in values for number in re.findall(r"22\d{5}", str(value))))
    if numbers:
        return " · ".join(f"의안 {number}" for number in numbers)
    return " · ".join(dict.fromkeys(str(value) for value in values if value))


def table(headers, rows, caption="", unit=""):
    output = f'<p class="caption">{e(caption)}</p>' if caption else ""
    if unit:
        output += f'<p class="unit">(단위: {e(unit)})</p>'
    output += "<table><thead><tr>" + "".join(f"<th>{e(value)}</th>" for value in headers) + "</tr></thead><tbody>"
    for row in rows:
        output += "<tr>" + "".join(f'<td class="{"left" if index == 0 or headers[index] in {"조·항", "주요 내용"} else ""}">{e(value)}</td>' for index, value in enumerate(row)) + "</tr>"
    return output + "</tbody></table>"


def bullet(value):
    return f"<p>□ {e(value)}</p>"


def child_support_detail(item, years):
    trace = item["derivationTrace"]
    variables = item.get("evidenceVariables", {})
    get = lambda key: variables.get(key, {}).get("value")
    share = lambda key: f"{(Decimal(str(get(key))) * 100).normalize():f}%" if get(key) is not None else "참고 비율"
    rows = [["장래 추계가구 수(A)", *[f"{step['households']:,}" for step in trace]]]
    gates = [
        ("minor_single_parent_share", "미성년 자녀 한부모가구 수(B)", "A"),
        ("divorced_unmarried_share", "이혼·미혼 한부모가구 수(C)", "B"),
        ("claim_holder_share", "양육비 채권 보유가구 수(D)", "C"),
        ("unpaid_claim_share", "양육비 미지급가구 수(E)", "D"),
    ]
    for key, label, previous in gates:
        rows.append([f"{label} ({previous}×{share(key)})",
                     *[f"{rounded(step['unrounded_stages'][key]):,}" for step in trace]])
    children = get("children_per_claim")
    rows.append([f"양육비 선지급 건수(F=E×{children}명)", *[f"{step['advance_cases']:,}" for step in trace]])
    output = bullet("통계 기반 가구 전망에 한부모·이혼 및 미혼·양육비 채권 보유·미지급 비율과 평균 자녀 수를 적용하여 선지급 건수를 추정함.")
    output += table(["구분", *years], rows, "[표 2] 양육비 선지급 건수 산출 내역", "가구, 건")
    output += PAGE_BREAK
    output += bullet("양육비 선지급 비용은 앞서 산출한 연도별 지원 건수에 가정한 월 지급액과 연간 지급 개월 수를 곱하여 산출함.")
    amount = get("advance_monthly_amount")
    months = get("advance_months")
    rows = [
        ["양육비 선지급 건수(A)", *[f"{step['advance_cases']:,}" for step in trace]],
        ["월 선지급액(B, 백만원)", *[f"{amount / 1000000:g}" if amount is not None else "확인 필요" for _ in years]],
        ["연간 지원 개월(C)", *[str(months) if months is not None else "확인 필요" for _ in years]],
        ["급여 지출(A×B×C)", *[million_won(step["gross_expense"]) for step in trace]],
    ]
    output += table(["구분", *years], rows, "[표 3] 양육비 선지급 비용", "건, 백만원, 개월")
    output += bullet("기존 한시적 양육비 긴급지원 사업 예산을 차감하여 추가재정소요를 산출함. 회수 수입과 지출은 상계하지 않음.")
    rows = [
        ["양육비 선지급 비용(A)", *[million_won(step["gross_expense"]) for step in trace]],
        ["기존 긴급지원 예산(B)", *[million_won(step["legacy_budget"]) for step in trace]],
        ["추가재정소요(A−B)", *[million_won(step["additional_expense"]) for step in trace]],
    ]
    return output + table(["구분", *years], rows, "[표 4] 양육비 선지급 제도 도입에 따른 추가재정소요", "백만원")


def generic_detail(item, years):
    output = bullet(f"산식: {item['formula']}")
    labels = {"annual_amount": "연간 비용", "quantity": "수량", "unit_cost": "단가",
              "recipient_count": "지원 대상자 수", "benefit_per_recipient": "1인당 지원금",
              "survey_unit_cost": "조사 단가", "recurrence_interval_years": "실시 주기"}
    for key, row in {**item["resolvedVariables"], **item.get("evidenceVariables", {})}.items():
        value = row["value"]
        label = labels.get(key, key)
        if isinstance(value, list):
            # Do not assign forecast years to historical series without evidence.
            is_annual = key in {"annual_amount", "annual_project_budget"} and len(value) == len(years)
            headings = years if is_annual else [f"자료 {index+1}" for index in range(len(value))]
            output += table(["구분", "값"], [[heading, f"{v:,}" if isinstance(v, (int, float)) else str(v)]
                for heading, v in zip(headings, value)], label, row["unit"])
        elif isinstance(value, dict):
            output += table(["구분", "값"], [[k, str(v)] for k, v in value.items()], label, row["unit"])
        else:
            shown = f"{value:,}" if isinstance(value, (int, float)) else str(value)
            output += bullet(f"{label}: {shown} {row['unit']}")
    return output


def render_draft_html(report, payload):
    title = report["title"]
    start, count = report["startYear"], report["years"]
    years = [str(start + index) for index in range(count)]
    cover = '<table class="cover-table"><tr><th>의안번호</th><td>' + e(payload.get("bill_no") or "확인 필요")
    cover += '</td><th>작성일</th><td>' + date.today().isoformat() + '</td></tr><tr><th>문서 구분</th><td colspan="3">검토용 자동 생성 초안</td></tr></table>'
    cover += f'<h1>{e(title)}</h1><p class="cover-kind">【비용추계서 초안】</p>'
    cover += '<p class="cover-footer">ERCE 비용추계 시스템<br/>공식 비용추계서가 아니며, 입력값과 적용 가정에 대한 검토가 필요합니다.</p>'
    body = '<h2>Ⅰ. 비용추계 결과</h2>'
    total = report["totalAmountThousand"]
    body += bullet(f"선택한 {len(report['items'])}개 비용 항목의 추가재정소요는 {start}년부터 {start+count-1}년까지 {count}년간 총 {million_won(total*1000)}백만원(연평균 {million_won(total*1000/count)}백만원)으로 추계됨.")
    body += '<p class="note">아래 금액은 선택한 범위와 가정에 따른 검토용 추계이며, 미산출 항목을 0원으로 판단한 것은 아님.</p>'
    rows = []
    for item in report["items"]:
        values = item["annualAmountsThousand"]
        rows.append([item["name"], *[million_won(value*1000) for value in values],
                     million_won(sum(values)*1000), million_won(sum(values)*1000/count)])
    rows.append(["합계", *[million_won(value*1000) for value in report["annualAmountsThousand"]],
                 million_won(total*1000), million_won(total*1000/count)])
    body += table(["구분", *years, "합계", "연평균"], rows,
                  f"[표 1] 추가재정소요 추계: {start}~{start+count-1}년", "백만원")
    body += '<p class="source">자료: ERCE 산출 결과 · 반올림으로 합계에 차이가 있을 수 있음</p>'
    body += '<h2>Ⅱ. 재정수반요인</h2>'
    raw_items = payload["items"]
    body += table(["연번", "조·항", "주요 내용"], [
        [index+1, item["triggerRef"] or "확인 필요", raw_items[index].get("source_quote") or raw_items[index].get("change_summary") or item["name"]]
        for index, item in enumerate(report["items"])])
    body += PAGE_BREAK + '<h2>Ⅲ. 비용추계의 전제와 상세내역</h2><h3>1. 재정수반요인별 추계 여부</h3>'
    body += table(["연번", "조·항", "추계 여부"], [[index+1, item["triggerRef"] or item["name"], "추계"]
        for index, item in enumerate(report["items"])])
    body += '<h3>2. 비용추계의 총괄적 전제</h3>'
    body += bullet(f"추계기간은 {start}년부터 {start+count-1}년까지 {count}년간으로 함.")
    for item in report["items"]:
        if item.get("documentAssumptions"):
            for note in item["documentAssumptions"]:
                body += bullet(note)
            continue
        if item.get("referenceNotice"):
            body += bullet(item["referenceNotice"])
        for method in item["selectedMethods"]:
            for note in dict.fromkeys(method["confirmed_assumptions"].values()):
                body += bullet(note)
    body += PAGE_BREAK + '<h3>3. 재정수반요인별 상세 추계내역</h3>'
    for index, item in enumerate(report["items"]):
        sections = ["가", "나", "다", "라", "마", "바", "사", "아", "자", "차", "카", "타", "파", "하"]
        section = sections[index] if index < len(sections) else str(index+1)
        body += f'<h3>{e(section)}. {e(item["name"])}</h3>'
        child = bool(item["derivationTrace"]) and all("advance_cases" in row for row in item["derivationTrace"])
        body += child_support_detail(item, years) if child else generic_detail(item, years)
        refs = short_sources(item["sourceRefs"])
        body += f'<p class="source">참고 근거: {e(refs or "입력된 값 및 의안 원문")}</p>'
    body += PAGE_BREAK + '<h2>Ⅳ. 부대의견</h2>'
    body += bullet("이 초안은 선택한 근거 및 가정에 따른 결과로, 실제 대상자 수·신청 및 선정률·지급액·시행시점 등에 따라 재정소요가 달라질 수 있음.")
    if any(item["derivationTrace"] and "advance_cases" in item["derivationTrace"][0] for item in report["items"]):
        body += bullet("선지급한 양육비의 회수에 따른 수입은 지출에서 상계하지 않았으며, 실제 회수액에 따라 정부의 재정부담은 달라질 수 있음.")
    if report["exclusions"]:
        body += '<h3>계산 시 참고할 내용</h3>'
        for note in report["exclusions"]:
            body += bullet(note)
    body += PAGE_BREAK + '<h2>Ⅴ. 작성 정보</h2>' + bullet(f"작성 시스템: ERCE / 작성일: {date.today().isoformat()}")
    body += bullet("검토용 자동 생성 초안. 국회예산정책처의 공식 회답 문서가 아니며 공식 추계번호·담당자 정보는 부여하지 않음.")
    return cover, body


def _story_pdf(html):
    stream = io.BytesIO()
    writer = fitz.DocumentWriter(stream)
    media = fitz.paper_rect("a4")
    bounds = media + (85, 70, -80, -60)
    try:
        font = Path(os.getenv("ERCE_PDF_FONT", "/System/Library/Fonts/Supplemental/AppleMyungjo.ttf"))
        css = CSS
        archive = None
        if font.is_file():
            archive = fitz.Archive(str(font.parent))
            css = f'@font-face {{ font-family: EstimateText; src: url("{font.name}"); }}\n' + CSS
        story = fitz.Story(html=html, user_css=css, archive=archive)
        story.write(writer, lambda _n, _filled: (media, bounds, None))
    finally:
        writer.close()
    return fitz.open(stream=stream.getvalue(), filetype="pdf")


def generate_draft_pdf(payload):
    report = generate_draft(payload)
    if report.get("status") != "draft_ready":
        raise ValueError("아직 계산하지 못한 항목이 있어요. 필요한 값을 확인한 뒤 PDF를 만들어 주세요.")
    cover_html, body_html = render_draft_html(report, payload)
    with _story_pdf(cover_html) as pdf:
        cover_pages = pdf.page_count
        for part in body_html.split(PAGE_BREAK):
            if not part.strip():
                continue
            with _story_pdf(part) as body:
                pdf.insert_pdf(body)
        for index in range(cover_pages, pdf.page_count):
            page = pdf[index]
            page.insert_textbox(fitz.Rect(230, 791, 365, 812), f"- {index-cover_pages+1} -",
                                fontsize=9, fontname="helv", align=1, color=(.4,.4,.4))
        pdf.set_metadata({"title": report["title"] + " 비용추계서 초안", "author": "ERCE", "subject": "검토용 자동 생성 초안"})
        pdf.subset_fonts()
        return pdf.tobytes(garbage=4, deflate=True)
