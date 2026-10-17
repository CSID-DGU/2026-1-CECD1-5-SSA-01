from backend.committee_evidence_adapter import apply_evidence_workflow


def _committee() -> dict:
    return {
        "id": "committee-1",
        "name": "정책위원회",
        "status": "review_required",
        "formula": "회의 횟수 × 인원 × 단가",
        "annual_amount_thousand": 1,
        "total_amount_thousand": 5,
        "year_estimates": [
            {"year": year, "amount_thousand": 1} for year in range(1, 6)
        ],
        "variables": {
            "meeting_count": {"value": 4, "confirmed": False, "blocking": False},
            "paid_members": {"value": 8, "confirmed": False, "blocking": False},
            "allowance_won": {"value": 200_000, "confirmed": False, "blocking": False},
        },
    }


def test_verified_package_overrides_preview_amount() -> None:
    committees = [_committee()]
    workflow = {
        "covered": {
            "decision": "calculated",
            "ready_for_auto_publish": True,
            "selected_bill_no": "P-1",
            "warnings": [],
            "package": {"decision": "exact_package"},
            "line_items": [
                {
                    "item_name": "정책위원회 운영비",
                    "formula": "10명 × 20만원 × 4회",
                    "full_year_thousand": 8_000,
                    "yearly_thousand": [8_000] * 5,
                }
            ],
        },
        "components": [],
    }
    apply_evidence_workflow(committees, workflow)
    result = committees[0]
    assert result["calculation_mode"] == "verified_package"
    assert result["annual_amount_thousand"] == 8_000
    assert result["total_amount_thousand"] == 40_000
    assert result["evidence_route"]["level"] == "verified"


def test_component_candidate_requires_confirmation_before_money_preview() -> None:
    committees = [_committee()]
    workflow = {
        "covered": {
            "decision": "needs_user_input",
            "blockers": ["no_complete_precedent_package"],
            "package": {"decision": "abstain", "selected_bill_no": None},
            "line_items": [],
        },
        "components": [
            {
                "target_name": "정책위원회",
                "candidate_top5": [
                    {
                        "bill_no": "P-2",
                        "bill_name": "선례법안",
                        "committee_name": "유사정책위원회",
                        "score": 11,
                        "paid_members": 8,
                        "annual_meetings": 4,
                        "meeting_unit_price": 200_000,
                        "source_texts": ["연 4회, 20만원"],
                    }
                ],
            }
        ],
    }
    apply_evidence_workflow(committees, workflow)
    result = committees[0]
    assert result["annual_amount_thousand"] is None
    assert result["total_amount_thousand"] is None
    assert result["status"] == "blocked_missing_variables"
    assert all(variable["blocking"] for variable in result["variables"].values())
    assert result["evidence_route"]["level"] == "recommended"
    assert result["reference_candidates"][0]["bill_no"] == "P-2"
