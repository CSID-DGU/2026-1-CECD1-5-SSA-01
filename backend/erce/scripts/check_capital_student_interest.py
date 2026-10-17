"""2219149 post-answer regression; manual AI, no paid API, no gold inversion."""
import json
from pathlib import Path

from backend.erce.engine import estimate_routed_item
from backend.erce.support_method_operands import support_operand_rows


def reviewed_payload(band):
    rows=[r for r in support_operand_rows() if r["source_bill_no"]=="2219149"
        and r["variable_key"] in {"eligible_loan_students","average_loan_balance","student_loan_rate"}
        and (not r.get("loan_income_band") or r["loan_income_band"]==str(band))]
    return dict(bill_no="2219149",route_key="transfer_recipient",start_year=2027,years=5,
        cutoff_date="2026-10-03",evidence_mode="development_review",
        support_derivation="student_income_interest",loan_income_band=str(band),student_loan_region="capital",
        support_derivation_note="정답 확인 후 수도권 소득구간별 ICL 이용자·잔액·금리 가정으로 회귀검증",
        student_interest_scope_note="6구간 이하·비수도권은 이미 면제라 제외.7·8구간 각각 계산하며 면제이자 전액 정부지원 시나리오. 졸업 후 누적·원금상환은 미반영",
        effective_date="2026-11-20",
        estimation_start_note="26C2955 PDF5쪽 선례는 시행 다음 완전연도2027년부터 추계. 해당 기간 가정을 확인하며2026년 비용이 없다고 주장하지 않음",
        selected_evidence_keys=[r["evidence_key"] for r in rows],
        evidence_selection_reasons={r["evidence_key"]:r["limitation"] for r in rows})


def run_regression():
    components=[]
    for band in (7,8):
        payload=reviewed_payload(band)
        estimate=estimate_routed_item(payload)
        components.append(dict(band=band,inputs=payload,formula_key=estimate.formula_key,
            annual_amounts_thousand=list(estimate.annual_amounts_thousand),
            resolved_variables={k:dict(value=v.value,unit=v.unit,source_ref=v.source_ref)
                                for k,v in estimate.resolved_variables.items()}))
    annual=[sum(c["annual_amounts_thousand"][i] for c in components) for i in range(5)]
    gold=[10288000,10547000,10815000,11091000,11374000]
    gold_total=54116000
    return dict(bill_no="2219149",post_answer_regression=True,independent_evaluation=False,
        components=components,annual_amounts_thousand=annual,total_thousand=sum(annual),
        gold_annual_thousand=gold,gold_total_thousand=gold_total,
        total_error_percent=abs(sum(annual)-gold_total)/gold_total*100,
        mape_percent=sum(abs(a-g)/g*100 for a,g in zip(annual,gold))/5,
        limitation="정답 표2·3의 표시 변수를 재계산. 총액에서 인원·단가를 역산하지 않으며 표의 표시 정밀도 차이는 남김")


if __name__=="__main__":
    result=run_regression()
    output=Path("docs/erce/cases/ERCE_REGRESSION_2219149.json")
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("annual_amounts_thousand","total_thousand","total_error_percent","mape_percent")},ensure_ascii=False))
