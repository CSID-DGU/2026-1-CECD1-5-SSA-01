"""Post-answer regression using explicitly selected historical operands.

No API call, no independent evaluation; original first-run files are untouched.
"""
import json
from pathlib import Path

from backend.erce.engine import estimate_routed_item
from backend.erce.support_method_operands import support_operand_rows, PROFILES


def payload_for(bill, profile, *, group=None, fiscal_scope="combined"):
    rows = [r for r in support_operand_rows() if r["source_bill_no"] == bill
        and (not r.get("university_kind") or r["university_kind"] == group)
        and (not r.get("support_fiscal_scope") or r["support_fiscal_scope"] == fiscal_scope)]
    return dict(route_key=PROFILES[profile][0], bill_no=bill, cutoff_date="2026-10-03",
        evidence_mode="development_review", start_year=2027 if bill=="2214218" else 2026, years=5,
        support_derivation=profile, support_derivation_note=
            "정답 확인 후 동일 범위의 가정 재계산. 신규 의안 정확도 검증이나 최신 공식값 확인이 아님",
        university_kind=group, support_fiscal_scope=fiscal_scope,
        selected_evidence_keys=[r["evidence_key"] for r in rows],
        evidence_selection_reasons={r["evidence_key"]: r["limitation"] for r in rows})


def run_regression():
    results = {}
    cases = [("2209405","student_tuition_interest",[34702,34317,34147,34080,33906]),
             ("2215813","graduate_fee_compensation",[23837000,24960000,26150000,27412000,28751000]),
             ("2214218","association_operating_support",[754000]*5)]
    for bill,profile,gold in cases:
        groups = ["public","private_general","private_graduate"] if bill=="2215813" else [None]
        components = []
        for group in groups:
            payload = payload_for(bill,profile,group=group)
            estimate = estimate_routed_item(payload)
            components.append(dict(group=group, inputs=payload,
                formula_key=estimate.formula_key, annual_amounts_thousand=list(estimate.annual_amounts_thousand),
                variables={k:dict(value=v.value,unit=v.unit,source_ref=v.source_ref,
                    is_assumption=v.is_assumption) for k,v in estimate.resolved_variables.items()}))
        predicted = [sum(c["annual_amounts_thousand"][i] for c in components) for i in range(5)]
        results[bill] = dict(independent_evaluation=False, post_answer_regression=True,
            components=components, annual_amounts_thousand=predicted,gold_annual_thousand=gold,
            total_thousand=sum(predicted),gold_total_thousand=sum(gold),
            total_error_percent=abs(sum(predicted)-sum(gold))/sum(gold)*100,
            mape_percent=sum(abs(p-g)/g*100 for p,g in zip(predicted,gold))/5,
            limitation="표시된 원시 변수로 재계산. 정답 출력 금액에 맞춰 단가나 인원을 역산하지 않음")
    return results


if __name__ == "__main__":
    results = run_regression()
    output = Path("docs/erce/cases/ERCE_REGRESSION_SUPPORT_METHOD_OPERANDS.json")
    output.write_text(json.dumps(results,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({b:{k:r[k] for k in ("annual_amounts_thousand","total_error_percent","mape_percent")}
                      for b,r in results.items()},ensure_ascii=False))
