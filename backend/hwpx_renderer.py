from __future__ import annotations

import copy
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET

from .config import GENERATED_DIR, PROJECT_ROOT

HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
OPF_NS = "http://www.idpf.org/2007/opf/"
ET.register_namespace("hp", HP_NS)
ET.register_namespace("opf", OPF_NS)

NS = {"hp": HP_NS, "opf": OPF_NS}
TEMPLATE_PATH = PROJECT_ROOT / "비용추계서" / "[별지 제1호서식] 비용추계서(경기도 의안의 비용 추계에 관한 조례).hwpx"


def _text_of_paragraph(paragraph: ET.Element) -> str:
    parts = []
    for text_node in paragraph.findall(".//hp:t", NS):
        parts.append("".join(text_node.itertext()).strip())
    return " ".join(part for part in parts if part).strip()


def _ensure_run(paragraph: ET.Element) -> ET.Element:
    run = paragraph.find("hp:run", NS)
    if run is not None:
        return run

    run = ET.Element(f"{{{HP_NS}}}run")
    run.set("charPrIDRef", "9")
    paragraph.append(run)
    return run


def _set_paragraph_text(paragraph: ET.Element, text: str) -> None:
    run = _ensure_run(paragraph)
    for child in list(run):
        run.remove(child)
    text_element = ET.SubElement(run, f"{{{HP_NS}}}t")
    text_element.text = text


def _find_paragraphs(root: ET.Element, target_text: str) -> list[ET.Element]:
    matches = []
    for paragraph in root.findall(".//hp:p", NS):
        if _text_of_paragraph(paragraph) == target_text:
            matches.append(paragraph)
    return matches


def _make_parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in parent}


def _clone_body_paragraph(root: ET.Element) -> ET.Element:
    template = _find_paragraphs(
        root,
        "1. 재정수반요인 : 의안이 시행되는 경우 세출의 순증가 또는 세입의 순감소를 가져올 것으로 예상되는 요인을 해당 의안 또는 관련 법령 등의 해당 조문과 함께 적어야 한다.",
    )[0]
    cloned = copy.deepcopy(template)
    _set_paragraph_text(cloned, "")
    return cloned


def _insert_after(parent_map: dict[ET.Element, ET.Element], target: ET.Element, new_elements: list[ET.Element]) -> None:
    parent = parent_map[target]
    siblings = list(parent)
    index = siblings.index(target)
    for offset, element in enumerate(new_elements, 1):
        parent.insert(index + offset, element)


def _compact_sentences(lines: list[str], limit: int = 2) -> list[str]:
    if not lines:
        return [""]
    if len(lines) <= limit:
        return lines
    midpoint = (len(lines) + 1) // 2
    return [
        " ".join(lines[:midpoint]),
        " ".join(lines[midpoint:]),
    ]


def _group_expenditure_rows(items: list[dict[str, object]]) -> list[dict[str, object]]:
    recurring = {
        "label": "관리비·운영비 지원",
        "yearly": [0, 0, 0, 0, 0],
    }
    capital = {
        "label": "에너지효율화 및 시스템 구축",
        "yearly": [0, 0, 0, 0, 0],
    }

    for item in items:
        target = recurring
        if item["period"] == "1회성" or item["category"] == "사업비":
            target = capital
        for index, amount in enumerate(item["yearlyAmounts"]):
            target["yearly"][index] += int(amount)

    return [recurring, capital]


def _format_amount(value: int) -> str:
    return f"{int(value):,}"


def _set_cell_text(table: ET.Element, row: int, col: int, text: str) -> None:
    for cell in table.findall(".//hp:tc", NS):
        addr = cell.find("hp:cellAddr", NS)
        if addr is None:
            continue
        if int(addr.get("rowAddr", "-1")) == row and int(addr.get("colAddr", "-1")) == col:
            paragraphs = cell.findall(".//hp:p", NS)
            if paragraphs:
                _set_paragraph_text(paragraphs[0], text)
            return


def _fill_summary_tables(root: ET.Element, result: dict[str, object]) -> None:
    tables = root.findall(".//hp:tbl", NS)
    summary_table = None
    funding_table = None
    for table in tables:
        texts = " ".join(
            text for text in (_text_of_paragraph(p) for p in table.findall(".//hp:p", NS)) if text
        )
        if "세출" in texts and "총 비용" in texts and summary_table is None:
            summary_table = table
        elif "국비" in texts and "시․군비" in texts and funding_table is None:
            funding_table = table

    if summary_table is None or funding_table is None:
        raise RuntimeError("HWPX 템플릿에서 요약표를 찾지 못했습니다.")

    current_year = 2026
    for idx in range(5):
        _set_cell_text(summary_table, 0, idx + 2, f"{current_year + idx}년")
        _set_cell_text(funding_table, 0, idx + 2, f"{current_year + idx}년")

    summary_rows = _group_expenditure_rows(result["items"])
    for row_index, row_data in enumerate(summary_rows, start=1):
        _set_cell_text(summary_table, row_index, 1, row_data["label"])
        for idx, amount in enumerate(row_data["yearly"], start=2):
            _set_cell_text(summary_table, row_index, idx, _format_amount(amount))
        _set_cell_text(summary_table, row_index, 7, _format_amount(sum(row_data["yearly"])))

    recurring_subtotal = summary_rows[0]["yearly"]
    capital_subtotal = summary_rows[1]["yearly"]
    expenditure_totals = [recurring_subtotal[i] + capital_subtotal[i] for i in range(5)]
    for idx, amount in enumerate(expenditure_totals, start=2):
        _set_cell_text(summary_table, 3, idx, _format_amount(amount))
    _set_cell_text(summary_table, 3, 7, _format_amount(sum(expenditure_totals)))

    for row in (4, 5, 6):
        for idx in range(2, 8):
            _set_cell_text(summary_table, row, idx, "0")
    for idx, amount in enumerate(expenditure_totals, start=2):
        _set_cell_text(summary_table, 7, idx, _format_amount(amount))
    _set_cell_text(summary_table, 7, 7, _format_amount(result["totalCost"]))

    funding_rows = {row["label"]: row for row in result["fundingPlan"]["rows"]}
    funding_targets = {
        (1, 0): "국비",
        (2, 1): "일반회계",
        (3, 1): "기타",
        (4, 1): "주거복지기금",
        (5, 0): "시·군비",
        (6, 0): "민간",
        (7, 0): "기타",
        (8, 0): "합계",
    }

    _set_cell_text(funding_table, 3, 1, "기타 특별회계")
    _set_cell_text(funding_table, 4, 1, "주거복지기금")

    total_yearly = result["yearlyTotals"]
    for (row_index, col_index), label in funding_targets.items():
        if label == "합계":
            for idx, amount in enumerate(total_yearly, start=2):
                _set_cell_text(funding_table, row_index, idx, _format_amount(amount))
            _set_cell_text(funding_table, row_index, 7, _format_amount(result["totalCost"]))
            continue

        row_data = funding_rows.get(label, {"amounts": [0, 0, 0, 0, 0], "total": 0})
        for idx, amount in enumerate(row_data["amounts"], start=2):
            _set_cell_text(funding_table, row_index, idx, _format_amount(amount))
        _set_cell_text(funding_table, row_index, 7, _format_amount(row_data["total"]))


def _fill_main_content(root: ET.Element, result: dict[str, object]) -> None:
    paragraphs = root.findall(".//hp:p", NS)
    parent_map = _make_parent_map(root)

    title_paragraph = _find_paragraphs(root, "ㅇㅇㅇ안 비용추계서")[0]
    _set_paragraph_text(title_paragraph, f"{result['billName']} 비용추계서")

    financial_heading = _find_paragraphs(root, "1. 재정수반요인")[0]
    assumptions_heading = _find_paragraphs(root, "2. 비용추계의 전제")[0]
    detail_heading = _find_paragraphs(root, "4. 비용추계의 상세내역")[0]
    funding_detail_heading = _find_paragraphs(root, "2) 재원조달의 구체적 방안")[0]
    cooperation_heading = _find_paragraphs(root, "3) 협의사항")[0]
    writer_heading = _find_paragraphs(root, "6. 작성자")[0]

    body_template = _clone_body_paragraph(root)

    inserts = [
        (
            financial_heading,
            _compact_sentences(result["sections"]["financialFactors"]),
        ),
        (
            assumptions_heading,
            _compact_sentences(result["sections"]["assumptions"]),
        ),
        (
            detail_heading,
            [result["sections"]["detailedBreakdown"]],
        ),
        (
            funding_detail_heading,
            [result["fundingPlan"]["detail"]],
        ),
        (
            cooperation_heading,
            [" ".join(result["sections"]["cooperationNotes"])],
        ),
        (
            writer_heading,
            [
                f"{result['writer']['department']} / {result['writer']['name']} / {result['writer']['contact']}"
            ],
        ),
    ]

    for target, texts in inserts:
        new_paragraphs = []
        for text in texts:
            paragraph = copy.deepcopy(body_template)
            _set_paragraph_text(paragraph, text)
            new_paragraphs.append(paragraph)
        _insert_after(parent_map, target, new_paragraphs)
        parent_map = _make_parent_map(root)

    _fill_summary_tables(root, result)


def _update_content_hpf(content_path: Path, title: str) -> None:
    tree = ET.parse(content_path)
    root = tree.getroot()
    title_node = root.find(".//opf:title", NS)
    if title_node is not None:
        title_node.text = title
    tree.write(content_path, encoding="utf-8", xml_declaration=True)


def save_report_hwpx(filename: str, result: dict[str, object], report_title: str) -> Path:
    if not TEMPLATE_PATH.exists():
        raise RuntimeError("HWPX 템플릿 파일을 찾을 수 없습니다.")

    temp_dir = GENERATED_DIR / "_hwpx_template_work"
    if temp_dir.exists():
        for path in sorted(temp_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    temp_dir.mkdir(parents=True, exist_ok=True)

    with ZipFile(TEMPLATE_PATH, "r") as archive:
        archive.extractall(temp_dir)

    section_path = temp_dir / "Contents" / "section0.xml"
    section_tree = ET.parse(section_path)
    section_root = section_tree.getroot()
    _fill_main_content(section_root, result)
    section_tree.write(section_path, encoding="utf-8", xml_declaration=True)

    _update_content_hpf(temp_dir / "Contents" / "content.hpf", report_title)

    output_path = GENERATED_DIR / filename
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(temp_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(temp_dir).as_posix())

    return output_path
