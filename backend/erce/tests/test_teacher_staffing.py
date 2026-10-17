import base64
import tempfile
import unittest
from pathlib import Path
import fitz
from backend.erce.teacher_staffing_evidence import (
    teacher_staffing_rows, reviewed_teacher_replay, PAY_PROFILE,
)
from backend.erce.ai_pdf_analysis import analyze_erce_pdf
from backend.erce.engine import estimate_routed_item
from backend.erce.variable_evidence_store import save_variable_rows, find_variable_candidates


class TeacherStaffingTests(unittest.TestCase):
    def test_replay_components_assets_and_private_salary_basis(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"variables.sqlite3"
            save_variable_rows(teacher_staffing_rows(),db)
            small=reviewed_teacher_replay(db,1)
            large=reviewed_teacher_replay(db,2)
            self.assertEqual(len(small["components"]),5)
            self.assertEqual(small["components"]["initial_asset"],[780000,0,0,0,0])
            self.assertEqual(small["components"]["basic_expense"][0],round(156*40e6*.0654/1000))
            self.assertEqual(small["components"]["private_pension"][0],round(8*35e6*.03706/1000))
            self.assertGreater(large["total_thousand"],small["total_thousand"])

    def test_reuse_guards(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"variables.sqlite3"
            save_variable_rows(teacher_staffing_rows(),db)
            candidates=find_variable_candidates(target_bill_no="new",cutoff_date="2026-10-03",db_path=db)
            self.assertFalse(any(r["variable_key"]=="headcount" for r in candidates))
            p=dict(route_key="personnel_average",bill_no="new",years=5,start_year=2026,
                cutoff_date="2026-10-03",evidence_mode="holdout",variable_db_path=db,
                staff_pay_profile=PAY_PROFILE,school_sector="public",personnel_cost_component="salary",
                selected_evidence_keys=["2200601:salary"],
                evidence_selection_reasons={"2200601:salary":"새 의안의 동일 교원 자격·기산호봉·연도 및 수당 가정 확인"},
                explicit_inputs={"headcount":{"value":2,"unit":"person","source_ref":"합성 의안 확정 순증2명"}})
            self.assertEqual(estimate_routed_item(p).annual_amounts_thousand[0],70000)
            for field,value in (("staff_pay_profile","general_staff"),("school_sector","private"),
                                ("start_year",2027),("cutoff_date","2024-06-18")):
                with self.assertRaises(ValueError):
                    estimate_routed_item({**p,field:value})
            with self.assertRaisesRegex(ValueError,"target answer"):
                estimate_routed_item({**p,"bill_no":"2200601"})

    def test_missing_components_are_review_only_and_old_text_does_not_trigger(self):
        def analyze(quote):
            doc=fitz.open()
            page=doc.new_page()
            page.insert_text((30,60),quote,fontname="korea")
            data=doc.tobytes()
            doc.close()
            draft=dict(bill_no="synthetic",bill_name="학교급식법",document_type="amendment",articles=[
                dict(article_ref="영양교사 증원 보수",source_quote=quote,source_page=1,
                     route_key="personnel_average",change_summary="배치 기준 변경",cost_trigger=True,variables=[]),
                dict(article_ref="국공립 기관부담금",source_quote=quote,source_page=1,
                     route_key="personnel_employer_contribution",cost_trigger=True,variables=[]),
            ])
            return analyze_erce_pdf("synthetic.pdf",base64.b64encode(data).decode(),ai_draft=draft)
        r=analyze("일정 규모 이상 학교에는 2명 이상의 영양교사를 둔다.")
        self.assertTrue(all(a["quote_verified"] for a in r["articles"]))
        review=r["erce"]["reviewCandidates"]
        self.assertEqual({x["componentKey"] for x in review},
                         {"public_basic_expense","public_initial_assets","private_pension_share"})
        self.assertTrue(all(x["requiresConfirmation"] for x in review))
        self.assertEqual(len(r["erce"]["items"]),2)  # no invented automatic expense
        self.assertEqual(analyze("기존 영양교사의 자격 명칭을 변경한다.")["erce"]["reviewCandidates"],[])
