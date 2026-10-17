"""Reference-only replay; no unseen bill or automatic estimation claim."""
import dataclasses
import json
from backend.erce.engine import estimate_routed_item


def payload():
    return dict(bill_no="2211669",route_key="direct_annual_amount",cutoff_date="2026-10-06",
        evidence_mode="development_review",start_year=2026,years=5,
        support_derivation="published_pension_cost_replay",replay_purpose="post_answer_reference_only",
        replay_source_note="정답PDF5쪽표4현행·개정총비용의차감재생.예측변수정확성성과아님",
        selected_evidence_keys=["2211669:published_cost_table:reference_replay"])


def run_replay():
    r=estimate_routed_item(payload());annual=r.annual_amounts_thousand
    return dict(bill_no="2211669",post_answer_reference_replay=True,independent_evaluation=False,
        predictive_reinforcement_complete=False,payload=payload(),result=dataclasses.asdict(r),
        total_thousand=sum(annual),published_total_thousand=30100000000,
        grand_total_difference_percent=abs(sum(annual)-30100000000)/30100000000*100,
        published_increment_thousand=[4100000000,5200000000,6500000000,6900000000,7300000000],
        annual_display_discrepancy_thousand=[int(v)-p for v,p in zip(annual,[4100000000,5200000000,6500000000,6900000000,7300000000])],
        limitation="정답공표비용값을입력받아차감한참조재생.원자료변수추계는여전히미완료.2028년표시총비용차감6.6조원과표시순증6.5조원은별도보존,0.1조원보정하지않음")


if __name__=="__main__":print(json.dumps(run_replay(),ensure_ascii=False,indent=2))
