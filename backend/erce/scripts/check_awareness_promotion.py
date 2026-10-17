"""After-answer package regression, not an independent prediction result."""
import dataclasses
import json
from backend.erce.awareness_promotion_evidence import PACKAGES
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def package_payload(package):
    method="2200879:annual_awareness_campaign_and_video"
    keys=[f"2200879:{package}:unit_cost:2023",f"2200879:{package}:annual_quantity:reviewed"]
    return dict(bill_no="2200879",route_key="quantity_unit",cutoff_date="2026-10-06",
        evidence_mode="development_review",start_year=2025,years=5,
        service_cost_basis=package,awareness_price_projection="freeze_2023_package",
        awareness_scale_profile="national_disability_awareness_annual_package",
        selected_evidence_keys=keys,evidence_selection_reasons={k:"같은국가차원장애인식개선과업·연간패키지의사후재사용 검토" for k in keys},
        selected_method_keys=[method],payer="government",
        method_selection_reasons={method:"원문홍보사업을캠페인·영상제작송출로가정하여분리"},
        method_confirmations={method:dict(annual_package_scope="전국대국민연간패키지.영상제작과송출함께포함",
            historical_price_freeze="2023예산준용단가를추계기간동결하는가정.최신광고공식요율아님",
            forecast_start_basis="공포후6개월에2025~2029시작으로가정한정답과같은사후시나리오")})


def run_regression():
    runs=[]
    for package in PACKAGES:
        p=package_payload(package);r=estimate_routed_item(p)
        # Web runs enforce holdout; only use a synthetic bill to check reuse wiring.
        web=calculate_erce_web_item({**p,"bill_no":"SYNTHETIC_SIMILAR_AWARENESS","evidence_mode":"holdout"})
        runs.append(dict(package=package,payload=p,result=dataclasses.asdict(r),
            synthetic_web_status=web["status"],synthetic_annual=web["annualAmountsThousand"]))
    annual=[sum(x["result"]["annual_amounts_thousand"][i] for x in runs) for i in range(5)]
    total=sum(annual)
    return dict(bill_no="2200879",post_answer_regression=True,independent_evaluation=False,
        runs=runs,required_variables_filled=4,required_variable_count=4,
        annual_amounts_thousand=annual,total_thousand=total,gold_total_thousand=1750000,
        difference_percent=abs(total-1750000)/1750000*100,
        penalty_revenue_status="review_pending",whole_bill_all_fiscal_effects_complete=False,
        limitation="단가·연간1패키지·가격동결을정답확인후저장한급여외홍보비회귀.정답미열람성능아님.과태료수입변화미확정.원2023사업예산독립검증아님")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
