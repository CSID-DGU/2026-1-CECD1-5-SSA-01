from __future__ import annotations

from backend.scripts.compare_committee_evidence_architectures import (
    _domain_history_score,
    _institution_history_score,
    _rrf,
    _target_anchored_text,
    cost_scopes,
    extract_features,
    target_required_scopes,
)


def test_structure_features_are_domain_generic() -> None:
    features = extract_features(
        "독립적으로 진상을 조사하는 특별위원회에 사무처와 상임위원을 둔다."
    )
    assert "function:investigation" in features
    assert "structure:independent" in features
    assert "structure:secretariat" in features
    assert "structure:standing_member" in features


def test_organization_heavy_target_requires_component_scopes() -> None:
    scopes = target_required_scopes("위원회에 사무기구와 필요한 직원을 둔다")
    assert scopes == {
        "cost:committee",
        "cost:personnel",
        "cost:basic",
        "cost:program",
    }
    assert "cost:basic" in cost_scopes("인건비 대비 기본경비 비중을 적용")


def test_rrf_rewards_cross_route_support_without_score_calibration() -> None:
    first = [{"bill_no": "a"}, {"bill_no": "b"}]
    second = [{"bill_no": "b"}, {"bill_no": "c"}]
    scores = _rrf([first, second])
    assert scores["b"] > scores["a"]
    assert scores["b"] > scores["c"]


def test_central_body_is_not_mislabeled_local_from_branch_geography() -> None:
    features = extract_features(
        "국무총리 소속 위원회는 특별시·광역시·특별자치시에 지부를 둘 수 있다"
    )
    assert "scope:central" in features
    assert "scope:local" not in features


def test_institution_history_prefers_matching_structure_and_cost_scope() -> None:
    target = {"scope:central", "structure:secretariat", "structure:standing_member"}
    required = {"cost:committee", "cost:personnel", "cost:basic"}
    strong = _institution_history_score(
        target,
        target,
        required,
        required,
        0.1,
    )
    weak = _institution_history_score(
        target,
        {"scope:local", "structure:subcommittee"},
        required,
        {"cost:committee"},
        0.8,
    )
    assert strong > weak


def test_domain_and_structure_are_scored_as_separate_fields() -> None:
    event = {"scope:central", "structure:independent", "structure:secretariat"}
    proposal = {"function:regulator", "function:rights_redress"}
    scopes = {"cost:personnel", "cost:basic", "cost:program"}
    relevant = _domain_history_score(
        event,
        proposal,
        event | proposal,
        scopes,
        scopes,
        0.1,
    )
    unrelated = _domain_history_score(
        event,
        proposal,
        {"scope:central", "function:strategy"},
        scopes,
        {"cost:program"},
        0.8,
    )
    assert relevant > unrelated


def test_anchored_query_keeps_named_appendix_passage() -> None:
    case = {"bill_name": "예시법안"}
    text = _target_anchored_text(
        case,
        ["부칙 제2조에 따라 설립준비위원회를 두고 6개월간 운영한다."],
    )
    assert text.startswith("예시법안 ")
    assert "설립준비위원회" in text
