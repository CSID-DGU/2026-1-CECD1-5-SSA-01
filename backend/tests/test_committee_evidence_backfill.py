from __future__ import annotations

from backend.legacy.scripts.backfill_committee_evidence import (
    build_backfill,
    classify_evidence_role,
    committee_name_from_item,
    normalize_value,
    recover_formula_operands,
)


def test_committee_name_stops_before_cost_item_suffix() -> None:
    assert committee_name_from_item("국립대학병원발전위원회 설치·운영") == "국립대학병원발전위원회"


def test_variable_role_distinguishes_paid_members_from_total_members() -> None:
    paid = {
        "variable_type": "target_count",
        "variable_name": "민간위원 수",
        "variable_unit": "명",
        "source_text": "민간위원 6명을 위촉",
    }
    total = {
        "variable_type": "target_count",
        "variable_name": "총 위원 수",
        "variable_unit": "명",
        "source_text": "위원장 포함 총 위원 수",
    }
    assert classify_evidence_role(paid) == "paid_members"
    assert classify_evidence_role(total) == "total_members"


def test_variable_role_keeps_incremental_members_separate() -> None:
    incremental = {
        "variable_type": "target_count",
        "variable_name": "추가 위촉위원 수",
        "variable_unit": "명",
        "source_text": "현행보다 추가되는 8명에게 수당 지급",
    }
    assert classify_evidence_role(incremental) == "incremental_paid_members"


def test_event_driven_meetings_are_not_annual_frequency() -> None:
    meetings = {
        "variable_type": "frequency",
        "variable_name": "위원회당 회의개최횟수",
        "variable_unit": "회",
        "source_text": "추천위원회마다 회의 3회 개최",
    }
    assert classify_evidence_role(meetings) == "meetings_per_event"


def test_committee_count_is_not_misclassified_as_member_count() -> None:
    instances = {
        "variable_type": "target_count",
        "variable_name": "기초자치단체 위원회 수",
        "variable_value": 226,
        "variable_unit": "개",
        "source_text": "각 기초자치단체에 위원회를 둔다",
    }
    assert classify_evidence_role(instances) == "committee_instances"


def test_cost_units_are_normalized_to_won() -> None:
    assert normalize_value(25, "만원/인·회", "meeting_unit_price") == (250_000, "원")


def test_explicit_report_formula_can_recover_missing_operands() -> None:
    variables, formula = recover_formula_operands(
        [
            {
                "documentType": "cost_estimate",
                "text": (
                    "환경발전위원회 설치 비용은 민간위원 6명 × 참석수당 20만원 "
                    "× 회의 개최횟수 3회 = 연 360만원이다."
                ),
            }
        ],
        "환경발전위원회",
    )
    assert formula == "민간위원6명×참석수당20만원×회의개최횟수3회"
    assert [value["variable_value"] for value in variables] == [6.0, 20.0, 3.0]


def test_build_backfill_links_profile_formula_and_operand_evidence() -> None:
    bill_id = "BILL-1"
    struct_id = f"{bill_id}::cost_estimate"
    item_id = f"{struct_id}::item1"
    data = {
        "cost_estimate_structures": [
            {
                "struct_id": struct_id,
                "bill_id": bill_id,
                "bill_no": "100",
                "bill_name": "환경발전법안",
                "propose_date": "2026-01-01",
            }
        ],
        "cost_estimate_items": [
            {
                "item_id": item_id,
                "struct_id": struct_id,
                "bill_id": bill_id,
                "item_category": "운영비",
                "item_name": "환경발전위원회 설치·운영",
                "trigger_ref": "안 제6조",
            }
        ],
        "cost_estimate_variables": [
            {
                "item_id": item_id,
                "variable_type": "target_count",
                "variable_name": "민간위원 수",
                "variable_value": 6,
                "variable_unit": "명",
                "source_text": "민간위원 6명을 위촉하는 것으로 가정",
            },
            {
                "item_id": item_id,
                "variable_type": "frequency",
                "variable_name": "연간 회의 횟수",
                "variable_value": 3,
                "variable_unit": "회/년",
                "source_text": "연간 3회 개최",
            },
            {
                "item_id": item_id,
                "variable_type": "unit_cost",
                "variable_name": "회의수당",
                "variable_value": 20,
                "variable_unit": "만원",
                "source_text": "예산 집행지침에 따라 회당 20만원",
            },
        ],
        "cost_estimate_amounts": [
            {
                "item_id": item_id,
                "formula_text": "민간위원 6명 × 연 3회 × 20만원",
            }
        ],
        "bill_text_for_tag": [
            {
                "chunkId": "BILL-1:1",
                "billId": bill_id,
                "chunkIndex": 1,
                "text": (
                    "제6조(환경발전위원회의 설치) 환경발전계획을 심의하기 위하여 "
                    "장관 소속으로 환경발전위원회를 둔다. 위원장 1명을 포함한 "
                    "20명 이내의 위원으로 구성한다."
                ),
            }
        ],
    }
    profiles, atoms, summary = build_backfill(data)
    assert len(profiles) == 1
    assert profiles[0]["committee_name"] == "환경발전위원회"
    assert profiles[0]["total_member_count"] == 20
    assert profiles[0]["member_count_is_cap"] is True
    assert profiles[0]["formula_signature"] == "paid_members*annual_meetings*meeting_unit_price"
    roles = {atom["evidence_role"] for atom in atoms}
    assert {
        "paid_members",
        "annual_meetings",
        "meeting_unit_price",
        "formula_expression",
    }.issubset(roles)
    assert "profile_total_members" in roles
    assert "profile_lifecycle" in roles
    assert summary["quality"]["orphan_atoms"] == 0
