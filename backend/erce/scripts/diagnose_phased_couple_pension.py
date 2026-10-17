"""Conditional checks of published pension costs, not fitted forecast inputs."""
import json
from pathlib import Path
from backend.erce.common_population_evidence import population_series


def diagnose():
    r=json.loads(Path('docs/erce/cases/ERCE_REGRESSION_2211669.json').read_text())
    population=population_series('age65_population',2026,5)
    standard=[349010,355990,363110,370372,377780]
    gold_old=[33.1,35.2,37.5,39.5,41.8];gold_new=[37.2,40.4,44.1,46.4,49.1]
    annual=[]
    for year,n,b,o,a in zip(range(2026,2031),population,standard,gold_old,gold_new):
        current_max=n*.7*b*12/1e12;new_max=n*.75*b*12/1e12
        annual.append(dict(year=year,elderly_population=n,monthly_standard=b,
            gold_current_trillion=o,gold_amended_trillion=a,
            conditional_current_undiscounted_max=current_max,
            conditional_amended_undiscounted_max=new_max,
            minimum_current_uptake_for_gold_without_any_discount=o/current_max,
            minimum_amended_uptake_for_gold_without_any_discount=a/new_max,
            current_exceeds_even_gold_display_rounding=o-.05>current_max,
            amended_exceeds_even_gold_display_rounding=a-.05>new_max))
    comparisons=[]
    for run in r['runs']:
        v=run['result']['resolved_variables']
        old=[n*p*12/1e12 for n,p in zip(v['existing_recipient_count']['value'],v['existing_benefit_per_recipient']['value'])]
        new=[n*p*12/1e12 for n,p in zip(v['new_recipient_count']['value'],v['benefit_per_recipient']['value'])]
        comparisons.append(dict(model=run['model'],current_trillion=old,amended_trillion=new,
            current_total=sum(old),amended_total=sum(new),increment=sum(new)-sum(old)))
    return dict(bill_no='2211669',diagnostic_only=True,annual=annual,model_comparisons=comparisons,
        bound_assumptions=['대상자수가표의65세이상인구×70%또는75%를넘지않음',
            '대상인원에추가하는수급률은0~1','1인당월기초연금은표기준연금액이하','연12개월·급여만이며추가비용은없음'],
        limitation='위조건하에서의검산이며정답오류확정아님.법률목표수급비율이절대인원상한인지·추계수급률분모/단위·유형합계중복·다른모형전제의확인이필요.진단역산값을단가DB에넣지않음')


if __name__=='__main__':print(json.dumps(diagnose(),ensure_ascii=False,indent=2))
