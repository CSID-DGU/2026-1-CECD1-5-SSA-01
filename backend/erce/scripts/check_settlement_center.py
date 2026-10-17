"""2201262 post-answer recurrence regression; no API, no target-total fitting."""
import json
from pathlib import Path

from backend.erce.engine import estimate_routed_item
from backend.erce.support_method_operands import support_operand_rows


def reviewed_payload(kind,scope="combined"):
    rows=[r for r in support_operand_rows() if r["source_bill_no"]=="2201262"
        and r["variable_key"]!="estimate_start_year"
        and (not r.get("center_kind") or r["center_kind"]==kind)
        and (not r.get("support_fiscal_scope") or r["support_fiscal_scope"]==scope)]
    return dict(bill_no="2201262",route_key="quantity_unit",start_year=2025,years=5,
        cutoff_date="2026-10-04",evidence_mode="development_review",
        support_derivation="center_annual_designation",center_kind=kind,support_fiscal_scope=scope,
        support_derivation_note="정답 확인 후 유형별 매년1개 신규 지정·계속 운영·단가 동결 시나리오로 재계산",
        center_operation_scope_note="신규 지원대상 센터만 계산하며 기존 재정지원 중복 제외. 지정된 센터는 다음 해에도 계속 운영하고 지정연도부터 연간 지원비 전액 반영. 패키지 인건비·사업비 중복 가산 없음",
        estimation_start_note="24B0644 PDF3쪽의2025~2029년 추계기간을 가정으로 확인. 공포일은 미정이며 원문 명시연도로 취급하지 않음",
        selected_evidence_keys=[r["evidence_key"] for r in rows],
        evidence_selection_reasons={r["evidence_key"]:r["limitation"] for r in rows})


def run_regression():
    scenarios={}
    for scope in ("combined","national","local"):
        components=[]
        for kind in ("agriculture","fisheries"):
            p=reviewed_payload(kind,scope)
            e=estimate_routed_item(p)
            components.append(dict(center_kind=kind,inputs=p,
                formula_key=e.formula_key,annual_amounts_thousand=list(e.annual_amounts_thousand),
                operating_centers=e.resolved_variables["quantity"].value,
                selected_unit_cost=e.resolved_variables["unit_cost"].value))
        annual=[sum(c["annual_amounts_thousand"][i] for c in components) for i in range(5)]
        scenarios[scope]=dict(components=components,annual_amounts_thousand=annual,total_thousand=sum(annual))
    gold=[1100000,2200000,3300000,4400000,5500000]
    return dict(bill_no="2201262",post_answer_regression=True,independent_evaluation=False,
        scenarios=scenarios,gold_annual_thousand=gold,
        total_error_percent=abs(scenarios["combined"]["total_thousand"]-16500000)/16500000*100,
        limitation="정답 확인 후 단가·지정 시나리오 재계산. 신규 의안의 자동 판단 정확도가 아님. 어업 원시603백만원 대신 정답이 명시한 적용단가600백만원을 사용; 총액 역산 없음")


if __name__=="__main__":
    r=run_regression()
    Path("docs/erce/cases/ERCE_REGRESSION_2201262.json").write_text(
        json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(dict(annual_thousand=r["scenarios"]["combined"]["annual_amounts_thousand"],
        total_thousand=r["scenarios"]["combined"]["total_thousand"],total_error_percent=r["total_error_percent"]),ensure_ascii=False))
