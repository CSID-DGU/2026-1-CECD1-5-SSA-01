"""Post-answer decision regression, not a new independent bill evaluation."""
import json
from pathlib import Path

from backend.erce.method_evidence_store import find_method_candidates,validate_non_estimation_review


def reviewed_payload():
    return dict(bill_no="2208749",cutoff_date="2026-10-04",evidence_mode="development_review",
        decision_evidence_key="2208749:multichild_delegated_allowance_not_estimated",
        reliable_estimation_basis_available=False,
        decision_facts={"multiple_minor_children_household":True,"reliable_household_child_basis_available":False,
            "payment_delegated":True,"payment_amount_confirmed":False},
        decision_confirmations={
            "household_child_scope":"원문3쪽제4조제5항 미성년자녀2명이상가구의아동, 출생순위둘째이상과같지않음",
            "population_basis_review":"25C1367 PDF4쪽의가구정보파악곤란사유를확인한해당역사적법안버전 사후검토.현재통계전수검색을했다는주장아님",
            "delegated_payment_review":"원문월10만원은최대액,자녀수별실제추가급여는대통령령위임.당시정답PDF4쪽추정곤란사유확인, 현재지급제도사실로선언하지않음"})


def run_regression():
    p=reviewed_payload();decision=validate_non_estimation_review(p)
    candidates=find_method_candidates(query="아동수당18세미만자녀2명이상추가지급대통령령",
        cutoff_date="2026-10-04",target_bill_no="SYNTHETIC_SIMILAR_MULTICHILD")
    comparable=validate_non_estimation_review({**p,"bill_no":"SYNTHETIC_SIMILAR_MULTICHILD","evidence_mode":"holdout"})
    return dict(bill_no="2208749",post_answer_regression=True,independent_evaluation=False,
        review_payload=p,decision=decision,synthetic_candidate_keys=[r["method_key"] for r in candidates],
        synthetic_condition_check=comparable,
        limitation="미추계사유보강은정답열람후수행.출처검색·조건검증·판정연결및합성유사조건검증,신규실제의안독립미추계정확도평가아님. 검토메모는외부자료전수검색의자동증명이아님")


if __name__=="__main__":
    r=run_regression()
    Path("docs/erce/cases/ERCE_REGRESSION_NON_ESTIMATION_2208749.json").write_text(
        json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(dict(decision=r["decision"]["decision"],amount=r["decision"]["amount"],
        candidates=r["synthetic_candidate_keys"]),ensure_ascii=False))
