"""Post-answer scenario regression; reuse existing population, never gold counts."""
import json
from pathlib import Path

from backend.erce.child_allowance_net_evidence import ALIAS_KEYS
from backend.erce.engine import estimate_routed_item


def reviewed_payload():
    return dict(bill_no="2200527",route_key="transfer_population_amount_delta",
        cutoff_date="2026-10-04",start_year=2025,years=5,
        support_derivation="child_allowance_net_population",child_allowance_scenario="under2_parent_only",
        child_population_geography="전국",
        parent_benefit_unchanged=True,
        child_allowance_scope_note="2세미만은 개정 기본 아동수당 미지급, 부모급여 유지. 현행0~7세 월10만원과 개정2~17세 월30만원의 차액만 계산",
        support_derivation_note="기존 타 의안 인구와 직접 확보했던 KOSIS0·1세 전망을 재사용; 같은 통계 버전·전국·기간, 지급률97.2% 동결 시나리오",
        estimation_start_note="24C0938 선례의2025~2029년을 확인한 추계기간 가정. 공포일이나 시행연도가 원문에 명시된 것은 아님",
        explicit_inputs={
            "benefit_per_recipient":dict(value=300000,unit="KRW/person/month",source_ref="원문3쪽 제4조제1항 개정 월30만원"),
            "existing_benefit_per_recipient":dict(value=100000,unit="KRW/person/month",source_ref="원문5쪽 현행 제4조제1항 월10만원"),
            "payments_per_year":dict(value=12,unit="month/year",source_ref="확인한 추계기간의 각 완전연도12개월 적용 시나리오")},
        selected_evidence_keys=list(ALIAS_KEYS),
        evidence_selection_reasons={key:"전국·같은2023년12월 중위전망·2025~2029년 인구. 실제 수급자 인원이 아니므로97.2%를1회 적용. 대상 정답 인구를 새로 적재하지 않음" for key in ALIAS_KEYS})


def run_regression():
    p=reviewed_payload()
    e=estimate_routed_item(p)
    annual=list(e.annual_amounts_thousand)
    gold_total=88100000000
    return dict(bill_no="2200527",post_answer_regression=True,independent_evaluation=False,
        target_answer_numbers_selected=False,inputs=p,formula_key=e.formula_key,
        annual_amounts_thousand=annual,total_thousand=sum(annual),gold_total_thousand=gold_total,
        gold_annual_thousand=[19100000000,18300000000,17600000000,16900000000,16100000000],
        total_error_percent=abs(sum(annual)-gold_total)/gold_total*100,
        new_recipients=e.resolved_variables["new_recipient_count"].value,
        existing_recipients=e.resolved_variables["existing_recipient_count"].value,
        source_refs=list(e.source_refs),
        limitation="정답의2세미만 운영 가정을 확인한 뒤 재계산. 정답 표시 인구를 복사하지 않고 기존 인구 근거로 산정했으나 독립 예측 평가는 아님. 정답 금액은0.1조원 단위 표시라 오차 해석 시 주의")


if __name__=="__main__":
    r=run_regression()
    Path("docs/erce/cases/ERCE_REGRESSION_2200527.json").write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:r[k] for k in ("annual_amounts_thousand","total_thousand","total_error_percent")},ensure_ascii=False))
