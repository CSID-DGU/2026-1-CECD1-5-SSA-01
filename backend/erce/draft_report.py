"""Render a reviewable draft from recalculated ERCE inputs, never model totals."""
from __future__ import annotations

import json
from typing import Any, Mapping

from backend.erce.web_bridge import calculate_erce_web_item


def _text(value: Any) -> str:
    return str(value or "").replace("\n", " ").replace("\r", " ").replace("|", "／")


def generate_draft(payload: Mapping[str, Any]) -> dict[str, Any]:
    start = payload.get("start_year")
    years = payload.get("years", 5)
    if type(start) is not int or not 1900 <= start <= 2200:
        raise ValueError("추계 시작연도를 확인해 주세요.")
    if type(years) is not int or not 1 <= years <= 10:
        raise ValueError("추계기간은 1~10년이어야 합니다.")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("추계할 비용 항목이 필요합니다.")
    routes = {row.get("route_key") for row in raw_items if isinstance(row, dict)}
    if {"infertility_leave_civil_proxy", "infertility_leave_budget_proxy"} <= routes:
        raise ValueError("난임휴가 대상자 산정의 두 방법은 대안 시나리오입니다. 하나씩 초안을 만들어 주세요.")
    items, pending = [], []
    for row in raw_items:
        if not isinstance(row, dict):
            raise ValueError("비용 항목 형식을 확인해 주세요.")
        if row.get("start_year") is not None and row["start_year"] != start:
            raise ValueError("항목별 추계 시작연도를 맞춰 주세요.")
        result = calculate_erce_web_item({**row, "start_year": start, "years": years})
        name = _text(row.get("name")) or "비용 항목"
        if result["status"] != "computed_review":
            pending.append({"name": name, "missingVariables": result.get("missingVariables", [])})
            continue
        values = result["annualAmountsThousand"]
        if len(values) != years or any(type(v) is not int for v in values):
            raise ValueError("연도별 계산 결과를 확인해 주세요.")
        items.append({"name": name, "triggerRef": _text(row.get("trigger_ref")),
                      "formula": result["formula"], "annualAmountsThousand": values,
                      "resolvedVariables": result["resolvedVariables"],
                      "sourceRefs": result["sourceRefs"]})
    if pending:
        return {"status": "needs_input", "pendingItems": pending}
    exclusions = payload.get("exclusions") or []
    if not isinstance(exclusions, list):
        raise ValueError("미산출 항목 형식을 확인해 주세요.")
    exclusions = [_text(v) for v in exclusions]
    annual = [sum(item["annualAmountsThousand"][i] for item in items) for i in range(years)]
    total = sum(annual)
    title = _text(payload.get("bill_name")) or "법안"
    summary = (f"확인한 {len(items)}개 비용 항목의 {start}~{start + years - 1}년 "
               f"합계는 {total:,}천원입니다. "
               + ("미산출 항목이 있어 법안 전체 비용은 아닙니다." if exclusions
                  else "분석 대상으로 선택한 항목을 합산한 검토용 금액입니다."))
    lines = [f"# {title} 비용추계서 초안", "", "> 검토용 자동 생성 초안입니다. 공식 비용추계서가 아닙니다.",
             "", "## Ⅰ. 비용추계 결과", "", summary, "", "단위: 천원", "",
             "| 항목 | " + " | ".join(str(start + i) for i in range(years)) + " | 합계 |",
             "| " + " | ".join(["---"] + ["---:"] * (years + 1)) + " |"]
    for item in items:
        values = item["annualAmountsThousand"]
        lines.append("| " + item["name"] + " | " + " | ".join(f"{v:,}" for v in values)
                     + f" | {sum(values):,} |")
    lines += ["| 합계 | " + " | ".join(f"{v:,}" for v in annual) + f" | {total:,} |",
              "", "## Ⅱ. 재정수반요인", ""]
    lines += [f"- {item['triggerRef'] or '조문 확인 필요'}: {item['name']}" for item in items]
    lines += ["", "## Ⅲ. 추계의 전제와 상세내역", "",
              "- 추계 시작연도와 기간은 원문 확인 또는 사용자의 설정을 따릅니다.",
              "- 입력하지 않은 선택 변수는 등록 산식의 기본값을 적용합니다. 지급범위·기간·참여율을 검토해야 합니다."]
    for item in items:
        lines += ["", f"### {item['name']}", "", f"산식: {item['formula']}", ""]
        for key, variable in item["resolvedVariables"].items():
            value = json.dumps(variable["value"], ensure_ascii=False)
            lines.append(f"- {key}: {value} {_text(variable['unit'])} — 근거: {_text(variable['source_ref'])}")
    lines += ["", "## Ⅳ. 부대의견 및 검토사항", "",
              "- 사용자 입력 및 선례 가정의 대상·규모·적용연도와 중복 지원 여부를 검토해야 합니다.",
              "- 산출된 금액은 입력 가정에 따라 달라지며, 비용 항목의 누락 여부도 확인해야 합니다."]
    if exclusions:
        lines += ["", "미산출·검토 보류 항목:", *[f"- {v}" for v in exclusions]]
    return {"status": "draft_ready", "title": title, "summary": summary,
            "startYear": start, "years": years, "items": items, "exclusions": exclusions,
            "annualAmountsThousand": annual, "totalAmountThousand": total,
            "markdown": "\n".join(lines) + "\n"}
