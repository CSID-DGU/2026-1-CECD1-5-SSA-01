from backend.legacy.committee.committee_membership import derive_paid_members


def test_fixed_member_groups_produce_exact_paid_count():
    text = "국회교섭단체가 추천하는 사람 5명, 법률가단체가 추천하는 사람 5명, 법원 내부 구성원 5명"
    groups = [
        {"label": "국회 추천", "count": 5, "allocation": "fixed", "kind": "private_external", "evidence_quote": "국회교섭단체가 추천하는 사람 5명"},
        {"label": "법률가 추천", "count": 5, "allocation": "fixed", "kind": "private_external", "evidence_quote": "법률가단체가 추천하는 사람 5명"},
        {"label": "법원 내부", "count": 5, "allocation": "fixed", "kind": "internal_public_organization", "evidence_quote": "법원 내부 구성원 5명"},
    ]
    result = derive_paid_members(text, member_groups=groups, total_members_min=15, total_members_max=15)
    assert result is not None
    assert (result.low, result.high, result.exact) == (10, 10, True)


def test_equal_share_constraint_produces_paid_range():
    text = "공무원, 이해관계자, 전문가를 각각 동수로 구성한다."
    groups = [
        {"label": "공무원", "count": None, "allocation": "equal_share", "kind": "government_official", "evidence_quote": "공무원"},
        {"label": "이해관계자", "count": None, "allocation": "equal_share", "kind": "private_external", "evidence_quote": "이해관계자"},
        {"label": "전문가", "count": None, "allocation": "equal_share", "kind": "private_external", "evidence_quote": "전문가"},
    ]
    result = derive_paid_members(text, member_groups=groups, total_members_min=30, total_members_max=40)
    assert result is not None
    assert (result.low, result.high, result.exact) == (20, 26, False)


def test_unverified_quote_or_unknown_group_is_not_used():
    result = derive_paid_members(
        "위원은 3명이다.",
        member_groups=[{"label": "민간", "count": 3, "allocation": "fixed", "kind": "private_external", "evidence_quote": "민간위원 3명"}],
        total_members_min=3,
        total_members_max=3,
    )
    assert result is None
