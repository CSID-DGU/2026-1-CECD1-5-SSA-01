from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import fitz


BASE_DIR = Path("backend/generated/assembly_rag_seed_age21_50/files")

TESTSET_NOTES: dict[str, dict[str, str]] = {
    "2126640": {
        "recommended_batch": "1-신설우선",
        "test_focus": "단순 위원회 신설: 회의횟수 x 수당대상 인원 x 회의수당 단가",
        "expected_coverage": "현재 일반화 산식으로 정답표와 exact 검증 가능",
    },
    "2126636": {
        "recommended_batch": "1-신설우선",
        "test_focus": "국회 특별위원회 신설: 소요인력 인건비등 + 운영 사업비",
        "expected_coverage": "현재 특수 산식으로 정답표 exact, 일반화 전환 검토 필요",
    },
    "2126655": {
        "recommended_batch": "1-신설우선",
        "test_focus": "담당관 지정: 조직/인력 운영비 산식",
        "expected_coverage": "조직 인력 산식 일반화 검증용",
    },
    "2126661": {
        "recommended_batch": "1-신설우선",
        "test_focus": "특별조사위원회+사무처 신설: 한시조직, 상임/비상임 수당, 직원 인건비",
        "expected_coverage": "특별위원회 산식 확장 검증용",
    },
    "2126679": {
        "recommended_batch": "1-신설우선",
        "test_focus": "위원회+분과위원회+계획/표준계약서/조사 연구성 사업",
        "expected_coverage": "위원회 운영비와 연구용역/계획 산식 혼합 검증용",
    },
    "2126659": {
        "recommended_batch": "2-확장",
        "test_focus": "기본계획, 실태조사, 정책심의위원회, 지원센터 설치운영",
        "expected_coverage": "지원센터/유사기관 운영비 산식 필요",
    },
    "2126639": {
        "recommended_batch": "2-확장",
        "test_focus": "보수교육 + 장애영유아 보육료/교사 인건비 추가지원",
        "expected_coverage": "직접지원/대상자 수/단가 통계 산식 필요",
    },
    "2126685": {
        "recommended_batch": "2-확장",
        "test_focus": "전문위원회 등 설치 + 사무처 설치",
        "expected_coverage": "위원회와 사무처 인력 산식 혼합 검증용",
    },
    "2126677": {
        "recommended_batch": "2-확장",
        "test_focus": "외국인근로자 기숙사 지원 사업, 시나리오 범위 추계",
        "expected_coverage": "시나리오형 보조사업 산식 필요",
    },
    "2126660": {
        "recommended_batch": "2-확장",
        "test_focus": "양육비 선지급 + 전산관리시스템 구축운영",
        "expected_coverage": "대상자 수/지급단가/회수율 및 전산시스템 산식 필요",
    },
    "2126635": {
        "recommended_batch": "3-고난도",
        "test_focus": "헌법개정 절차: 자문위원회, 국민참여회의, 지원단, 홍보교육",
        "expected_coverage": "여러 산식 패키지와 연계법률 제외 전제 처리 필요",
    },
    "2126648": {
        "recommended_batch": "3-고난도",
        "test_focus": "고등법원/고등검찰청 신설",
        "expected_coverage": "법원/검찰청 기관설치 인력·운영비 산식 별도 필요",
    },
    "2126650": {
        "recommended_batch": "3-고난도",
        "test_focus": "국민연금 크레딧 확대",
        "expected_coverage": "NABO 연금 재정전망 모형 영역이라 현재 일반 산식으로 대응 곤란",
    },
}


def _pdf_text(path: Path) -> str:
    with fitz.open(path) as doc:
        return "\n".join(page.get_text() for page in doc)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _parse_first_cost_table(text: str) -> dict[str, Any]:
    marker = re.search(r"((?:20\d{2}\s+){1,6})(?:합\s*계|계)\s+(?:평균|연평균)", text)
    if not marker:
        return {"header_years": [], "years": [], "total": None, "average": None, "unit": None, "raw": ""}
    header_years = [int(y) for y in re.findall(r"20\d{2}", marker.group(1))]
    value_count = len(header_years) + 2
    block = text[marker.end(): marker.end() + 900]
    block = re.split(r"\n\s*(?:주:|자료:|\[표|\u203b)", block, maxsplit=1)[0]
    unit_window = text[marker.start(): marker.end() + 1300]
    unit_match = re.search(r"단위\s*:\s*(백만원|억원)", unit_window)
    source_unit = unit_match.group(1) if unit_match else None
    factor = 100 if source_unit == "억원" else 1

    row_source = block
    total_rows = list(re.finditer(r"^\s*(?:추가재정소요\s*)?합\s*계\s*$|^\s*합계\s*$", block, re.MULTILINE))
    if total_rows:
        row_source = block[total_rows[0].end(): total_rows[0].end() + 350]

    numbers = [int(n.replace(",", "")) for n in re.findall(r"\d{1,3}(?:,\d{3})*|\d+", row_source)]
    if len(numbers) < value_count:
        return {
            "header_years": header_years,
            "years": [],
            "total": None,
            "average": None,
            "unit": "백만원",
            "source_unit": source_unit,
            "raw": block.strip(),
        }
    values = numbers[:value_count] if total_rows else numbers[-value_count:]
    return {
        "header_years": header_years,
        "years": [v * factor for v in values[:len(header_years)]],
        "total": values[len(header_years)] * factor,
        "average": values[len(header_years) + 1] * factor,
        "unit": "백만원",
        "source_unit": source_unit,
        "raw": block.strip(),
    }


def _title_from_cost_pdf(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for idx, line in enumerate(lines):
        if line != "추계번호":
            continue
        title_lines: list[str] = []
        for candidate in lines[idx + 2:]:
            if "【비용추계서】" in candidate:
                break
            title_lines.append(candidate)
        title = " ".join(title_lines).strip()
        if title:
            return title
    for idx, line in enumerate(lines):
        if "【비용추계서】" not in line:
            continue
        candidates = lines[max(0, idx - 8):idx]
        return " ".join(candidates[-2:]).strip()
    return ""


def _doc_type(title: str, bill_text: str) -> str:
    title_compact = _compact(title)
    if "일부개정" in title_compact:
        return "일부개정"
    if "전부개정" in title_compact:
        return "전부개정"
    if title_compact.endswith(("법률안", "법안")):
        return "제정"

    haystack = _compact(bill_text[:2000])
    if "일부개정" in haystack:
        return "일부개정"
    if "전부개정" in haystack:
        return "전부개정"
    if "법안" in haystack or "다음과같이제정" in haystack:
        return "제정"
    return "미상"


def _formula_categories(cost_text: str, bill_text: str) -> list[str]:
    compact = _compact(cost_text + "\n" + bill_text)
    categories: list[str] = []
    checks = [
        ("위원회회의수당", r"(위원회|심의회|협의회|자문위원회).{0,80}(수당|회의|실비|교통비)"),
        ("조직인력운영", r"(소요인력|증원|인건비|보수|기관부담|기본경비|지원단|담당관|사무처)"),
        ("기관신설시설", r"(고등법원|고등검찰청|법원|검찰청|청사|공사비|시설비|임차료)"),
        ("센터설치운영", r"(지원센터|전담기관|상담센터).{0,80}(설치|운영|지정|위탁)"),
        ("직접지원급여", r"(급여|보육료|지원금|보조금|수당|비용지원|재정지원)"),
        ("연금보험", r"(국민연금|공적연금|보험료|가입기간|크레딧)"),
        ("전산시스템", r"(전산|정보시스템|시스템|정보망|데이터베이스|플랫폼)"),
        ("교육홍보", r"(교육|홍보|캠페인|연수|보수교육)"),
        ("조사계획용역", r"(실태조사|기본계획|종합계획|연구용역|평가)"),
    ]
    for name, pattern in checks:
        if re.search(pattern, compact):
            categories.append(name)
    return categories


def _establishment_type(cost_text: str, bill_text: str, categories: list[str]) -> str:
    compact = _compact(cost_text + "\n" + bill_text)
    if not re.search(r"(신설|설치|둔다|설립|지정|구성|운영)", compact):
        return "비신설/지원중심"
    if "기관신설시설" in categories:
        return "기관신설"
    if "조직인력운영" in categories and "위원회회의수당" in categories:
        return "조직+위원회신설"
    if "위원회회의수당" in categories:
        return "단순위원회신설"
    if "조직인력운영" in categories:
        return "조직신설"
    return "기타신설"


def _priority(establishment_type: str, categories: list[str], total: int | None) -> str:
    hard = {"직접지원급여", "연금보험", "기관신설시설", "전산시스템"}
    if establishment_type == "단순위원회신설":
        return "A-우선: 일반화 검증"
    if establishment_type in {"조직신설", "조직+위원회신설"} and not (set(categories) & {"연금보험"}):
        return "B-우선: 조직/인력 산식 확장"
    if set(categories) & hard:
        return "C-고난도: 별도 산식/통계 필요"
    if total is None:
        return "D-표파싱 확인 필요"
    return "B-우선: 보강 후보"


def classify_one(bill_dir: Path) -> dict[str, Any]:
    bill_no = bill_dir.name
    bill_pdf = bill_dir / "bill_text_의안원문.pdf"
    cost_pdf = bill_dir / "cost_estimate_비용추계서.pdf"
    bill_text = _pdf_text(bill_pdf)
    cost_text = _pdf_text(cost_pdf)
    title = _title_from_cost_pdf(cost_text)
    table = _parse_first_cost_table(cost_text)
    categories = _formula_categories(cost_text, bill_text)
    establishment_type = _establishment_type(cost_text, bill_text, categories)
    return {
        "bill_no": bill_no,
        "title": title,
        "doc_type": _doc_type(title, bill_text),
        "official_amount_million": {
            "header_years": table["header_years"],
            "years": table["years"],
            "total": table["total"],
            "average": table["average"],
            "unit": table["unit"],
            "source_unit": table.get("source_unit"),
        },
        "partial_estimate": "일부추계" in cost_text[:2500] or "일부 재정수반요인" in cost_text,
        "establishment_type": establishment_type,
        "formula_categories": categories,
        "priority": _priority(establishment_type, categories, table["total"]),
        **TESTSET_NOTES.get(bill_no, {}),
        "official_table_label": re.sub(r"\s+", " ", table.get("raw") or "")[:160],
    }


def main() -> None:
    rows = []
    for cost_pdf in sorted(BASE_DIR.glob("*/cost_estimate_비용추계서.pdf")):
        rows.append(classify_one(cost_pdf.parent))
    recommended_batches: dict[str, list[str]] = {}
    for row in rows:
        recommended_batches.setdefault(row.get("recommended_batch", "미분류"), []).append(row["bill_no"])
    summary = {
        "source_dir": str(BASE_DIR),
        "count": len(rows),
        "recommended_batches": recommended_batches,
        "rows": rows,
    }
    out = Path("/private/tmp/assembly_testset_classification.json")
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
