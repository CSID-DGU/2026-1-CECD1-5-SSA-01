from __future__ import annotations

from backend.tag_committee_precedent_adapter import (
    apply_precedent_fallback,
    extract_bill_metadata,
)
from backend.tag_parsers import CommitteeVars
from backend.tag_rule_engine import _calculate_committee_impl
from backend.tag_router import route_article


def _item(status: str) -> dict:
    return {
        "entity_name": "정책위원회",
        "label": "제7조 정책위원회",
        "calc_result": {
            "name": "정책위원회",
            "status": status,
            "annual_cost_won": 8_000_000,
        },
        "year_amounts": [8_000_000] * 5,
    }


def _verified_workflow(selected_bill_no: str) -> dict:
    return {
        "covered": {
            "decision": "calculated",
            "ready_for_auto_publish": True,
            "selected_bill_no": selected_bill_no,
            "warnings": [],
            "package": {"decision": "exact_package"},
            "line_items": [
                {
                    "item_name": "정책위원회 운영비",
                    "formula": "6명 × 20만원 × 연 3회",
                    "full_year_thousand": 3_600,
                    "yearly_thousand": [3_600] * 5,
                }
            ],
        },
        "components": [],
    }


def test_metadata_reconstructs_full_bill_number() -> None:
    text = """
    의안 번호 17718
    발 의 연 월 일 : 2026. 3. 24.
    인공지능데이터센터 구축 및 운영 활성화에 관한 법률안
    """
    assert extract_bill_metadata(text) == ("2217718", "2026-03-24")


def test_tag_anchor_always_beats_a_verified_precedent() -> None:
    items = [_item("calculated_with_rule")]
    apply_precedent_fallback(
        items,
        _verified_workflow("2213320"),
        current_bill_no="2217718",
    )
    assert items[0]["calc_result"]["annual_cost_won"] == 8_000_000
    assert items[0]["calc_result"]["evidence_route"]["level"] == "tag_anchor"


def test_verified_precedent_replaces_only_low_confidence_result() -> None:
    items = [_item("calculated_low_confidence")]
    apply_precedent_fallback(
        items,
        _verified_workflow("2213320"),
        current_bill_no="2217718",
    )
    calc = items[0]["calc_result"]
    assert calc["status"] == "calculated_with_verified_precedent"
    assert calc["annual_cost_won"] == 3_600_000
    assert calc["selected_precedent_bill_no"] == "2213320"
    assert items[0]["year_amounts"] == [3_600_000] * 5


def test_current_bill_can_never_be_executed_as_its_own_precedent() -> None:
    items = [_item("review_required")]
    apply_precedent_fallback(
        items,
        _verified_workflow("2217718"),
        current_bill_no="2217718",
    )
    calc = items[0]["calc_result"]
    assert calc["annual_cost_won"] == 8_000_000
    assert calc["evidence_route"]["level"] == "blocked_self_match"
    assert calc["evidence_route"]["selected_bill_no"] is None


def test_missing_committee_size_returns_review_range_instead_of_crashing() -> None:
    result = _calculate_committee_impl(
        CommitteeVars("정책위원회", None, None, None)
    )
    assert result["status"] == "review_required"
    assert result["paid_members_range"] == [7, 15]
    assert result["annual_cost_won_range"] == [7_000_000, 15_000_000]


def test_training_support_is_not_misrouted_as_civil_service_personnel() -> None:
    categories = route_article(
        "전문인력 양성기관을 지정하여 교육하고 필요한 비용을 지원할 수 있다."
    )
    assert "1_인건비_물건비" not in categories
    assert "2_이전지출" in categories
