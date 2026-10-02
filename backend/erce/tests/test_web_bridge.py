import base64
import io
import json
import os
from unittest.mock import patch

import fitz

from backend.erce.ai_pdf_analysis import _openai_draft, analyze_erce_pdf
from backend.erce.web_bridge import route_options, calculate_erce_web_item


def test_web_catalog_is_erce_formula_catalog():
    options = route_options()
    assert any(row["routeKey"] == "personnel_grade" for row in options)
    assert any(row["routeKey"] == "committee_components" for row in options)


def test_web_calculation_calls_erce_and_never_invents_missing_inputs():
    base = {"route_key": "quantity_unit", "years": 2}
    missing = calculate_erce_web_item(base)
    assert missing["status"] == "needs_input"
    assert missing["missingVariables"] == ["quantity", "unit_cost"]

    result = calculate_erce_web_item({
        **base,
        "explicit_inputs": {
            "quantity": {"value": 3, "unit": "item", "source_ref": "의안 제1조"},
            "unit_cost": {"value": 1000000, "unit": "KRW/item", "source_ref": "공식 단가표"},
        },
    })
    assert result["status"] == "computed_review"
    assert result["annualAmountsThousand"] == [3000, 3000]


def test_web_calculation_rejects_unreferenced_values():
    try:
        calculate_erce_web_item({
            "route_key": "quantity_unit",
            "explicit_inputs": {"quantity": {"value": 3, "unit": "item"}},
        })
    except ValueError as exc:
        assert "근거" in str(exc)
    else:
        raise AssertionError("unreferenced variable should be rejected")


def test_web_research_calculation_keeps_cutoff_date():
    result = calculate_erce_web_item({
        "route_key": "research_plan", "bill_no": "2217718",
        "cutoff_date": "2026-03-24", "years": 5,
        "explicit_inputs": {
            "plan_unit_cost": {
                "value": 203_000_000, "unit": "KRW/plan", "source_ref": "선행 의안 용역비",
            },
            "recurrence_interval_years": {
                "value": 5, "unit": "year", "source_ref": "의안 원문: 5년마다",
            },
        },
    })
    assert result["status"] == "computed_review"
    assert result["annualAmountsThousand"] == [203_000, 0, 0, 0, 0]


def test_web_committee_operation_accepts_confirmed_components():
    result = calculate_erce_web_item({
        "route_key": "committee_operation", "bill_no": "2200039",
        "cutoff_date": "2024-05-30", "years": 5,
        "explicit_inputs": {
            "committee_components": {
                "value": [{"paid_members": 5, "annual_meetings": 4,
                           "meeting_unit_price": 200_000}],
                "unit": "component_bundle", "source_ref": "사용자 확인 위원회 운영 가정",
            },
        },
    })
    assert result["status"] == "computed_review"
    assert result["annualAmountsThousand"] == [4000] * 5


def test_health_insurance_web_route_needs_evidence_then_counts_only_treasury_share():
    base = {"route_key": "health_insurance_treasury_support", "years": 2,
            "bill_no": "synthetic", "cutoff_date": "2024-06-03"}
    missing = calculate_erce_web_item(base)
    assert missing["status"] == "needs_input"
    assert missing["missingVariables"] == ["insurance_benefit_cohorts", "government_support_rate"]
    result = calculate_erce_web_item({**base, "explicit_inputs": {
        "insurance_benefit_cohorts": {"value": [{"eligible_cases": [10, 20],
            "covered_days_per_case": 10, "insurer_daily_benefit": 100000}],
            "unit": "cohort_bundle", "source_ref": "합성 환자군 및 단가"},
        "government_support_rate": {"value": .2, "unit": "ratio",
                                    "source_ref": "합성 국고지원 가정"},
    }})
    assert result["status"] == "computed_review"
    assert result["annualAmountsThousand"] == [2000, 4000]


def test_manual_ai_pdf_draft_uses_only_verified_quotes():
    document = fitz.open()
    page = document.new_page()
    page.insert_text((50, 50), "Section 1: 3 facilities. Unit cost KRW 1000000.")
    content = base64.b64encode(document.tobytes()).decode()
    document.close()
    draft = {
        "bill_name": "Test bill", "document_type": "enactment", "bill_no": "2201234",
        "articles": [{
            "article_ref": "Section 1", "change_summary": "Three facilities",
            "cost_trigger": True, "route_key": "quantity_unit",
            "route_reason": "quantity times unit cost",
            "source_quote": "Section 1: 3 facilities.", "source_page": 1,
            "variables": [
                {"key": "quantity", "value_json": "3", "unit": "facility",
                 "source_quote": "3 facilities", "source_page": 1},
                {"key": "unit_cost", "value_json": "1000000", "unit": "KRW/facility",
                 "source_quote": "Unit cost KRW 1000000", "source_page": 1},
            ],
        }],
    }
    result = analyze_erce_pdf("test.pdf", content, ai_draft=draft)
    assert result["engine"] == "erce"
    assert "estimate" not in result and "verdict" not in result
    assert result["articles"][0]["quote_verified"] is True
    assert result["erce"]["items"][0]["calculation"]["annualAmountsThousand"] == [3000] * 5

    draft["articles"][0]["variables"][1]["source_quote"] = "invented source"
    missing = analyze_erce_pdf("test.pdf", content, ai_draft=draft)
    assert missing["erce"]["items"][0]["calculation"]["missingVariables"] == ["unit_cost"]

    draft["articles"][0]["variables"][1]["source_quote"] = "Unit cost KRW 1000000"
    draft["articles"][0]["variables"][1]["value_json"] = "9000000"
    mismatched = analyze_erce_pdf("test.pdf", content, ai_draft=draft)
    assert mismatched["erce"]["items"][0]["calculation"]["missingVariables"] == ["unit_cost"]


def test_deferred_cost_candidate_does_not_create_user_questions():
    document = fitz.open()
    document.new_page().insert_text((50, 50), "The agency may provide support.")
    content = base64.b64encode(document.tobytes()).decode()
    document.close()
    draft = {
        "bill_name": "Test bill", "document_type": "enactment", "bill_no": "2201234",
        "articles": [{
            "article_ref": "Section 1", "change_summary": "Discretionary support",
            "cost_trigger": True, "estimation_decision": "defer",
            "decision_reason": "Recipients and budget are not fixed.",
            "route_key": "transfer_subsidy_rate", "route_reason": "Potential subsidy",
            "source_quote": "The agency may provide support.", "source_page": 1,
            "variables": [],
        }],
    }
    result = analyze_erce_pdf("test.pdf", content, ai_draft=draft)
    assert result["erce"]["items"] == []
    assert result["erce"]["unmappedCount"] == 0
    assert result["erce"]["deferredItems"][0]["decision"] == "defer"


def test_pdf_upload_defaults_to_manual_even_with_an_api_key():
    document = fitz.open()
    document.new_page().insert_text((50, 50), "Test bill")
    content = base64.b64encode(document.tobytes()).decode()
    document.close()
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "ERCE_AI_MODE": "manual"}):
        with patch("backend.erce.ai_pdf_analysis._openai_draft") as mocked:
            result = analyze_erce_pdf("test.pdf", content)
    assert result["analysisMode"] == "manual_required"
    mocked.assert_not_called()


def test_gpt_pdf_adapter_uses_requested_model_without_live_call():
    draft = {"bill_name": "Test", "document_type": "enactment", "bill_no": "", "articles": []}
    response = {"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(draft)}]}]}
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        with patch("backend.erce.ai_pdf_analysis.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as mocked:
            assert _openai_draft("test.pdf", base64.b64encode(b"pdf").decode()) == draft
    sent = json.loads(mocked.call_args.args[0].data)
    assert sent["model"] == "gpt-6.1-sol"
    assert sent["reasoning"]["effort"] == "medium"
    assert sent["input"][0]["content"][0]["type"] == "input_file"
    assert sent["text"]["format"]["type"] == "json_schema"
