from __future__ import annotations

import base64
import json
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from .config import PROJECT_ROOT, SCRIPT_DIR
from .docx_renderer import save_report_docx
from .gemini_client import GeminiClient
from .hwpx_renderer import save_report_hwpx
from .knowledge_base import COST_RULES, PRECEDENTS, YEARS
from .report_renderer import render_report_html, save_report_html


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣]+", "-", text).strip("-")
    return cleaned[:80] or "report"


def _extract_bill_name(text: str, fallback_name: str) -> str:
    match = re.search(r"「\s*([^」]+조례안)\s*」", text)
    if match:
        return match.group(1).strip()

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.endswith("조례안"):
            cleaned = re.sub(r"^[「」\s]+", "", stripped)
            cleaned = re.sub(r"\s+", " ", cleaned)
            return cleaned.strip()

    return fallback_name


def _extract_article_map(text: str) -> dict[str, str]:
    pattern = re.compile(r"(제\s*\d+\s*조\([^)]+\))")
    matches = list(pattern.finditer(text))
    if not matches:
        return {}

    article_map: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        article_title = re.sub(r"\s+", "", match.group(1))
        article_map[article_title] = re.sub(r"\s+", " ", text[start:end]).strip()
    return article_map


def _find_legal_basis(article_map: dict[str, str], hint: str, keywords: tuple[str, ...]) -> str:
    if hint:
        return hint
    for title, body in article_map.items():
        if any(keyword in body for keyword in keywords):
            return title
    return "관련 조문 검토 필요"


def _lookup_article_excerpt(article_map: dict[str, str], legal_basis: str) -> str:
    normalized_basis = re.sub(r"\s+", "", legal_basis)
    if normalized_basis in article_map:
        return article_map[normalized_basis]

    article_number_match = re.search(r"(제\s*\d+\s*조)", legal_basis)
    if article_number_match:
        article_number = re.sub(r"\s+", "", article_number_match.group(1))
        for title, body in article_map.items():
            if title.startswith(article_number):
                return body

    return legal_basis


def _build_cost_items(article_map: dict[str, str], bill_text: str) -> list[dict[str, object]]:
    lowered = bill_text.lower()
    items: list[dict[str, object]] = []

    for rule in COST_RULES:
        if not any(keyword in bill_text or keyword.lower() in lowered for keyword in rule.keywords):
            continue

        yearly_amounts = [0, 0, 0, 0, 0]
        annual_amount = rule.unit_cost_thousand_krw * rule.quantity
        if rule.occurrence == "annual":
            yearly_amounts = [annual_amount] * 5
        elif rule.occurrence == "year1_only":
            yearly_amounts[0] = annual_amount

        items.append(
            {
                "id": rule.id,
                "category": rule.category,
                "item": rule.item,
                "unit": rule.unit_label,
                "period": "5년" if rule.occurrence == "annual" else "1회성",
                "quantityLabel": rule.quantity_label,
                "amount": sum(yearly_amounts),
                "yearlyAmounts": yearly_amounts,
                "formula": f"{rule.unit_cost_thousand_krw:,}천원 × {rule.quantity} = {annual_amount:,}천원",
                "legalBasis": _find_legal_basis(article_map, rule.legal_hint, rule.keywords),
                "evidenceSource": rule.evidence_source,
                "evidenceDetail": rule.evidence_detail,
            }
        )

    if not items:
        items.append(
            {
                "id": "baseline_operations",
                "category": "운영비",
                "item": "조례 시행 기본 운영비",
                "unit": "연 120,000천원/식",
                "period": "5년",
                "quantityLabel": "기본 운영 1식",
                "amount": 600_000,
                "yearlyAmounts": [120_000] * 5,
                "formula": "120,000천원 × 1식",
                "legalBasis": "지원계획 및 위탁 조항 검토 필요",
                "evidenceSource": "프로토타입 기본 운영비 가정(2026)",
                "evidenceDetail": "비용요인이 추상적인 경우 최소 운영비 시나리오를 기본값으로 반영",
            }
        )

    return items


def _build_evidences(article_map: dict[str, str], items: list[dict[str, object]]) -> list[dict[str, str]]:
    evidences: list[dict[str, str]] = []
    for item in items:
        legal_basis = item["legalBasis"]
        article_text = _lookup_article_excerpt(article_map, legal_basis)
        evidences.append(
            {
                "type": "law",
                "tag": "법령",
                "source": legal_basis,
                "detail": f"{item['item']} 비용의 법적 근거 조항",
                "highlight": article_text[:220],
            }
        )
        evidences.append(
            {
                "type": "stat",
                "tag": "단가",
                "source": item["evidenceSource"],
                "detail": item["evidenceDetail"],
                "highlight": item["formula"],
            }
        )

    for precedent in PRECEDENTS:
        evidences.append(
            {
                "type": "precedent",
                "tag": "선례",
                "source": precedent["title"],
                "detail": precedent["summary"],
                "highlight": precedent["summary"],
            }
        )

    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for evidence in evidences:
        key = (evidence["source"], evidence["detail"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(evidence)
    return unique


def _sum_yearly(items: list[dict[str, object]]) -> list[int]:
    yearly_totals = [0, 0, 0, 0, 0]
    for item in items:
        for index, amount in enumerate(item["yearlyAmounts"]):
            yearly_totals[index] += amount
    return yearly_totals


def _build_funding_plan(yearly_totals: list[int]) -> dict[str, object]:
    rows = [
        {"label": "국비", "ratio": 0.0},
        {"label": "일반회계", "ratio": 0.6},
        {"label": "주거복지기금", "ratio": 0.1},
        {"label": "시·군비", "ratio": 0.2},
        {"label": "민간", "ratio": 0.1},
        {"label": "기타", "ratio": 0.0},
    ]
    funding_rows: list[dict[str, object]] = []
    for row in rows:
        amounts = [round(amount * row["ratio"]) for amount in yearly_totals]
        funding_rows.append(
            {
                "label": row["label"],
                "amounts": amounts,
                "total": sum(amounts),
            }
        )

    return {
        "rows": funding_rows,
        "detail": (
            "관리비 지원은 경기도 일반회계를 주재원으로 하고, 에너지 효율화 사업은 "
            "주거복지기금과 시·군 매칭, 일부 민간 참여를 결합하는 시범사업 구조를 가정하였다."
        ),
    }


def _build_fallback_sections(
    bill_name: str,
    items: list[dict[str, object]],
    yearly_totals: list[int],
) -> dict[str, object]:
    total_cost = sum(yearly_totals)
    cost_summary = ", ".join(item["item"] for item in items[:4])
    return {
        "financialFactors": [
            f"{bill_name}은 공공임대주택 입주자의 관리비 부담 완화를 위한 직접 지원 근거를 두고 있어 반복적 세출이 발생한다.",
            "공용시설 전기요금, 수도·하수도 요금 등 공공요금 지원은 매년 계속비 성격의 재정수반요인에 해당한다.",
            "에너지 효율화 사업과 시스템 구축은 초기 투자비가 집중되는 자본성 지출 요인이다.",
            "지원계획 수립, 위탁, 협력체계 운영에 따라 행정운영비 및 사업관리비가 추가로 발생한다.",
        ],
        "assumptions": [
            "추계기간은 조례 시행 후 5개년으로 설정하였다.",
            "지원대상은 시범사업 기준 공공임대주택 50개 단지, 에너지 효율화 우선개선 20개 단지로 가정하였다.",
            "단가 기준은 프로토타입 내부 기준표(2026년 기준)이며, 실제 편성 단계에서는 경기도 및 시·군 집행단가로 보정이 필요하다.",
            f"5개년 총비용은 {total_cost:,}천원으로 추계하였고, 주요 항목은 {cost_summary} 등이다.",
        ],
        "detailedBreakdown": (
            "비용추계는 조례 제6조의 관리비 지원 조항과 제7조의 에너지 이용 효율화 지원 조항, "
            "제8조의 위탁 조항을 중심으로 항목을 구분하였다. 반복적 관리비 지원은 단지 수와 연간 "
            "지원단가를 곱하여 산정하고, 에너지 개선 및 시스템 구축비는 1차년도 집중 투자로 반영하였다. "
            "이후 운영비와 유지관리비는 매년 계속 반영하였다."
        ),
        "cooperationNotes": [
            "사업 집행 전 경기도, 시·군, 공공주택사업자 간 매칭비율 협의가 필요하다.",
            "에너지 효율화 사업은 관련 전문기관 또는 공동주택 기술자문단과의 사전 협의가 요구된다.",
            "실제 예산편성 시에는 지원 상한액, 대상 선정기준, 중복지원 배제기준을 별도로 마련해야 한다.",
        ],
    }


def _build_gemini_prompt(
    bill_name: str,
    bill_text: str,
    items: list[dict[str, object]],
    yearly_totals: list[int],
) -> str:
    compact_items = [
        {
            "item": item["item"],
            "category": item["category"],
            "formula": item["formula"],
            "legalBasis": item["legalBasis"],
            "yearlyAmounts": item["yearlyAmounts"],
            "total": item["amount"],
        }
        for item in items
    ]
    return f"""
너는 대한민국 지방의회 비용추계서 작성 보조 AI다.
다음 조례안을 바탕으로 경기도 의안의 비용 추계에 관한 조례 [별지 제1호서식]에 맞는 문안을 작성하라.
반드시 JSON만 반환하고, 스키마는 아래와 같다.

{{
  "financialFactors": ["문장", "..."],
  "assumptions": ["문장", "..."],
  "detailedBreakdown": "한 단락",
  "cooperationNotes": ["문장", "..."]
}}

조건:
- 한국어로 작성한다.
- 과장하지 말고, '시범사업 가정', '프로토타입 단가 기준' 등 불확실성은 명시한다.
- 서술은 공문체로 간결하게 작성한다.
- financialFactors와 assumptions는 각각 3~5개 문장 배열로 작성한다.
- 아래 계산 결과를 뒤집거나 새로운 금액을 invent 하지 말라.

조례안명:
{bill_name}

핵심 비용 항목:
{json.dumps(compact_items, ensure_ascii=False, indent=2)}

연도별 총액(천원):
{json.dumps(yearly_totals, ensure_ascii=False)}

조례안 원문 일부:
{bill_text[:8000]}
""".strip()


def _extract_pdf_text(pdf_path: Path) -> str:
    swift_script = SCRIPT_DIR / "extract_pdf_text.swift"
    command = [
        "swift",
        str(swift_script),
        str(pdf_path),
    ]
    environment = {
        "HOME": "/tmp/swift-home",
        "CLANG_MODULE_CACHE_PATH": "/tmp/swift-module-cache",
    }
    Path(environment["HOME"]).mkdir(parents=True, exist_ok=True)
    Path(environment["CLANG_MODULE_CACHE_PATH"]).mkdir(parents=True, exist_ok=True)

    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "PDF 텍스트 추출에 실패했습니다.")

    text = re.sub(r"<<<PAGE:\d+>>>", "\n", completed.stdout)
    normalized = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not normalized:
        raise RuntimeError("PDF에서 텍스트를 추출하지 못했습니다.")
    return normalized


def analyze_document(filename: str, payload_b64: str) -> dict[str, object]:
    file_bytes = base64.b64decode(payload_b64)
    suffix = Path(filename).suffix.lower() or ".bin"
    if suffix != ".pdf":
        raise ValueError("현재 MVP는 텍스트 기반 PDF 분석만 지원합니다.")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = Path(tmp.name)

    bill_text = _extract_pdf_text(tmp_path)
    bill_name = _extract_bill_name(bill_text, Path(filename).stem)
    article_map = _extract_article_map(bill_text)
    items = _build_cost_items(article_map, bill_text)
    yearly_totals = _sum_yearly(items)
    funding_plan = _build_funding_plan(yearly_totals)

    sections = _build_fallback_sections(bill_name, items, yearly_totals)
    llm_status = "fallback"
    llm_error = ""
    client = GeminiClient()
    if client.enabled:
        try:
            sections = client.generate_sections(
                _build_gemini_prompt(bill_name, bill_text, items, yearly_totals)
            )
            llm_status = "gemini"
        except Exception as exc:
            llm_error = str(exc)

    evidences = _build_evidences(article_map, items)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    result: dict[str, object] = {
        "billName": bill_name,
        "generatedAt": generated_at,
        "analysisMode": llm_status,
        "analysisError": llm_error,
        "items": items,
        "yearlyTotals": yearly_totals,
        "totalCost": sum(yearly_totals),
        "evidences": evidences,
        "sections": sections,
        "fundingPlan": funding_plan,
        "writer": {
            "department": "비용추계자동화시스템 MVP",
            "name": "AI 초안 생성",
            "contact": "검토 후 확정 필요",
        },
    }

    report_title = f"{bill_name} 비용추계서"
    report_html = render_report_html(result, report_title)
    stem = _slugify(bill_name)
    html_name = f"{stem}-비용추계서.html"
    docx_name = f"{stem}-비용추계서.docx"
    hwpx_name = f"{stem}-비용추계서.hwpx"
    json_name = f"{stem}-분석결과.json"

    save_report_html(html_name, report_html)
    save_report_docx(docx_name, result, report_title)
    save_report_hwpx(hwpx_name, result, report_title)
    (PROJECT_ROOT / "backend" / "generated" / json_name).write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result["reportDownloadUrl"] = f"/generated/{html_name}"
    result["docxDownloadUrl"] = f"/generated/{docx_name}"
    result["hwpxDownloadUrl"] = f"/generated/{hwpx_name}"
    result["jsonDownloadUrl"] = f"/generated/{json_name}"
    result["reportTitle"] = report_title
    return result
