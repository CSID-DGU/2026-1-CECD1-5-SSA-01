"""After-answer replay, with scoped non-estimation and untouched first-run records."""
import dataclasses
import json
from backend.erce.median_pension_evidence import PROFILE,median_pension_rows
from backend.erce.engine import estimate_routed_item
from backend.erce.method_evidence_store import validate_non_estimation_review
from backend.erce.web_bridge import calculate_erce_web_item


def payload():
    rows=median_pension_rows()
    return dict(bill_no="2204828",route_key="transfer_population_amount_delta",cutoff_date="2026-10-06",
        evidence_mode="development_review",start_year=2025,years=5,support_derivation=PROFILE,
        median_pension_reading="answer_table_replay",pension_baseline_version="2024_03_reviewed_projection",
        support_derivation_note="정답표2019~2023실적4집단CAGR및지급표재생.직역연금·국비분담이동미포함",
        median_pension_conflict_note="정답표4지급예상액은감액액식과같고본문32%와2023표30%불일치.표재생후보이며법문정확추계로확정하지않음",
        published_baseline_note="정답의동일경제전망기준현행급여예측총액표9를기준선으로사용.최신실측예산·독립재계산아님.명당평균은공표기준선/공식예측수급자/12의대리평균",
        use_unmatched_source_as_reference=True,unmatched_source_reference_note="표지번호공란·회답일이발의일보다앞서는역사자료.내용대응은확인했으나정확버전미확인.명시적사후참조",
        selected_evidence_keys=[r["evidence_key"] for r in rows],
        evidence_selection_reasons={r["evidence_key"]:"해당기간·동일변경의표재생및기준선참조;후보가정" for r in rows},
        explicit_inputs={"payments_per_year":dict(value=12,unit="month/year",source_ref="원문2025-01-01시행·월급여")})


def non_estimation_payload():
    return dict(bill_no="2204828",cutoff_date="2026-10-06",evidence_mode="development_review",
        decision_evidence_key="2204828:occupational_pension_not_estimated",reliable_estimation_basis_available=False,
        decision_facts=dict(occupational_recipients_included=True,reliable_income_distribution_available=False,payment_delegated=True,payment_amount_confirmed=False),
        decision_confirmations=dict(occupational_scope_review="원문제3조제3항삭제·제5조제8항신설.직역연금수급자와배우자포함",
            income_distribution_review="당시정답PDF3쪽대상별소득분포부재확인.현재공개자료전수검색완료주장아님",
            delegated_payment_review="원문산정방식대통령령위임과당시정답단가미확정확인.현재확정된단가있다면재검토",
            source_version_review="표지의안번호공란및회답일선행.해당폴더역사적사유의사후검토로범위한정"))


def run_regression():
    p=payload();r=estimate_routed_item(p)
    web=calculate_erce_web_item({**p,"bill_no":"SYNTHETIC_MEDIAN_PENSION","evidence_mode":"holdout"})
    total=sum(r.annual_amounts_thousand)
    return dict(bill_no="2204828",post_answer_regression=True,independent_evaluation=False,
        answer_table_replay=True,payload=p,result=dataclasses.asdict(r),required_variables_filled=5,required_variable_count=5,
        partial_total_thousand=total,gold_partial_total_thousand=100300000000,
        difference_percent=abs(total-100300000000)/100300000000*100,
        non_estimation=validate_non_estimation_review(non_estimation_payload()),
        synthetic_web_status=web["status"],group_trace=web["derivationTrace"],
        limitation="정답표와공표현행기준선참조후사후재생.직역연금미추계와국비이동포함전체금액아님.정답서식모순이있는표재생을독립추계성능으로해석금지")


if __name__=="__main__":print(json.dumps(run_regression(),ensure_ascii=False,indent=2))
