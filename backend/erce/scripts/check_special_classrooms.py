import dataclasses
import json
from backend.erce.special_classroom_evidence import PROFILE,NOTES,special_classroom_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.method_evidence_store import validate_non_estimation_review


def classroom_payload(basis="reviewed_historical_bridge",rounding="reviewed_two_decimal_ceiling"):
    method="2205721:capacity_shortfall_classroom_construction"
    notes=dict(zip(NOTES,["전국초등·고등의특수학교/일반학교특수학급4그룹. 유휴공간 증개축, 사립동일지원. 일반학급이동·새학교신축미반영",
        "2026기설치학급은2021~2024성장유지전망, 이후증개축한학급까지누적. 첫해여유학급고정유지해고등부족학급0인지계산",
        "정답학급표를대조해필요학급 소수2자리정리후올림 가정 승인. 문서에명시된공식규칙아니며 엄격올림과별도비교",
        "2022가격5000만원, 원공표2022지수107.71·2023지수111.59를연결하는참고가정.2024공표에서2022는107.72로수정됐으므로동일버전기본값과구분;2024~2029전망·2030동일2%연장 승인"] ))
    if basis=="consistent_2024_vintage":
        notes["classroom_price_note"]="2024.7같은공표버전의2022지수107.72·2023지수111.59로2022가격환산.2024~2029전망·2030동일2%연장가정"
    if rounding=="strict_ceiling":
        notes["classroom_precision_note"]="학생·필요학급중간값을반올림하지않고필요학급에엄격올림. 정답대조로추론한2자리정리를사용하지않음"
    keys=[r["evidence_key"] for r in special_classroom_rows() if r.get("classroom_price_basis") in (None,basis)
          and (rounding!="strict_ceiling" or r["variable_key"]!="class_need_rounding_digits")]
    p=dict(bill_no="2205721",evidence_mode="development_review",cutoff_date="2026-10-11",route_key=PROFILE,
        support_derivation=PROFILE,payer="government",start_year=2026,years=5,classroom_scenario_confirmed=True,
        classroom_price_basis=basis,classroom_rounding_policy=rounding,price_index_bridge_confirmed=True,
        class_precision_assumption_confirmed=True,**notes,
        explicit_inputs={"special_new_class_caps":dict(value=dict(elementary=4,high=6),unit="stage_to_person/class",source_ref="2205721 원문PDF3·5쪽 제27조 개정설치기준")},
        selected_evidence_keys=keys,evidence_selection_reasons={k:"학교급·시설유형·관측년·통계가격버전·수량정밀도가정 확인" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"정원변경에따른부족학급×학급당증개축비"},method_confirmations={method:notes})
    if basis=="reviewed_historical_bridge":
        p.update(estimate_purpose="reference_scenario",reference_notice="학급소수정밀도와다른공표버전의2022/2023지수연결은사후검토참고가정. 정답이같은내부규칙을썼다고확정하지않음")
    return p


def teacher_review():
    return dict(bill_no="2205721",evidence_mode="development_review",cutoff_date="2026-10-11",
        decision_evidence_key="2205721:teacher_increment_not_estimated",reliable_estimation_basis_available=False,
        decision_facts=dict(teacher_increment_confirmed=False,existing_teacher_redeployment_confirmed=False),
        decision_confirmations=dict(teacher_increment_scope_note="정답PDF3쪽증원가능불명확,학급수와교원순증동일시금지",
            teacher_redeployment_review_note="기존교원활용·재배치가능량불명확,표준보수단가가없어서미추계한것아님"))


def run_regression(db_path=None):
    p=classroom_payload(); options={"variable_db_path":db_path} if db_path else {}
    if db_path:
        p["variable_db_path"]=str(db_path)
    result=estimate_routed_item(p)
    web=calculate_erce_web_item({**p,"bill_no":"SIMILAR_SPECIAL_CLASSROOMS","evidence_mode":"holdout"},**options)
    ordinary=calculate_erce_web_item({**classroom_payload("consistent_2024_vintage","strict_ceiling"),"bill_no":"STRICT_SPECIAL_CLASSROOMS","evidence_mode":"holdout"},**options)
    a=list(result.annual_amounts_thousand);total=sum(a)/100000
    review=teacher_review(); decision=validate_non_estimation_review(review,**({"db_path":db_path} if db_path else {}))
    return dict(bill_no="2205721",post_answer_regression=True,independent_evaluation=False,payload=p,result=dataclasses.asdict(result),web_result=web,
        annual_eok=[x/100000 for x in a],total_eok=total,gold_headline_total_eok=3143.52,error_percent=abs(total-3143.52)/3143.52*100,
        annual_display_matches=sum(round(x/100000,1)==g for x,g in zip(a,[1302.8,409.5,441.8,475.3,514.1])),
        teacher_review_payload=review,teacher_decision=decision,strict_consistent_web_result=ordinary,
        strict_consistent_total_eok=sum(ordinary["annualAmountsThousand"])/100000,
        limitation="정답표와대조해소수정밀도와역사지수연결을선택한참고회귀. 같은공식규칙을독립검증했다고주장하지않으며 기본엄격올림/동일발표버전 비교결과유지")


if __name__=="__main__":
    print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
