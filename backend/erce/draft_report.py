"""Render a reviewable draft from recalculated ERCE inputs, never model totals."""
from __future__ import annotations

import json
from typing import Any, Mapping

from backend.erce.web_bridge import calculate_erce_web_item


def _text(value: Any) -> str:
    return str(value or "").replace("\n", " ").replace("\r", " ").replace("|", "／")


def document_assumptions(item, row, start, years):
    """Document actual operations; keep internal selection instructions in audit fields."""
    trace = item.get("derivationTrace", [])
    if not trace or not all("advance_cases" in step for step in trace):
        return None
    values = item.get("evidenceVariables", {})
    notes = [f"본 추계에서는 {start}년에 사업을 개시하는 것으로 가정하고, {start}년부터 {start + years - 1}년까지 {years}년간의 추가재정소요를 산출함. 사업 개시연도는 추계를 위한 가정이며, 실제 시행시점에 따라 추계기간과 적용 통계를 조정할 필요가 있음."]
    if row.get("advance_take_up_scenario") == "all_eligible":
        notes.append("양육비 미지급으로 선지급이 필요한 대상자 전원이 신청하여 지원받는 것으로 가정함. 실제 신청률 및 선정률에 따른 차이는 반영하지 않음.")
    notes.append("연도별 가구 전망에 미성년 자녀 한부모가구 비율, 이혼·미혼 비율, 양육비 채권 보유 비율, 미지급 비율 및 평균 자녀 수를 순차적으로 적용하여 지원 건수를 산출함.")
    amount = values.get("advance_monthly_amount", {}).get("value")
    months = values.get("advance_months", {}).get("value")
    if amount is not None and months is not None:
        notes.append(f"자녀 1인당 월 지급액은 {amount:,}원, 연간 지급기간은 {months}개월로 가정함. 지급 대상자의 양육비 채권액은 가정한 월 지급액 이상인 것으로 전제함.")
    budgets = [step["legacy_budget"] for step in trace]
    if len(set(budgets)) == 1:
        notes.append(f"기존 한시적 양육비 긴급지원 사업이 선지급 제도로 대체되는 것을 전제로, 기존 사업 예산은 추계기간 동안 연간 {budgets[0]:,}원으로 유지되는 것으로 가정함. 선지급 총지출에서 해당 예산을 차감하여 추가재정소요를 산출함.")
    else:
        notes.append("기존 한시적 양육비 긴급지원 사업이 선지급 제도로 대체되는 것을 전제로, 연도별 선지급 총지출에서 해당 연도의 기존 사업 예산을 차감하여 추가재정소요를 산출함.")
    notes.append("양육비 회수에 따른 수입은 「의안의 비용추계 등에 관한 규칙」 제5조제2항에 따라 지출과 상계하지 않음. 본 지출 추계에는 회수수입을 포함하지 않았으며, 회수에 따른 재정수입 효과는 별도 산정 대상임.")
    return notes


def generate_draft(payload: Mapping[str, Any]) -> dict[str, Any]:
    start = payload.get("start_year")
    years = payload.get("years", 5)
    if type(start) is not int or not 1900 <= start <= 2200:
        raise ValueError("추계 시작연도를 확인해 주세요.")
    if type(years) is not int or not 1 <= years <= 10:
        raise ValueError("추계기간은 1~10년이어야 합니다.")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or (not raw_items and not payload.get("non_estimation_items")):
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
            pending.append({"name": name, "missingVariables": result.get("missingVariables", []),
                            "missingDerivationVariables": result.get("missingDerivationVariables", [])})
            continue
        values = result["annualAmountsThousand"]
        if len(values) != years or any(type(v) is not int for v in values):
            raise ValueError("연도별 계산 결과를 확인해 주세요.")
        items.append({"name": name, "triggerRef": _text(row.get("trigger_ref")),
                      "formula": result["formula"], "annualAmountsThousand": values,
                      "resolvedVariables": result["resolvedVariables"],
                      "sourceRefs": result["sourceRefs"],
                      "derivationTrace": result.get("derivationTrace", []),
                      "evidenceVariables": result.get("evidenceVariables", {}),
                      "selectedMethods": result.get("selectedMethods", [])})
        items[-1]["documentAssumptions"] = document_assumptions(items[-1], row, start, years)
        if result.get("estimatePurpose") == "reference_scenario":
            items[-1]["estimatePurpose"] = "reference_scenario"
            items[-1]["referenceNotice"] = result.get("referenceNotice", "가정에 따른 참고금액입니다.")
    if pending:
        return {"status": "needs_input", "pendingItems": pending}
    exclusions = payload.get("exclusions") or []
    if not isinstance(exclusions, list):
        raise ValueError("미산출 항목 형식을 확인해 주세요.")
    exclusions = [_text(v) for v in exclusions]
    non_estimation_items=payload.get("non_estimation_items") or []
    if not isinstance(non_estimation_items,list):
        raise ValueError("미추계 근거 항목 형식을 확인해 주세요.")
    reviewed_non_estimation=[]
    from backend.erce.method_evidence_store import validate_non_estimation_review
    for entry in non_estimation_items:
        if not isinstance(entry,Mapping):raise ValueError("미추계 근거 검토가 필요합니다.")
        review=validate_non_estimation_review({**entry,"bill_no":str(payload.get("bill_no") or ""),
            "cutoff_date":str(payload.get("cutoff_date") or ""),"evidence_mode":"holdout",
            "target_family_key":str(payload.get("target_family_key") or ""),
            "excluded_bill_nos":payload.get("excluded_bill_nos") or ()})
        name=_text(entry.get("name")) or "미추계 항목"
        reviewed_non_estimation.append({"name":name,**review})
        exclusions.append(f"{name}: {review['reason']} [근거: {review['source_ref']}] 재추계 조건: {review['reestimate_when']}")
    if not items and reviewed_non_estimation:
        return {"status":"not_estimated","totalThousand":None,"annualAmountsThousand":None,
                "nonEstimationItems":reviewed_non_estimation,"exclusions":exclusions,
                "markdown":"# 비용추계서 검토 초안\n\n금액을 추계하지 않았으며 비용이0이라는 뜻이 아닙니다.\n\n"+
                    "\n".join(f"- {value}" for value in exclusions)}
    annual = [sum(item["annualAmountsThousand"][i] for item in items) for i in range(years)]
    total = sum(annual)
    title = _text(payload.get("bill_name")) or "법안"
    summary = (f"확인한 {len(items)}개 비용 항목의 {start}~{start + years - 1}년 "
               f"합계는 {total:,}천원입니다. "
               + ("미산출 항목이 있어 법안 전체 비용은 아닙니다." if exclusions
                  else "분석 대상으로 선택한 항목을 합산한 검토용 금액입니다."))
    if any(item.get("estimatePurpose") == "reference_scenario" for item in items):
        summary += " 가정에 따른 참고 시나리오 금액이 포함되어 있으며, 공식 미첨부·미추계 판단과 구분해야 합니다."
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
        if item.get("documentAssumptions"):
            lines += [f"- {note}" for note in item["documentAssumptions"]]
        elif item.get("estimatePurpose") == "reference_scenario":
            lines.append(f"- 참고 시나리오: {_text(item['referenceNotice'])}")
        for method in item["selectedMethods"]:
            if item.get("documentAssumptions"):
                lines.append(f"- 추계 근거: {_text(method['source_ref'])}")
                continue
            lines += [f"- 추계 방법 선례: {_text(method['source_ref'])}",
                      f"- 적용 판단: {_text(method['applicability_reason'])}",
                      f"- 기존 비용 확인 기준: {_text(method['baseline_check'])}",
                      f"- 한계: {_text(method['limitation'])}"]
            for condition, note in method["confirmed_assumptions"].items():
                lines.append(f"- 확인한 가정 ({_text(condition)}): {_text(note)}")
        for step in item["derivationTrace"]:
            if step.get("advance_cases") is not None:
                lines.append(f"- {step['year']}년: 선지급 {step['advance_cases']:,}건, 급여지출 {step['gross_expense']:,}원 − 기존예산 {step['legacy_budget']:,}원 = 추가 소요 {step['additional_expense']:,}원")
            if step.get("applied"):
                lines += [f"- 변수 산정 ({_text(step['variable_key'])}): {_text(step['expression'])}",
                          f"- 적용 가정: {_text(step['applicability_note'])}",
                          f"- 변수 산정 근거: {_text(step['source_ref'])}"]
        operand_labels = {
            "household_forecast": "연도별 가구 전망", "minor_single_parent_share": "미성년 자녀 한부모 비율",
            "divorced_unmarried_share": "이혼·미혼 비율", "claim_holder_share": "양육비 채권 보유 비율",
            "unpaid_claim_share": "양육비 미지급 비율", "children_per_claim": "평균 자녀 수",
            "advance_monthly_amount": "월 선지급액", "advance_months": "연간 지급 개월",
            "legacy_support_budget": "기존 긴급지원 예산", "annual_amount": "연도별 소요액",
        }
        for key, variable in item.get("evidenceVariables", {}).items():
            value = json.dumps(variable["value"], ensure_ascii=False)
            lines.append(f"- {operand_labels.get(key, key)}: {value} — 근거: {_text(variable['source_ref'])}")
        for key, variable in item["resolvedVariables"].items():
            value = json.dumps(variable["value"], ensure_ascii=False)
            lines.append(f"- {operand_labels.get(key, key)}: {value} {_text(variable['unit'])} — 근거: {_text(variable['source_ref'])}")
    lines += ["", "## Ⅳ. 부대의견 및 검토사항", "",
              "- 사용자 입력 및 선례 가정의 대상·규모·적용연도와 중복 지원 여부를 검토해야 합니다.",
              "- 산출된 금액은 입력 가정에 따라 달라지며, 비용 항목의 누락 여부도 확인해야 합니다."]
    if exclusions:
        lines += ["", "미산출·검토 보류 항목:", *[f"- {v}" for v in exclusions]]
    return {"status": "draft_ready", "title": title, "summary": summary,
            "startYear": start, "years": years, "items": items, "exclusions": exclusions,
            "nonEstimationItems":reviewed_non_estimation,
            "annualAmountsThousand": annual, "totalAmountThousand": total,
            "markdown": "\n".join(lines) + "\n"}
