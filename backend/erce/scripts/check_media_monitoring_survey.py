import json
from pathlib import Path
from dataclasses import asdict
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item

FIRST_RUN = Path(__file__).resolve().parents[3]/"docs/erce/first_runs/ERCE_FIRST_RUN_2209797.json"


def monitoring_payload():
    p = json.loads(FIRST_RUN.read_text())["payload"]
    method = "2209797:policy_media_monitoring_survey"
    keys = ["2209797:media_monitoring:2025_unit_cost","2209797:media_monitoring:price_freeze"]
    return {**p,"evidence_mode":"development_review",
        "research_service_function":"policy_media_monitoring_survey",
        "research_cost_scope":"monitoring_research_package","selected_evidence_keys":keys,
        "evidence_selection_reasons":{k:"정책·언론모니터링 조사분석 동일과업·규모·가격동결 선례 확인" for k in keys},
        "selected_method_keys":[method],"method_selection_reasons":{method:"기존기관의 권고기준점검 조사연구 과업"},
        "method_confirmations":{method:dict(
            monitoring_scope_note="아동권리보장원 무증원 조사연구. 정책·언론 모니터링 조사분석에5천만원 준용. 대상변경은 선례가정",
            price_freeze_note="2025사업예산을2026~2030 조사실시연도에 동결적용. 현재공식요율 아님",
            recurrence_phase_note="원문3년주기·2026.1.1시행 유지. 첫조사2026가정으로2026/2029 실시")}}


def run_regression(db_path=None):
    p = monitoring_payload()
    if db_path:
        p["variable_db_path"] = str(db_path)
    r = estimate_routed_item(p)
    web = calculate_erce_web_item({**monitoring_payload(),"bill_no":"SYNTHETIC_MEDIA_MONITORING"},
        **({"variable_db_path":db_path} if db_path else {}))
    annual = list(r.annual_amounts_thousand)
    if annual != web["annualAmountsThousand"]:
        raise ValueError("engine/web monitoring mismatch")
    return dict(bill_no="2209797",post_answer_regression=True,independent_evaluation=False,
        payload=p,result=asdict(r),web_interface_result=web,total_eok=sum(annual)/100000,
        gold_total_eok=1,error_percent=abs(sum(annual)/100000-1)*100,
        annual_display_matches=sum(a==g for a,g in zip(annual,[50000,0,0,50000,0])),
        first_run_cycle_and_start_preserved=True,limitation="정답 확인 후 단가보강 회귀. 새의안 독립성과 아님")


if __name__ == "__main__":
    print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
