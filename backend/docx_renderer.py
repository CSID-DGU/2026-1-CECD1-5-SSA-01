from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from .config import GENERATED_DIR
from .knowledge_base import YEARS

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _xml_header() -> str:
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'


def _paragraph(text: str, *, bold: bool = False) -> str:
    bold_tag = "<w:b/>" if bold else ""
    preserve = ' xml:space="preserve"' if text.startswith(" ") or text.endswith(" ") else ""
    return (
        "<w:p><w:r>"
        f"<w:rPr>{bold_tag}</w:rPr>"
        f"<w:t{preserve}>{escape(text)}</w:t>"
        "</w:r></w:p>"
    )


def _table(cells: list[list[str]], widths: list[int] | None = None) -> str:
    width_xml = ""
    if widths:
        width_xml = "".join(
            f'<w:gridCol w:w="{width}"/>' for width in widths
        )
        width_xml = f"<w:tblGrid>{width_xml}</w:tblGrid>"

    rows_xml = []
    for row in cells:
        cell_xml = []
        for cell in row:
            cell_xml.append(
                "<w:tc>"
                "<w:tcPr><w:tcW w:w=\"0\" w:type=\"auto\"/></w:tcPr>"
                f"{_paragraph(cell)}"
                "</w:tc>"
            )
        rows_xml.append("<w:tr>" + "".join(cell_xml) + "</w:tr>")

    return (
        "<w:tbl>"
        "<w:tblPr>"
        "<w:tblStyle w:val=\"TableGrid\"/>"
        "<w:tblW w:w=\"0\" w:type=\"auto\"/>"
        "<w:tblBorders>"
        "<w:top w:val=\"single\" w:sz=\"8\" w:space=\"0\" w:color=\"auto\"/>"
        "<w:left w:val=\"single\" w:sz=\"8\" w:space=\"0\" w:color=\"auto\"/>"
        "<w:bottom w:val=\"single\" w:sz=\"8\" w:space=\"0\" w:color=\"auto\"/>"
        "<w:right w:val=\"single\" w:sz=\"8\" w:space=\"0\" w:color=\"auto\"/>"
        "<w:insideH w:val=\"single\" w:sz=\"8\" w:space=\"0\" w:color=\"auto\"/>"
        "<w:insideV w:val=\"single\" w:sz=\"8\" w:space=\"0\" w:color=\"auto\"/>"
        "</w:tblBorders>"
        "</w:tblPr>"
        f"{width_xml}"
        f"{''.join(rows_xml)}"
        "</w:tbl>"
    )


def _document_xml(result: dict[str, object], report_title: str) -> str:
    sections = result["sections"]
    items = result["items"]
    funding_plan = result["fundingPlan"]
    evidences = result["evidences"]
    yearly_totals = result["yearlyTotals"]

    body = []
    body.append(_paragraph("■ 경기도 의안의 비용 추계에 관한 조례 [별지 제1호서식]"))
    body.append(_paragraph(report_title, bold=True))
    body.append(_paragraph(f"의안명: {result['billName']}"))
    body.append(_paragraph(f"생성시각: {result['generatedAt']}"))

    body.append(_paragraph("1. 재정수반요인", bold=True))
    for line in sections["financialFactors"]:
        body.append(_paragraph(f"• {line}"))

    body.append(_paragraph("2. 비용추계의 전제", bold=True))
    for line in sections["assumptions"]:
        body.append(_paragraph(f"• {line}"))

    body.append(_paragraph("3. 비용추계의 결과 (단위: 천원)", bold=True))
    result_rows = [["구분", "비용 항목", "산출식", "관련 조문", *YEARS, "합계"]]
    for item in items:
        result_rows.append(
            [
                item["category"],
                item["item"],
                item["formula"],
                item["legalBasis"],
                *[f"{amount:,}" for amount in item["yearlyAmounts"]],
                f"{item['amount']:,}",
            ]
        )
    result_rows.append(
        ["총 비용", "", "", "", *[f"{amount:,}" for amount in yearly_totals], f"{result['totalCost']:,}"]
    )
    body.append(_table(result_rows))

    body.append(_paragraph("4. 비용추계의 상세내역", bold=True))
    body.append(_paragraph(sections["detailedBreakdown"]))

    body.append(_paragraph("5. 재원조달 방안", bold=True))
    body.append(_paragraph("1) 부문별 재원분담계획 (단위: 천원)"))
    funding_rows = [["구분", *YEARS, "합계"]]
    for row in funding_plan["rows"]:
        funding_rows.append([row["label"], *[f"{amount:,}" for amount in row["amounts"]], f"{row['total']:,}"])
    body.append(_table(funding_rows))
    body.append(_paragraph("2) 재원조달의 구체적 방안"))
    body.append(_paragraph(funding_plan["detail"]))
    body.append(_paragraph("3) 협의사항"))
    for line in sections["cooperationNotes"]:
        body.append(_paragraph(f"• {line}"))

    body.append(_paragraph("6. 작성자", bold=True))
    body.append(
        _paragraph(
            f"{result['writer']['department']} / {result['writer']['name']} / {result['writer']['contact']}"
        )
    )

    body.append(_paragraph("첨부: 근거 추적", bold=True))
    evidence_rows = [["유형", "출처", "설명", "하이라이트"]]
    for evidence in evidences:
        evidence_rows.append(
            [
                evidence["tag"],
                evidence["source"],
                evidence["detail"],
                evidence["highlight"][:200],
            ]
        )
    body.append(_table(evidence_rows))

    sect_pr = (
        "<w:sectPr>"
        "<w:pgSz w:w=\"11906\" w:h=\"16838\"/>"
        "<w:pgMar w:top=\"1440\" w:right=\"1440\" w:bottom=\"1440\" w:left=\"1440\" "
        "w:header=\"720\" w:footer=\"720\" w:gutter=\"0\"/>"
        "</w:sectPr>"
    )

    return (
        _xml_header()
        + f'<w:document xmlns:w="{W_NS}"><w:body>'
        + "".join(body)
        + sect_pr
        + "</w:body></w:document>"
    )


def _content_types_xml() -> str:
    return (
        _xml_header()
        + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        + '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        + '<Default Extension="xml" ContentType="application/xml"/>'
        + '<Override PartName="/word/document.xml" '
        + 'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        + '<Override PartName="/word/styles.xml" '
        + 'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        + "</Types>"
    )


def _rels_xml() -> str:
    return (
        _xml_header()
        + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + '<Relationship Id="rId1" '
        + 'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        + 'Target="word/document.xml"/>'
        + "</Relationships>"
    )


def _document_rels_xml() -> str:
    return (
        _xml_header()
        + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>'
    )


def _styles_xml() -> str:
    return (
        _xml_header()
        + f'<w:styles xmlns:w="{W_NS}">'
        + '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        + '<w:name w:val="Normal"/>'
        + '<w:qFormat/>'
        + '<w:rPr><w:sz w:val="20"/></w:rPr>'
        + "</w:style>"
        + "</w:styles>"
    )


def save_report_docx(filename: str, result: dict[str, object], report_title: str) -> Path:
    output_path = GENERATED_DIR / filename
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml())
        archive.writestr("_rels/.rels", _rels_xml())
        archive.writestr("word/document.xml", _document_xml(result, report_title))
        archive.writestr("word/styles.xml", _styles_xml())
        archive.writestr("word/_rels/document.xml.rels", _document_rels_xml())
    return output_path
