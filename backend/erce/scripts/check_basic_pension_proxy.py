"""Complete candidate scenario from observed national proxies, not exact gold."""
import dataclasses
import json
from backend.erce.basic_pension_statistical_proxies import BASIS,basic_pension_proxy_rows
from backend.erce.scripts.check_basic_pension_staged import band_payload
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item


def proxy_payload(band):
    p=band_payload(band);rows=[r for r in basic_pension_proxy_rows() if r["pension_income_band"]==band]
    p.update(pension_rate_basis=BASIS,use_national_pension_proxy=True,
        pension_proxy_confirmation_note="실제소득구간계수미관측.전국평균수급률·평균수령액비율을구간별증액에같게준용하는검토후보.사용자확정아님")
    p["selected_evidence_keys"] += [r["evidence_key"] for r in rows]
    p["evidence_selection_reasons"].update({r["evidence_key"]:"공식실적기반전국평균준용의검토용후보.구간별관측값아님" for r in rows})
    return p


def run_regression():
    runs=[]
    for band in ("lower30","between30_50"):
        p=proxy_payload(band);r=estimate_routed_item(p)
        web=calculate_erce_web_item({**p,"bill_no":"SYNTHETIC_PENSION_PROXY","evidence_mode":"holdout"})
        runs.append(dict(band=band,payload=p,result=dataclasses.asdict(r),synthetic_web_status=web["status"]))
    total=sum(sum(x["result"]["annual_amounts_thousand"]) for x in runs)
    return dict(bill_no="2203602",post_answer_regression=True,independent_evaluation=False,
        scenario_only=True,actual_band_parameters_verified=False,runs=runs,
        required_variables_filled=6,required_variable_count=6,total_thousand=total,
        gold_partial_total_thousand=11100000000,difference_percent=abs(total-11100000000)/11100000000*100,
        proxy_rows=basic_pension_proxy_rows(),
        limitation="필수슬롯은근거있는대리가정으로채움.정답소득구간별실제계수확보또는정확재현은아님.전국평균급여비율을한계차액계수로준용하는비례근사의적절성미검증.미추계거주요건은합계에0으로포함하지않음")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
