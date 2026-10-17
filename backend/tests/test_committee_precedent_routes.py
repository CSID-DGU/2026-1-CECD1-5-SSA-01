from __future__ import annotations

from backend.scripts.evaluate_committee_precedent_routes import (
    CandidateText,
    _eligible_at_cutoff,
    _structure_compatibility,
    _target_passages,
    _select_relation_candidate,
)


def _ranked_candidate(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "bill_no": "source",
        "same_law": False,
        "title_similarity": 0.0,
        "template_similarity": 0.0,
        "completeness": 1.0,
        "relation_score": 0.0,
    }
    row.update(overrides)
    return row


def test_same_law_history_requires_matching_cost_event() -> None:
    ranking = [
        _ranked_candidate(
            bill_no="right",
            same_law=True,
            template_similarity=0.48,
            relation_score=0.85,
        ),
        _ranked_candidate(bill_no="other", relation_score=0.25),
    ]
    assert _select_relation_candidate(ranking) == ("retrieve", "right")

    ranking[0]["template_similarity"] = 0.05
    assert _select_relation_candidate(ranking) == ("abstain", None)


def test_same_law_reintroductions_are_corroboration_not_competitors() -> None:
    ranking = [
        _ranked_candidate(
            bill_no="latest-exact",
            same_law=True,
            template_similarity=0.95,
            relation_score=0.98,
        ),
        _ranked_candidate(
            bill_no="older-same-lineage",
            same_law=True,
            template_similarity=0.92,
            relation_score=0.978,
        ),
        _ranked_candidate(bill_no="unrelated", relation_score=0.22),
    ]
    assert _select_relation_candidate(ranking) == ("retrieve", "latest-exact")


def test_weak_same_law_amendment_is_not_corroboration() -> None:
    ranking = [
        _ranked_candidate(
            bill_no="top",
            same_law=True,
            template_similarity=0.40,
            relation_score=0.85,
        ),
        _ranked_candidate(
            bill_no="different-cost-event",
            same_law=True,
            template_similarity=0.05,
            relation_score=0.83,
        ),
    ]
    assert _select_relation_candidate(ranking) == ("abstain", None)


def test_template_lineage_requires_title_structure_and_margin() -> None:
    ranking = [
        _ranked_candidate(
            bill_no="lineage",
            title_similarity=0.32,
            template_similarity=0.70,
            relation_score=0.56,
        ),
        _ranked_candidate(bill_no="runner-up", relation_score=0.25),
    ]
    assert _select_relation_candidate(ranking) == ("retrieve", "lineage")

    ranking[1]["relation_score"] = 0.53
    assert _select_relation_candidate(ranking) == ("abstain", None)


def test_completeness_cannot_rescue_an_unrelated_candidate() -> None:
    ranking = [
        _ranked_candidate(
            bill_no="complete-but-unrelated",
            completeness=1.0,
            relation_score=0.90,
        )
    ]
    assert _select_relation_candidate(ranking) == ("abstain", None)


def test_reply_date_not_proposal_date_controls_historical_availability() -> None:
    candidate = CandidateText(
        bill_no="prior-proposal",
        bill_name="유사 법률안",
        propose_date="2026-01-30",
        available_date="2026-02-25",
        chunks=("위원회 추계",),
    )
    assert not _eligible_at_cutoff(
        candidate,
        target_bill_no="target",
        cutoff_date="2026-02-03",
    )
    assert _eligible_at_cutoff(
        candidate,
        target_bill_no="target",
        cutoff_date="2026-02-26",
    )
    assert not _eligible_at_cutoff(
        candidate,
        target_bill_no="target",
        cutoff_date="2026-02-25",
    )


def test_persisted_source_passage_does_not_require_a_pdf() -> None:
    case = {
        "target_passages": ["제7조 위원회를 둔다."],
        "source_pdf": "does-not-exist.pdf",
    }
    assert _target_passages(case) == ["제7조 위원회를 둔다."]


def test_changed_legal_structure_downgrades_same_law_history() -> None:
    status, reasons = _structure_compatibility(
        "위원장 1명을 포함한 9명 이내로 구성하고 전문위원회를 둘 수 있다.",
        "위원장 1명을 포함한 9명 이내로 구성하고 사무기구를 둔다.",
    )
    assert status == "changed"
    assert "secretariat_changed" in reasons
    assert "subcommittee_changed" in reasons


def test_same_member_structure_is_compatible() -> None:
    status, reasons = _structure_compatibility(
        "위원장 1명을 포함하여 10명 이내의 위원으로 구성한다.",
        "위원장 1명을 포함한 10명 이내의 위원으로 구성함.",
    )
    assert status == "compatible"
    assert reasons == []
