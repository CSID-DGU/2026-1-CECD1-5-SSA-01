import dataclasses
import json
from backend.erce.scripts.check_jobseeker_livelihood import allowance_payload
from backend.erce.engine import estimate_routed_item


def table_payload():
    p=allowance_payload()
    p.update(bill_no="2204843",cutoff_date="2026-10-08",historical_table_year_offset=1,
        estimation_start_note="정답의2026~2030가정확인.공포날시행이2026을확정하지는않음",
        source_year_discrepancy_note="원문·설명은전년도이나정답2026단가표는2025기준액에1년추세를반영한값과일치.법정해석변경없이표재현모드에서만1년이동")
    return p


def run_regression():
    p=table_payload();r=estimate_routed_item(p)
    normal=estimate_routed_item({**p,"historical_table_year_offset":0})
    total=sum(r.annual_amounts_thousand)/100000
    return dict(bill_no="2204843",post_answer_regression=True,independent_evaluation=False,
        table_payload=p,table_result=dataclasses.asdict(r),
        annual_eok=[v/100000 for v in r.annual_amounts_thousand],total_eok=total,
        gold_total_eok=22237,error_percent=abs(total-22237)/22237*100,
        statutory_previous_year_eok=sum(normal.annual_amounts_thousand)/100000,
        limitation="정답표재현과법정전년도시나리오구분.미해결시차를다른의안/일반웹에자동전용하지않음.첫결과유지")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
