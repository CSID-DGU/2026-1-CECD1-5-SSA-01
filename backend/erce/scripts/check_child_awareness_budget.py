import dataclasses
import json
from backend.erce.child_awareness_budget_evidence import PROFILE, NOTES, child_awareness_budget_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def awareness_payload():
    method = "2208744:child_awareness_education_budget"
    notes = dict(zip(NOTES,[
        "제41조의2제1·2항 교육홍보 업무를 입양인식개선 매체홍보·교육·실무자교육 통합사업비로 준용",
        "같은 아동분야 전국 인식개선 목적과 과업을 검토. 대상이 달라도 같은 연간예산 준용하는 선례가정",
        "강사양성·프로그램을 통합예산에 준용해 별도 추가하지 않음. 교과서는 정답 산출범위 밖이며 특정 미추계유형으로 단정하지 않음",
        "2025 입양교육홍보 예산7.77억원,2025.3 전망2026~2030 물가2%. 현재 최신공식요율로 주장하지 않음"
    ]))
    keys = [r["evidence_key"] for r in child_awareness_budget_rows()]
    return dict(bill_no="2208744",route_key=PROFILE,support_derivation=PROFILE,
        evidence_mode="development_review",cutoff_date="2026-10-12",start_year=2026,years=5,
        payer="government",child_awareness_package_confirmed=True,**notes,explicit_inputs={},
        selected_evidence_keys=keys,evidence_selection_reasons={k:"아동분야 교육과홍보 통합 연간사업 예산·물가 선례" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"교육과홍보 통합사업 범위·규모 준용 확인"},
        method_confirmations={method:notes})


def run_regression(db_path=None):
    p = awareness_payload()
    if db_path:
        p["variable_db_path"] = str(db_path)
    r = estimate_routed_item(p)
    annual = list(r.annual_amounts_thousand)
    total = sum(annual)/100000
    gold = [793,808,825,841,858]
    q = {**awareness_payload(),"bill_no":"SYNTHETIC_CHILD_EDUCATION_MEDIA","evidence_mode":"holdout"}
    web = calculate_erce_web_item(q,**({"variable_db_path":db_path} if db_path else {}))
    return dict(bill_no="2208744",post_answer_regression=True,independent_evaluation=False,
        payload=p,result=dataclasses.asdict(r),total_eok=total,gold_display_total_eok=41.24,
        raw_error_percent=abs(total-41.24)/41.24*100,
        annual_million_display=[round(x/1000) for x in annual],
        annual_display_matches=sum(round(x/1000)==g for x,g in zip(annual,gold)),
        displayed_total_million=sum(round(x/1000) for x in annual),
        reusable_web_interface_result=web,
        limitation="독립성과 아님. 정답 확인 후 통합예산·물가 준용. 합성 의안은 재사용 인터페이스 검사")


if __name__ == "__main__":
    print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
