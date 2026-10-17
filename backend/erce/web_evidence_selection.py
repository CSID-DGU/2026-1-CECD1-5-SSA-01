"""Validate AI-selected DB references before forwarding them to the web engine."""
from datetime import date
import re

from backend.erce.method_evidence_store import find_method_candidates
from backend.erce.variable_evidence_store import find_variable_candidates


class CitationReviewRequired(ValueError):
    """A selected method needs a verified positive fiscal provision."""


def advance_clause_candidates(pages):
    """Find original, newly added advance-application provisions for user review.

    This proposes citations only; it never accepts them or invents operands.
    Whitespace offsets preserve the exact PDF quotation and page number.
    """
    candidates, seen = [], set()
    for page_number, text in enumerate(pages, 1):
        offsets = [i for i, character in enumerate(text) if not character.isspace()]
        compact = ''.join(text[i] for i in offsets)
        for match in re.finditer(r'(제\d+조(?:의\d+)?)\([^)]*선지급[^)]*신청[^)]*\)', compact):
            if '신설' not in compact[max(0, match.start()-180):match.start()]:
                continue
            end = compact.find('1.', match.end(), match.end()+500)
            if end < 0:
                continue
            excerpt = compact[match.start():end]
            if '먼저지급' not in excerpt or '신청' not in excerpt or excerpt in seen:
                continue
            seen.add(excerpt)
            candidates.append({'articleRef': match.group(1), 'sourcePage': page_number,
                               'sourceQuote': text[offsets[match.start()]:offsets[end]]})
    return candidates[:3]


def evidence_catalog(text, bill_no="", cutoff=None):
    cutoff = cutoff or date.today().isoformat()
    methods = [m for m in find_method_candidates(
        query=text, cutoff_date=cutoff, target_bill_no=bill_no)
        if m.get("evidence_kind") != "non_estimation"]
    keys = {key for m in methods for key in m.get("variable_evidence_keys", [])}
    variables = [v for v in find_variable_candidates(
        cutoff_date=cutoff, target_bill_no=bill_no) if v["evidence_key"] in keys]
    return {"cutoff_date": cutoff, "methods": methods, "variables": variables}


def selected_web_context(selection, catalog, quote, route):
    if not selection or not selection.get("method_key"):
        return {}
    methods = {m["method_key"]: m for m in catalog["methods"]}
    method = methods.get(selection["method_key"])
    if not method or route not in method["allowed_routes"]:
        raise ValueError("선택한 근거와 비용 유형이 맞지 않아요. 산식을 다시 확인해 주세요.")
    note = str(selection.get("applicability_note") or "").strip()
    if not note:
        raise ValueError("유사 자료를 적용한 이유를 확인해 주세요.")
    selected = selection.get("evidence_keys") or []
    if not isinstance(selected, list) or len(set(selected)) != len(selected):
        raise ValueError("선택한 근거 목록을 확인해 주세요.")
    allowed = set(method.get("variable_evidence_keys", []))
    available = {v["evidence_key"]: v for v in catalog["variables"]}
    if any(key not in allowed or key not in available for key in selected):
        raise ValueError("현재 사용할 수 없는 근거가 선택됐어요. 근거를 다시 확인해 주세요.")
    profile = method.get("support_derivation")
    # Other specialized models need their own reviewed scenario adapter; never
    # blindly manufacture model flags or transfer a total from a precedent.
    if profile and profile != "child_support_advance_expense":
        return {}
    context = {
        "selected_method_keys": [method["method_key"]],
        "method_selection_reasons": {method["method_key"]: note},
        "method_confirmations": {method["method_key"]: {
            key: note for key in method["required_confirmations"]}},
        "selected_evidence_keys": selected,
        "evidence_selection_reasons": {key: note for key in selected},
        "payer": method["payer"], "cutoff_date": catalog["cutoff_date"],
    }
    if profile:
        compact_quote = re.sub(r'\s+', '', quote)
        if "선지급" not in compact_quote or not any(term in compact_quote
                for term in ("선지급신청", "선지급금액", "먼저지급")):
            raise CitationReviewRequired("선지급을 도입하는 조문을 다시 확인해야 해요. 현재 인용만으로는 계산을 진행하지 않았어요.")
        series = [available[key].get("value_years") for key in selected
                  if available[key].get("value_years")]
        if not series or any(years != series[0] for years in series):
            raise ValueError("대상자 전망의 적용 연도를 확인해 주세요.")
        context.update({
            "support_derivation": profile, "child_support_model": profile,
            "start_year": series[0][0],
            "fiscal_reporting": "separate_revenue_and_expenditure",
            "advance_take_up_scenario": "all_eligible", "claim_count_rounding": "final_half_up",
            "support_derivation_note": note, "child_support_scope_note": note,
            "estimation_start_note": "DB 전망 기간을 사용한 참고 가정이며 실제 시행연도는 확정되지 않았습니다.",
            "estimate_purpose": "reference_scenario",
            "reference_notice": "기존 조사 비율·전원 신청·월 20만원·12개월·기존 예산 차감 및 DB 전망 기간을 적용한 참고 가정입니다. 최신 확정 지급기준이 아닙니다.",
        })
    return context
