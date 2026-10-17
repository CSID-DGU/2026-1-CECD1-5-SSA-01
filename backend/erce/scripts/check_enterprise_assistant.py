import dataclasses
import json
from backend.erce.enterprise_assistant_evidence import PROFILE, NOTES, BUDGET_BASIS, enterprise_assistant_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def assistant_payload(replay=True):
    method="2207221:annual_assistant_service"
    notes=dict(zip(NOTES,[
        "근로자 없는 중증장애 사업자의 업무지원에 근로지원인 연간패키지 준용, 대상제도는 달라 과업 비교 가정. 시범사업 계속사업 승인",
        "2018 4494·2020 6051·2022 9142개에서2018~2022 무반올림CAGR 산출. 표시19.4%를 원시값으로 사용하지 않음",
        "모든기업이 신청하지 않으므로 지원율50% 참고 가정 승인, 현재지원0.3%·법정권리비율 아님",
        "NABO2025.7 PDF324쪽 고용부 예산:2024시급14843원×월125시간×12개월×98.406%,2025시급15092원. 시간과집행률 동결·시급증가율 전망 가정. 연단가 산출후12개월 재곱셈 금지",
        "공포후3개월과 준비기간 고려2026~2030 가정. 정답은 총지원비용 시나리오,2024시범예산2억원을 미래확정기존지원액으로 자동 차감하지 않음",
    ]))
    keys=[r["evidence_key"] for r in enterprise_assistant_rows() if r.get("assistant_operand_basis")==BUDGET_BASIS
          or r["variable_key"] in {"solo_enterprise_history","assistant_take_up","assistant_public_share"}]
    return dict(bill_no="2207221",evidence_mode="development_review",cutoff_date="2026-10-11",
        route_key=PROFILE,support_derivation=PROFILE,payer="government",start_year=2026,years=5,
        assistant_continuation_confirmed=True,assistant_operand_basis=BUDGET_BASIS,**notes,reviewed_assistant_price_year_offset=0,
        assistant_price_year_discrepancy_note="독립 공식 예산에서21.9백만원은2024지원금 연간단가 수준임을 확인. 실제2024기준년으로 계산하고 자기회귀용 연도추가를 제거",
        selected_evidence_keys=keys,evidence_selection_reasons={k:notes["assistant_task_note"] for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"회당 이용비 아닌 연간인력지원서비스 가격×지원기업수"},method_confirmations={method:notes})


def run_regression(db_path=None):
    p=assistant_payload()
    if db_path:
        p["variable_db_path"]=str(db_path)
    engine=estimate_routed_item(p)
    q={**assistant_payload(False),"bill_no":"SIMILAR_ENTERPRISE_ASSISTANT","evidence_mode":"holdout"}
    options={"variable_db_path":db_path} if db_path else {}
    web=calculate_erce_web_item(q,**options)
    annual=list(engine.annual_amounts_thousand);total=sum(annual)/100000
    return dict(bill_no="2207221",post_answer_regression=True,independent_evaluation=False,
        replay_payload=p,replay_result=dataclasses.asdict(engine),replay_total_eok=total,gold_display_total_eok=16120,
        error_percent=abs(total-16120)/16120*100,annual_display_eok=[round(x/100000) for x in annual],
        annual_display_matches=sum(round(x/100000)==g for x,g in zip(annual,[2106,2558,3106,3771,4579])),
        general_base_year_payload=q,general_web_result=web,general_total_eok=sum(web["annualAmountsThousand"])/100000,
        displayed_total_eok=round(total),displayed_total_matches=round(total)==16120,
        engine_and_web_same=annual==web["annualAmountsThousand"],
        limitation="공식예산 구성과 무반올림 역사증가율로 재계산한 사후회귀. 표시금액 정답과 일치하며 원시합계 반올림차이는 별도 기록; 최초정답미열람 성과 아님")


if __name__ == "__main__":
    print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
