import dataclasses
import json
from backend.erce.ombudsman_evidence import PROFILE,ROUTES,ombudsman_rows,ombudsman_display_table
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def ombudsman_payload(component):
    method=f"2205719:ombudsman:{component}"
    notes=dict(ombudsman_scope_note="중소기업옴부즈만과 같은 규제·애로해결과업 및 사무기구규모 준용. 장애인분야 업무량 적합성 확인할 가정",
        ombudsman_staffing_note="사무기구1개·비상근무보수위촉자1명·전문위원16명, 기존부서행정지원은 추가순증없음 가정. 파견과추가보수중복 금지",
        ombudsman_unit_note="회의사례금40만원·연48회 동결, 2024전문위원16명연보수9.64억원·운영21.68억원 각각임금/물가. 일반공무원보수표 아님",
        ombudsman_start_note="공포후6개월·준비기간 고려2026~2030 가정, 2025전망부터2024기준에 적용",
        ombudsman_asset_price_note="2020연구의인당420만원을2024참고액으로 준용해2025부터물가, 첫해17명만. 2021~2024가격보정 미확인·최신집기표아님")
    keys=[r["evidence_key"] for r in ombudsman_rows() if component in r["ombudsman_components"]]
    return dict(bill_no="2205719",evidence_mode="development_review",cutoff_date="2026-10-11",
        route_key=ROUTES[component],support_derivation=PROFILE,payer="government",start_year=2026,years=5,
        ombudsman_component=component,ombudsman_model_confirmed=True,**notes,
        selected_evidence_keys=keys,evidence_selection_reasons={k:"직종·근무형태·과업규모·연간단위·물가/임금 및 첫해자산 가정 검토" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"옴부즈만 비용을 기존 구성요소별 산식에 연결"},
        method_confirmations={method:notes})


def run_regression(db_path=None):
    parts={};webs={};options={"variable_db_path":db_path} if db_path else {}
    for component in ROUTES:
        p=ombudsman_payload(component)
        if db_path:
            p["variable_db_path"]=str(db_path)
        r=estimate_routed_item(p)
        w=calculate_erce_web_item({**p,"bill_no":"SIMILAR_APPOINTED_OMBUDSMAN","evidence_mode":"holdout"},**options)
        parts[component]=dict(payload=p,result=dataclasses.asdict(r));webs[component]=w
    components={k:list(v["result"]["annual_amounts_thousand"]) for k,v in parts.items()}
    annual=[sum(v[i] for v in components.values()) for i in range(5)];total=sum(annual)/100000
    display=ombudsman_display_table(components)
    return dict(bill_no="2205719",post_answer_regression=True,independent_evaluation=False,
        parts=parts,reusable_web_results=webs,annual_raw_thousand=annual,raw_total_eok=total,
        gold_display_total_eok=175.17,raw_error_percent=abs(total-175.17)/175.17*100,
        display_table=display,annual_display_matches=sum(a==g for a,g in zip(display["annual_total_million"],[3389,3399,3486,3575,3668])),
        displayed_total_matches=display["summed_display_total_million"]==17517,
        display_precision_note="정답표 구성행 인건비·운영비·자산은백만원반올림,회의19.2백만원은유지후총행반올림. 표시행 합계와 구성총계+96백만원은1백만원차이, 원시값을보정하지않음",
        limitation="정답확인후선례패키지 보강회귀. 표시5/5와 원시합계차이는구분. 2020집기단가2024재사용의 정밀가격은미확인")


if __name__=="__main__":
    print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
