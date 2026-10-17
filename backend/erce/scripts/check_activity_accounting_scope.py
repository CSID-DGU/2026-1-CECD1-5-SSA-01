import base64
import copy
import json
from pathlib import Path
from backend.erce.ai_pdf_analysis import analyze_erce_pdf
from backend.erce.engine import estimate_routed_item
from backend.erce.method_evidence_store import validate_non_estimation_review
from backend.erce.evaluation_scope_status import scope_status


def run_review():
    first=json.loads(Path("docs/erce/first_runs/ERCE_FIRST_RUN_2203903.json").read_text())
    draft=copy.deepcopy(first["ai_draft"])
    draft["articles"][2]["source_page"]=7
    pdf=Path("backend/generated/assembly_22_pdfs/by_bill/2203903/bill_text.pdf")
    result=analyze_erce_pdf(filename="bill_text.pdf",content_b64=base64.b64encode(pdf.read_bytes()).decode(),ai_draft=draft)
    calculation=estimate_routed_item(first["survey_payload"])
    decision=validate_non_estimation_review(first["pay_non_estimation_payload"])
    items=[
        dict(key="survey_contract",status="estimated",source_ref="원문제3조의2·정답24C3732 PDF2~4",note="3년주기연구계약9000만원×2,독립계약시나리오"),
        dict(key="pay_standard",status="grounded_non_estimation",source_ref=decision["source_ref"],note=decision["reason"]),
        dict(key="accounting_split_direct_payment",status="direct_scope_reviewed",
            source_ref="2203903 원문PDF6~7 제31조제1항,제32조제2항",
            note="제31조는급여비용중인건비/운영비청구·지급구분이다.금액인상기준은별도제32조에서검토.이구분만으로정액지출추가를생성하지않음"),
        dict(key="accounting_system_implementation",status="needs_review",
            source_ref="2203903 원문PDF6~7 제31조;2026-10-09공식사이트검색에서해당개편과업견적미확보",
            note="기존전산필드사용/새개발여부,인터페이스·정산/급여분리과업견적필요.예산0또는3호미추계확정아님"),
        dict(key="supervision_administration",status="needs_review",source_ref="2203903 원문PDF6 제23조의2·제24조",
            note="시정명령·업무정지/취소집행의순증사건수,인력/시간,기존업무흡수가능성미확정"),
        dict(key="penalty_revenue",status="needs_review",source_ref="2203903 원문PDF6 제24조의2",
            note="추가과징금부과대상확대에따른사건수·부과액·징수율자료없음.수입0으로판정하지않음")
    ]
    covered=sum(calculation.annual_amounts_thousand)
    status=scope_status(items,covered_amount_thousand=covered,covered_error_percent=abs(covered-180000)/180000*100)
    return dict(bill_no="2203903",review_date="2026-10-09",post_answer_reinforcement=True,
        original_first_run_unchanged=True,corrected_draft=draft,original_quote_verified=first["quote_verified"],
        corrected_quote_verified=[a["quote_verified"] for a in result["articles"]],
        survey_annual_thousand=list(calculation.annual_amounts_thousand),pay_non_estimation=decision,
        items=items,completion=status,
        open_required_evidence=dict(accounting_system_implementation=["기존청구·정산시스템기능확인서","추가개발이있다면작업범위·견적"],
            supervision_administration=["기존업무처리자료","순증처리사건수·추가인력/시간"],
            penalty_revenue=["기존부과/징수실적","새위반대상예상건수"]),
        reuse_note="분리청구직접지급분과구현/집행비분리검토구조는재사용가능.근거없는수치추가/수당단가조정없음")


if __name__=="__main__":print(json.dumps(run_review(),ensure_ascii=False,indent=2))
