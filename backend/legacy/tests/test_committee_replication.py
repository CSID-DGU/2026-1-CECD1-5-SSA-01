from backend.legacy.committee.committee_replication import detect_replication


MIXED_LOCAL_ARTICLE = """
시ㆍ도 돌봄근로자 처우개선위원회와 시ㆍ군ㆍ구 돌봄근로자
처우개선위원회를 각각 둔다.
"""


def test_entity_name_wins_when_two_jurisdiction_units_share_article():
    province = detect_replication(
        MIXED_LOCAL_ARTICLE, "시ㆍ도돌봄근로자처우개선위원회"
    )
    municipal = detect_replication(
        MIXED_LOCAL_ARTICLE, "시ㆍ군ㆍ구돌봄근로자처우개선위원회"
    )

    assert province["factor"] == 17
    assert municipal["factor"] == 229


def test_generic_local_government_remains_unresolved():
    result = detect_replication(
        "지방자치단체에 지역금융위원회를 둔다.", "지역금융위원회"
    )

    assert result["factor"] == 1
    assert result["confident"] is False
