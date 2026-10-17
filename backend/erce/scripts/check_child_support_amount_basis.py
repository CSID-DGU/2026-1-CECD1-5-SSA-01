import json
import dataclasses
from backend.erce.scripts.check_child_support_advance import advance_payload
from backend.erce.child_support_advance_evidence import ADVANCE
from backend.erce.child_support_amount_basis import STANDARD
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def proxy_payload():
    p=advance_payload(ADVANCE);p.update(bill_no="2203287",statutory_standard_table_required=True,
        advance_amount_basis="policy_fixed_proxy",proxy_assumption_confirmed=True,
        proxy_basis_note="정답이쓴정부정책참고월20만원가정을사후재현용으로선택",
        statutory_basis_difference_note="표준양육비/부모소득/분담률로도출된값아님.원문기준과정답정액시나리오별도",
        child_support_scope_note="정답정액정부계획후보·원문표준기준차이명시")
    p["selected_evidence_keys"]=[k for k in p["selected_evidence_keys"] if "advance_monthly_amount" not in k]+["2203287:advance_monthly_amount:policy_proxy"]
    p["evidence_selection_reasons"]={k:"정답정책참고가정승인모드.표준양육비계산완료라고표시하지않음" for k in p["selected_evidence_keys"]}
    method="2203287:approved_policy_proxy"
    p.update(selected_method_keys=[method],method_selection_reasons={method:"승인된정액참고가정"},
        method_confirmations={method:dict(proxy_basis_note=p["proxy_basis_note"],statutory_basis_difference_note=p["statutory_basis_difference_note"])})
    return p


def standard_payload():
    p=advance_payload(ADVANCE);p.update(bill_no="2203287",support_derivation=STANDARD,child_support_model=STANDARD,
        advance_amount_basis="standard_income_age_table",statutory_standard_table_required=True,
        standard_table_scope_note="원문소득연령표와개별가산감액·소득분담률.아직실제원자료/구성비미확보")
    p["selected_evidence_keys"]=[k+":standard_table" for k in p["selected_evidence_keys"] if "advance_monthly_amount" not in k]
    p["evidence_selection_reasons"]={k:"동일대상모형피연산자만재사용,월액은표준표로계산" for k in p["selected_evidence_keys"]}
    method="2203287:income_age_standard"
    p.update(selected_method_keys=[method],method_selection_reasons={method:"원문기준모드선택"},
        method_confirmations={method:dict(standard_table_scope_note=p["standard_table_scope_note"])})
    return p


def reference_reproduction_status(annual_amounts_thousand, calculation_status):
    """공식 추계서의 표시 정밀도로 비교하며, 별도 모드를 완료 조건에 섞지 않는다."""
    gold_annual_million = [63333, 63881, 64382, 64836, 65249]
    displayed_annual_million = [round(value / 1000) for value in annual_amounts_thousand]
    amount = sum(annual_amounts_thousand) / 100000
    annual_match = displayed_annual_million == gold_annual_million
    total_match = round(amount, 2) == 3216.81
    complete = calculation_status == "computed_review" and annual_match and total_match
    return dict(
        evaluation_scope="official_cost_estimate_reproduction",
        reproduction_status="complete" if complete else "needs_reinforcement",
        reproduction_complete=complete,
        annual_display_match=annual_match,
        total_display_match=total_match,
        displayed_total_eok=round(amount, 2),
        raw_error_percent=abs(amount - 3216.81) / 3216.81 * 100,
    )


def run_regression():
    p=proxy_payload();r=estimate_routed_item(p)
    proxy_web=calculate_erce_web_item({**p,"bill_no":"SIMILAR_STANDARD_RULE_PROXY","evidence_mode":"holdout"})
    standard_web=calculate_erce_web_item({**standard_payload(),"bill_no":"SIMILAR_STANDARD_RULE_TABLE","evidence_mode":"holdout"})
    amount=sum(r.annual_amounts_thousand)/100000
    return dict(bill_no="2203287",post_answer_regression=True,independent_evaluation=False,
        **reference_reproduction_status(r.annual_amounts_thousand, proxy_web["status"]),
        proxy_payload=p,proxy_result=dataclasses.asdict(r),proxy_web_status=proxy_web["status"],
        covered_total_eok=amount,gold_total_eok=3216.81,covered_error_percent=abs(amount-3216.81)/3216.81*100,
        standard_table_status=standard_web["status"],standard_missing=standard_web.get("missingDerivationVariables"),
        whole_bill_total=None,
        optional_standard_mode_blocks_reproduction=False,
        limitation="공식 추계서의 급여 추계범위 재현 완료. 원문 표준양육비 모드는 별도이며 실제 자료가 필요하다. 정답 확인 후 보강 회귀로, 독립 평가 성과는 아니다.")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
