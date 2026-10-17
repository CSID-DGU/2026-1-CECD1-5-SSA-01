import dataclasses
import json
from backend.erce.qualification_exam_evidence import PROFILE,NOTES,qualification_exam_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def exam_payload(include_target_projection=True):
    method="2207043:qualification_exam_stock_flow"
    notes=dict(zip(NOTES,["언어시험과발달재활시험의인당운영과업유사성검토.종류별비용같음·인당1회·초기개발/교부비별도중복없음 가정",
        "원문연계2207049 의결전제.2027기존미자격51.3%,이후언어/발달제공인원순증전체를신규시험수요로추정.원관측추세미확보",
        "첫3년특례,4년차부터국가시험.특례전원취득,국가시험실패32%다음해재응시.진행중기존응시자를매년반복하지않음",
        "2023언어시험예산662백만원/2760명의원시단가로계산,2024.12 CPI·2031동일2%연장가정",
        "공포후2년·2025심의공포가정으로2027~2031.원문에확정연도없으며실제공포일·통과사실확인한것아님"]))
    keys=[r["evidence_key"] for r in qualification_exam_rows() if include_target_projection or r.get("reuse_policy")!="target_only"]
    return dict(bill_no="2207043",evidence_mode="development_review",cutoff_date="2026-10-11",
        route_key=PROFILE,support_derivation=PROFILE,payer="government",start_year=2027,years=5,
        exam_model_confirmed=True,exam_linked_dependency_present=True,exam_linked_bill_assumed_passed=True,
        exam_special_all_pass_assumed=True,**notes,
        explicit_inputs={"exam_special_duration_years":dict(value=3,unit="year",source_ref="2207043 원문PDF5쪽 시행후3년이내특례·정답의3년특례운영 가정")},
        selected_evidence_keys=keys,evidence_selection_reasons={k:"시험운영단가·과업·기간·인원범위확인.정답인원표는자기회귀만" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"첫재고·후속신규·정규실패재응시의동일계산구조"},
        method_confirmations={method:notes})


def run_regression(db_path=None):
    p=exam_payload()
    if db_path:
        p["variable_db_path"]=str(db_path)
    r=estimate_routed_item(p);a=list(r.annual_amounts_thousand);total=sum(a)/100000
    options={"variable_db_path":db_path} if db_path else {}
    q={**exam_payload(False),"bill_no":"SYNTHETIC_QUALIFICATION_EXAM","evidence_mode":"holdout"}
    missing=calculate_erce_web_item(q,**options)
    supplied={**q,"explicit_inputs":{**q["explicit_inputs"],"service_provider_forecast":dict(
        value={str(y):n for y,n in zip(range(2027,2032),[36188,37236,38161,38988,39736])},
        unit="year_to_person",source_ref="인터페이스시험용공급전망.정답표를사용한입력테스트로신규기관독립자료아님")}}
    web=calculate_erce_web_item(supplied,**options)
    return dict(bill_no="2207043",post_answer_regression=True,independent_evaluation=False,payload=p,result=dataclasses.asdict(r),
        total_eok=total,gold_display_total_eok=58.93,raw_error_percent=abs(total-58.93)/58.93*100,
        annual_million_display=[round(x/1000) for x in a],annual_display_matches=sum(round(x/1000)==g for x,g in zip(a,[4848,279,251,229,286])),
        displayed_total_million=sum(round(x/1000) for x in a),general_missing_projection_result=missing,
        explicit_projection_web_result=web,explicit_projection_payload=supplied,
        limitation="응시자계산과단가는재사용가능하지만미래제공인원은자기정답회귀전용.공식원관측자료미확보로새의안자동인원예측까지완료한것아님")


if __name__=="__main__":
    print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
