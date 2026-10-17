from unittest.mock import patch

from backend.committee_gate import CommitteeEntity
from backend.tag_parsers import CommitteeVars
from backend.tag_pipeline import _run_committee_entity
from backend.tag_timeseries import (
    aggregate,
    category_to_year_amounts,
    category_to_year_amounts_range,
)


def test_discretionary_entity_keeps_computable_scenario_amount():
    entity = CommitteeEntity(
        name="가상위원회",
        article_nos=["제1조"],
        texts=["가상위원회를 둘 수 있다."],
        discretionary=True,
    )
    calculated = {
        "status": "calculated_with_rule",
        "annual_cost_won": 5_000_000,
        "trace": "5명 × 25만원 × 4회",
    }

    with (
        patch(
            "backend.tag_pipeline.extract_committee_vars",
            return_value=CommitteeVars(
                name="가상위원회", total_members=5, ex_officio=0, meetings=4
            ),
        ),
        patch("backend.tag_pipeline.rule_engine.calculate_committee", return_value=calculated),
    ):
        item = _run_committee_entity(entity, "가상 법률안")

    assert item["calc_result"]["status"] == "calculated_discretionary_scenario"
    assert item["calc_result"]["conditional_on_implementation"] is True
    assert item["year_amounts"] == [5_000_000] * 5


def test_unresolved_review_item_still_does_not_enter_totals():
    calc_result = {
        "status": "review_required",
        "annual_cost_won_range": [2_000_000, 7_000_000],
    }
    amounts = category_to_year_amounts(
        "1_인건비_물건비",
        calc_result,
    )
    amount_range = category_to_year_amounts_range(
        "1_인건비_물건비", calc_result
    )

    assert amounts == [0] * 5
    assert amount_range == [[2_000_000, 7_000_000]] * 5

    summary = aggregate([
        {"year_amounts": amounts, "year_amounts_range": amount_range},
    ])
    assert summary["grand_total_won"] == 0
    assert summary["grand_total_won_range"] == [10_000_000, 35_000_000]


def test_gate_entity_name_wins_over_parser_name():
    entity = CommitteeEntity(
        name="시ㆍ도위원회",
        article_nos=["제1조"],
        texts=["시ㆍ도위원회와 시ㆍ군ㆍ구위원회를 둔다."],
    )
    calculated = {
        "status": "calculated_with_rule",
        "annual_cost_won": 1,
    }

    with (
        patch(
            "backend.tag_pipeline.extract_committee_vars",
            return_value=CommitteeVars(
                name="시ㆍ군ㆍ구위원회", total_members=10, ex_officio=0, meetings=4
            ),
        ),
        patch("backend.tag_pipeline.rule_engine.calculate_committee", return_value=calculated) as calculate,
    ):
        _run_committee_entity(entity, "가상 법률안")

    assert calculate.call_args.args[0].name == "시ㆍ도위원회"
