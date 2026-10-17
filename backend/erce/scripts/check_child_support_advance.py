import dataclasses
import json
from backend.erce.child_support_advance_evidence import ADVANCE,SYSTEM,child_support_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.evaluation_scope_status import scope_status


def advance_payload(profile):
    keys=[r["evidence_key"] for r in child_support_rows() if r["support_derivation"]==profile]
    method="2201707:"+profile
    p=dict(bill_no="2201707",evidence_mode="development_review",cutoff_date="2026-10-09",
        route_key="direct_annual_amount",support_derivation=profile,child_support_model=profile,payer="government",
        start_year=2026,years=5,fiscal_reporting="separate_revenue_and_expenditure",
        support_derivation_note="정답후가구·채권필터/기존사업대체예산과전산사업수명주기분리",
        child_support_scope_note="신청필요전원지원가정·원부처고도화계획범위;회수수입은상계안함",
        estimation_start_note="원문공포후6개월과정답2026~2030준비가정확인",
        selected_evidence_keys=keys,evidence_selection_reasons={k:"조건·과업·기준연도확인후사후준용" for k in keys},
        selected_method_keys=[method],method_selection_reasons={method:"동일선지급급여/전산사업과업범위"},
        method_confirmations={method:dict(child_support_scope_note="기존긴급지원차감·회수수입분리확인",
            estimation_start_note="2026시작참고가정")})
    if profile==ADVANCE:p.update(advance_take_up_scenario="all_eligible",claim_count_rounding="final_half_up")
    else:p.update(upgrade_scope_note="기존양육비정보시스템기능/연계/OCR/감리고도화",
        warranty_timing_note="2026구축·2027무상하자보수·2028유지관리시작",
        maintenance_price_note="첫유지연도구축비15%를기준가격으로두고다음해부터전망물가반영")
    return p


def run_regression():
    parts=[]
    for profile in (ADVANCE,SYSTEM):
        p=advance_payload(profile);r=estimate_routed_item(p)
        web=calculate_erce_web_item({**p,"bill_no":"SIMILAR_CHILD_SUPPORT","evidence_mode":"holdout"})
        parts.append(dict(profile=profile,payload=p,result=dataclasses.asdict(r),trace=web["derivationTrace"],web_status=web["status"]))
    annual=[sum(p["result"]["annual_amounts_thousand"][i] for p in parts) for i in range(5)]
    total=sum(annual);error=abs(total-323064000)/323064000*100
    items=[dict(key="advance_expense",status="estimated",source_ref="24C1988 PDF4~6"),
        dict(key="system_upgrade",status="estimated",source_ref="24C1988 PDF7"),
        *[dict(key=k,status="needs_review",source_ref="2201707 원문관련조항·정답별도금액없음")
          for k in ("recovery_revenue","investigation_staff","notifications","fee_exemptions")]]
    return dict(bill_no="2201707",post_answer_regression=True,independent_evaluation=False,
        parts=parts,annual_thousand=annual,covered_total_thousand=total,gold_covered_thousand=323064000,
        covered_error_percent=error,completion=scope_status(items,covered_amount_thousand=total,covered_error_percent=error),
        limitation="선지급+전산정답범위재현,전체4범위미해결.회수수입상계안함.사후회귀")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
