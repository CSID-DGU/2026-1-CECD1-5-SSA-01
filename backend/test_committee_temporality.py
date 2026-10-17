from unittest.mock import patch

from backend.committee_gate import CommitteeEntity
from backend.committee_temporality import decide_committee_temporality
from backend.tag_parsers import CommitteeVars
from backend.tag_pipeline import _run_committee_entity
from backend.tag_timeseries import aggregate


EVENT_TEXT = """
전담재판부후보추천위원회는 후보자를 추천한다.
제17조제5항제1호 및 제2호에 따른 후보자추천위원회는 이 법 시행 후 2주 이내에,
제17조제5항제3호에 따른 후보자추천위원회는 제1심판결 선고일부터 2주 이내에 구성을 완료하여야 한다.
"""

QUOTES = [
    "제17조제5항제1호 및 제2호에 따른 후보자추천위원회는 이 법 시행 후 2주 이내에",
    "제17조제5항제3호에 따른 후보자추천위원회는 제1심판결 선고일부터 2주 이내에",
]


def test_verified_bounded_events_replace_annual_fallback_with_total():
    entity = CommitteeEntity(
        name="전담재판부후보추천위원회",
        article_nos=["제17조", "부칙 제1조"],
        texts=[EVENT_TEXT],
    )
    values = CommitteeVars(
        name=entity.name,
        total_members=9,
        ex_officio=0,
        meetings=None,
        temporal_mode="event_driven",
        finite_event_count=2,
        temporal_evidence_quotes=QUOTES,
    )
    annual_fallback = {
        "status": "calculated_low_confidence",
        "annual_cost_won": 12_600_000,
        "paid_members": 9,
        "unit_cost_won": 350_000,
        "meetings": 4,
        "meetings_source": "fallback_default_n36",
    }

    with (
        patch("backend.tag_pipeline.extract_committee_vars", return_value=values),
        patch("backend.tag_pipeline.rule_engine.calculate_committee", return_value=annual_fallback),
    ):
        item = _run_committee_entity(entity, "가상 법률안")

    calc = item["calc_result"]
    assert calc["status"] == "calculated_finite_event_total"
    assert calc["finite_event_count"] == 2
    assert calc["finite_event_total_cost_won"] == 6_300_000
    assert calc["event_year_allocation_unresolved"] is True
    assert item["year_amounts"] == [0, 0, 0, 0, 0]
    summary = aggregate([item])
    assert summary["unallocated_total_won"] == 6_300_000
    assert summary["grand_total_including_unallocated_won"] == 6_300_000


def test_unverified_llm_quote_does_not_change_existing_result():
    decision = decide_committee_temporality(
        "정책위원회를 둔다. 위원장이 필요한 때 회의를 소집한다.",
        proposed_mode="event_driven",
        proposed_event_count=1,
        evidence_quotes=["이 법 시행 후 2주 이내에 추천한다."],
    )
    assert decision.kind == "unknown"


def test_explicit_periodic_cadence_wins_over_event_proposal():
    decision = decide_committee_temporality(
        "위원회는 후보를 추천하기 위해 매년 2회 소집한다.",
        proposed_mode="event_driven",
        proposed_event_count=1,
        evidence_quotes=["후보를 추천한다"],
    )
    assert decision.kind == "annual"
