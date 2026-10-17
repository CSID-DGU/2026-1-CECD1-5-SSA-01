from backend.article_extraction_engine import (
    extract_inline_amendment_articles,
    split_articles_regex,
)
from backend.committee_gate import group_committee_articles


TEXT = """
제안이유에서 안 제44조의2를 언급한다.
법원조직법 일부를 다음과 같이 개정한다.
제44조의2제1항 중 “한다.”를 “하며 외부전문가등으로 구성된 15명 이내의
법관평가위원회를 둔다.”로 하고, 각 호를 다음과 같이 신설하며,
1. 국회가 추천하는 사람 5명
2. 법률가단체가 추천하는 사람 5명
3. 법원 내부 구성원 5명
부 칙
이 법은 공포 후 6개월이 경과한 날부터 시행한다.
신ㆍ구조문대비표
제44조의2 현행 문구에도 법관평가위원회가 있다.
"""


def test_inline_replacement_becomes_changed_article():
    rows = extract_inline_amendment_articles(TEXT)
    assert len(rows) == 1
    assert rows[0]["no"] == "제44조의2"
    assert "15명 이내의" in rows[0]["text"]
    assert "공포 후 6개월" not in rows[0]["text"]
    assert "현행 문구" not in rows[0]["text"]


def test_regex_split_includes_recovered_inline_article():
    rows = split_articles_regex(TEXT)
    assert [row["no"] for row in rows] == ["제44조의2"]


def test_membership_modifier_is_not_part_of_committee_name():
    entities = group_committee_articles(split_articles_regex(TEXT))
    assert [entity.name for entity in entities] == ["법관평가위원회"]
