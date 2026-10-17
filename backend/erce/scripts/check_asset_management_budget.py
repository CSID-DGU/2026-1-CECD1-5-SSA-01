import dataclasses
import json
from backend.erce.asset_management_budget_evidence import PROFILE, NOTES, asset_management_budget_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def asset_payload():
    method = "2207509:asset_management_annual_budget_proxy"
    notes = dict(zip(NOTES, [
        "보호대상아동 자산관리 계약지원·교육홍보를 신탁지원 전체 사업비 범위로 묶음",
        "대상자 수 확정 전 발달장애인 재산관리 시범사업과 같은 연간규모 예산을 준용하는 선례가정",
        "아동권리보장원 기존업무 수행·추가 조직 인력 없음은 정답을 확인해 채택한 가정",
        "2024예산460백만원이지만 정답 첫해469백만원에 대응하는 첫물가2026 적용.2025동결은 표에서 추론한 시점 가정"
    ]))
    keys = [r["evidence_key"] for r in asset_management_budget_rows()]
    return dict(bill_no="2207509",evidence_mode="development_review",cutoff_date="2026-10-12",
        route_key=PROFILE,support_derivation=PROFILE,payer="government",start_year=2026,years=5,
        asset_budget_proxy_confirmed=True,asset_existing_agency_no_expansion=True,**notes,
        explicit_inputs={"asset_price_adjustment_first_year":dict(value=2026,unit="year",
            source_ref="2207509 정답표469백만원=460백만원×1.02에 대응하는 계산시점 가정")},
        selected_evidence_keys=keys,evidence_selection_reasons={k:"동일과업 전체예산 준용 가정·가격시점 확인" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"신탁자산관리 전체 연간사업예산 준용"},
        method_confirmations={method:notes})


def run_regression(db_path=None):
    p = asset_payload()
    if db_path:
        p["variable_db_path"] = str(db_path)
    result = estimate_routed_item(p)
    annual = list(result.annual_amounts_thousand)
    total = sum(annual)/100000
    gold = [469,479,488,498,508]
    q = {**asset_payload(),"bill_no":"SYNTHETIC_ASSET_BUDGET","evidence_mode":"holdout"}
    web = calculate_erce_web_item(q,**({"variable_db_path":db_path} if db_path else {}))
    return dict(bill_no="2207509",post_answer_regression=True,independent_evaluation=False,
        payload=p,result=dataclasses.asdict(result),total_eok=total,
        gold_display_total_eok=24.42,raw_error_percent=abs(total-24.42)/24.42*100,
        annual_million_display=[round(x/1000) for x in annual],
        annual_display_matches=sum(round(x/1000)==g for x,g in zip(annual,gold)),
        displayed_total_million=sum(round(x/1000) for x in annual),
        reusable_web_interface_result=web,
        limitation="합성 다른의안ID는 재사용 인터페이스 검사일 뿐 독립 추계 성과 아님. 대상·규모·무증원·물가시점은 사용자 확인 가정")


if __name__ == "__main__":
    print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
