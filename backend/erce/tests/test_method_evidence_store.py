from copy import deepcopy
import base64
import tempfile
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import fitz

from backend.erce.method_evidence_store import find_method_candidates, save_method_rows, validate_selected_methods
from backend.erce.reviewed_method_rows import reviewed_method_rows
from backend.erce.variable_evidence_store import find_variable_candidates, save_variable_rows
from backend.erce.village_enterprise_evidence import village_enterprise_rows
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.ai_pdf_analysis import analyze_erce_pdf


def check_method_search_is_not_bound_to_wrong_provisional_route(db_path):
    candidates = find_method_candidates(query="대학원 입학금 폐지", cutoff_date="2026-10-03",
        target_bill_no="NEW_FEE_BILL", db_path=db_path)
    assert len(candidates) == 1
    assert candidates[0]["allowed_routes"] == ["transfer_recipient_subsidy"]
    assert candidates[0]["selection_status"] == "candidate_only"
    assert "variable_evidence_keys" in candidates[0]
    assert "value" not in candidates[0]  # Methods do not smuggle in target amounts.
    assert find_method_candidates(query="부동산 등기 수수료 폐지", cutoff_date="2026-10-03", db_path=db_path) == []


def check_method_holdout_excludes_self_family_future_and_explicit_exclusions(db_path, overrides):
    args = dict(query="입학금 폐지", cutoff_date="2026-10-03", db_path=db_path)
    assert find_method_candidates(**{**args, **overrides}) == []


def _plan_payload():
    return dict(route_key="research_plan", bill_no="NEW_PLAN_TEST", cutoff_date="2026-10-03",
        start_year=2027, years=5, payer="government",
        selected_method_keys=["2200039:periodic_plan_research"],
        method_selection_reasons={"2200039:periodic_plan_research": "동일 부처의 유사 과업·규모 연구용역을 비교하는 개발용 시나리오"},
        method_confirmations={"2200039:periodic_plan_research": {
            "external_research_scope": "내부 작성 아닌 외부 용역을 실시하는 시나리오로 확인"}},
        selected_evidence_keys=["2200039:mois_plan_research_unit_cost:2021-2023"],
        evidence_selection_reasons={"2200039:mois_plan_research_unit_cost:2021-2023":
            "과업 규모가 같은 계획 용역 단가를 가격 동결 가정으로 재사용하는 연결 테스트"},
        explicit_inputs={"recurrence_interval_years": {"value": 5, "unit": "year", "source_ref": "합성 의안 5년 주기"}})


def check_web_selected_method_and_variable_reach_existing_fixed_calculator(db_path):
    result = calculate_erce_web_item(_plan_payload(), variable_db_path=db_path)
    assert result["status"] == "computed_review"
    assert result["annualAmountsThousand"] == [203000, 0, 0, 0, 0]
    assert result["methodEvidenceKeys"] == ["2200039:periodic_plan_research"]
    assert result["resolvedVariables"]["plan_unit_cost"]["source_class"] == "precedent_assumption"
    assert result["resolvedVariables"]["plan_unit_cost"]["is_assumption"] is True
    assert "24D0282" in " ".join(result["sourceRefs"])
    assert result["selectedMethods"][0]["confirmed_assumptions"]


def check_explicit_value_beats_selected_precedent(db_path):
    payload = _plan_payload()
    payload["explicit_inputs"]["plan_unit_cost"] = {
        "value": 150000000, "unit": "KRW/plan", "source_ref": "대상 의안 확정 용역비"}
    result = calculate_erce_web_item(payload, variable_db_path=db_path)
    assert result["annualAmountsThousand"] == [150000, 0, 0, 0, 0]
    assert result["resolvedVariables"]["plan_unit_cost"]["source_class"] == "target_explicit"


def check_missing_variable_returns_candidates_but_does_not_auto_select(db_path):
    payload = _plan_payload()
    payload.pop("selected_evidence_keys")
    result = calculate_erce_web_item(payload, variable_db_path=db_path)
    assert result["status"] == "needs_input"
    assert result["missingVariables"] == ["plan_unit_cost"]
    candidates = result["referenceCandidates"]
    assert len(candidates) >= 1
    assert all(c["requiresConfirmation"] is True for c in candidates)
    assert result["missingVariableEvidence"]["plan_unit_cost"]["status"] == "candidates_need_review"
    assert "annualAmountsThousand" not in result


def check_variable_search_and_selection_respect_excluded_family_bills(db_path):
    candidates=find_variable_candidates(cutoff_date="2026-10-03", variable_key="plan_unit_cost",
        excluded_bill_nos=["2200039"], db_path=db_path)
    assert all(c["source_bill_no"] != "2200039" for c in candidates)
    with unittest.TestCase().assertRaisesRegex(ValueError, "excluded bill"):
        calculate_erce_web_item({**_plan_payload(), "selected_method_keys": [],
                                "excluded_bill_nos": ["2200039"]}, variable_db_path=db_path)


def check_web_cannot_read_client_supplied_db_path(db_path):
    result = calculate_erce_web_item({**_plan_payload(), "variable_db_path": "/not/a/database"}, variable_db_path=db_path)
    assert result["status"] == "computed_review"


def check_method_link_requires_real_variable_evidence(db_path):
    rows = deepcopy(reviewed_method_rows()[:1])
    rows[0]["variable_evidence_keys"] = ["nonexistent"]
    import sqlite3
    with unittest.TestCase().assertRaises(sqlite3.IntegrityError):
        save_method_rows(rows, db_path)
    assert find_method_candidates(query="계획 수립", cutoff_date="2026-10-03", db_path=db_path)[0]["variable_evidence_keys"] != ["nonexistent"]


def check_pdf_no_incremental_cost_is_reviewed_not_silently_zero_when_method_conflicts(db_path):
    pdf = fitz.open()
    pdf.new_page().insert_text((50, 50), "2026-10-03\nSection 1: admission fee abolished.")
    content = base64.b64encode(pdf.tobytes()).decode()
    pdf.close()
    draft = dict(bill_name="Synthetic fee bill", bill_no="NEW_FEE_BILL", propose_date="2026-10-03", articles=[
        dict(article_ref="Section 1", change_summary="admission fee abolished", cost_trigger=True,
             estimation_decision="no_incremental_cost", decision_reason="Existing authorization",
             route_key="non_tax_fee_change", source_quote="admission fee abolished", source_page=1, variables=[])])
    original_search = find_method_candidates
    with patch("backend.erce.method_evidence_store.find_method_candidates",
               side_effect=lambda **args: original_search(**args, db_path=db_path)):
        result = analyze_erce_pdf("test.pdf", content, ai_draft=draft)
    assert result["erce"]["items"] == []
    review = result["erce"]["deferredItems"][0]
    assert review["decision"] == "needs_review"
    assert review["methodCandidates"][0]["method_key"] == "2215813:fee_abolition_compensation"
    assert result["articles"][0]["original_estimation_decision"] == "no_incremental_cost"


class MethodEvidenceStoreTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "evidence.sqlite3"
        from backend.erce.support_method_operands import support_operand_rows
        save_variable_rows(village_enterprise_rows() + support_operand_rows(), self.path)
        save_method_rows(reviewed_method_rows(), self.path)

    def test_search(self):
        check_method_search_is_not_bound_to_wrong_provisional_route(self.path)

    def test_holdout(self):
        for overrides in ({"cutoff_date": "2025-12-31"}, {"target_bill_no": "2215813"},
                          {"target_family_key": "graduate_admission_fee_abolition"},
                          {"excluded_bill_nos": ["2215813"]}):
            with self.subTest(overrides=overrides):
                check_method_holdout_excludes_self_family_future_and_explicit_exclusions(self.path, overrides)

    def test_selection_guards(self):
        for change, message in (({"route_key": "quantity_unit"}, "route mismatch"),
                                ({"payer": "private"}, "payer"),
                                ({"method_selection_reasons": {}}, "applicability"),
                                ({"method_confirmations": {}}, "confirmation")):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, message):
                validate_selected_methods({**_plan_payload(), **change}, db_path=self.path)

    def test_web_connection(self):
        check_web_selected_method_and_variable_reach_existing_fixed_calculator(self.path)

    def test_explicit_priority(self):
        check_explicit_value_beats_selected_precedent(self.path)

    def test_candidates_not_selected(self):
        check_missing_variable_returns_candidates_but_does_not_auto_select(self.path)

    def test_variable_family_exclusion(self):
        check_variable_search_and_selection_respect_excluded_family_bills(self.path)

    def test_missing_candidate_does_not_claim_db_contains_no_value(self):
        payload = _plan_payload()
        payload.pop("selected_evidence_keys")
        payload["selected_method_keys"] = []
        # Registry growth may add other eligible plan contracts. Exclude all
        # fixture sources here to test the intentionally empty candidate set.
        with sqlite3.connect(self.path) as connection:
            payload["excluded_bill_nos"] = [r[0] for r in connection.execute(
                "SELECT DISTINCT source_bill_no FROM erce_variable_evidence WHERE variable_key='plan_unit_cost'")]
        result = calculate_erce_web_item(payload, variable_db_path=self.path)
        evidence = result["missingVariableEvidence"]["plan_unit_cost"]
        self.assertEqual(evidence["status"], "no_eligible_candidate")
        self.assertIn("DB 전체에 값이 없다는 뜻은 아닙니다", evidence["meaning"])

    def test_server_db_path(self):
        check_web_cannot_read_client_supplied_db_path(self.path)

    def test_relational_integrity(self):
        check_method_link_requires_real_variable_evidence(self.path)

    def test_no_cost_review(self):
        check_pdf_no_incremental_cost_is_reviewed_not_silently_zero_when_method_conflicts(self.path)

    def test_snapshot_roundtrip_preserves_method_links(self):
        import sqlite3
        from backend.erce.official_salary_store import SCHEMA
        from backend.erce.scripts.reference_snapshot import export_snapshot, import_snapshot
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript(SCHEMA)
        snapshot = Path(self.directory.name) / "snapshot.json"
        restored = Path(self.directory.name) / "restored.sqlite3"
        from backend.erce.support_method_operands import support_operand_rows
        counts = (4 + len(support_operand_rows()), 0)
        self.assertEqual(export_snapshot(self.path, snapshot), counts)
        self.assertEqual(import_snapshot(restored, snapshot), counts)
        self.assertEqual(export_snapshot(restored, snapshot), counts)
        check_web_selected_method_and_variable_reach_existing_fixed_calculator(restored)

    def test_draft_retains_method_assumptions_and_provenance(self):
        from backend.erce.draft_report import generate_draft
        original_calculate = calculate_erce_web_item
        with patch("backend.erce.draft_report.calculate_erce_web_item",
                   side_effect=lambda payload: original_calculate(payload, variable_db_path=self.path)):
            report = generate_draft(dict(bill_name="합성 용역 시나리오", start_year=2027, years=5,
                items=[{**_plan_payload(), "name": "기본계획", "trigger_ref": "제1조"}]))
        self.assertEqual(report["status"], "draft_ready")
        self.assertIn("추계 방법 선례", report["markdown"])
        self.assertIn("확인한 가정", report["markdown"])
        self.assertIn("24D0282", report["markdown"])
