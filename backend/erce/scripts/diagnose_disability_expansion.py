"""Diagnostic attribution, without fitting population/price to gold totals."""
import json
from pathlib import Path


def diagnose():
    base=Path("docs/erce/cases")
    projected=json.loads((base/"ERCE_REGRESSION_2203497_OFFICIAL_POPULATION.json").read_text())
    frozen=json.loads((base/"ERCE_REGRESSION_2203497.json").read_text())
    t=projected["population_evidence"]["calculation_trace"]
    prices=projected["result"]["resolved_variables"]["benefit_per_recipient"]["value"]
    gold_old=[14130,14401,14667,14925,15198];gold_new=[24956,25302,25626,25923,26237]
    annual=[]
    for i,year in enumerate(range(2025,2030)):
        old=t["adult_population"][i]*t["existing_projected_ratios"][i]*t["take_up"]*prices[i]*12/1e8
        new=t["adult_population"][i]*t["expanded_projected_ratios"][i]*t["take_up"]*prices[i]*12/1e8
        annual.append(dict(year=year,current_cost_eok=old,expanded_cost_eok=new,
            gold_current_cost_eok=gold_old[i],gold_expanded_cost_eok=gold_new[i]))
    return dict(bill_no="2203497",diagnostic_only=True,annual=annual,
        current_cost_total_eok=sum(x["current_cost_eok"] for x in annual),
        expanded_cost_total_eok=sum(x["expanded_cost_eok"] for x in annual),
        gold_current_total_eok=73320,gold_expanded_total_eok=128044,
        current_cost_difference_eok=sum(x["current_cost_eok"] for x in annual)-73320,
        expanded_cost_difference_eok=sum(x["expanded_cost_eok"] for x in annual)-128044,
        population_scenario_effect_eok=(projected["total_thousand"]-frozen["total_thousand"])/100000,
        known_age_share_2018=225337/364712,known_age_share_2023=219478/355094,
        limitation="기존/개정총액차이분해는가능하나정답연도별수급자·평균단가미공개로인원대단가오차의유일한분해불가.총액역산으로DB인원생성하지않음")


if __name__=="__main__":print(json.dumps(diagnose(),ensure_ascii=False,indent=2))
