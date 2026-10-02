import unittest

from backend.erce.scripts.classify_policy_purpose_pdfs import classify


class PolicyPurposeClassifierTest(unittest.TestCase):
    def labels(self, title, cost_text):
        return {(row["group"], row["subtype"]) for row in classify(title, cost_text)}

    def test_committee_and_industry_support_can_both_apply(self):
        labels = self.labels(
            "마을기업 지원에 관한 법률안",
            "마을기업지원위원회를 설치·운영한다. 마을기업에 재정적 지원을 할 수 있다.")
        self.assertIn(("조직구성_행정지원", "위원회_협의회"), labels)
        self.assertIn(("사업진흥_기반조성", "재정지원"), labels)

    def test_existing_medical_institution_is_not_new_organization(self):
        labels = self.labels(
            "참전유공자 예우법 일부개정법률안",
            "참전명예수당을 인상한다. 국가가 설치·운영하는 의료기관에서 진료한다.")
        self.assertIn(("사회보장_교육지원", "사회보장급여"), labels)
        self.assertNotIn(("조직구성_행정지원", "조직신설_확대"), labels)

    def test_revenue_bill_is_not_forced_into_excerpted_spending_groups(self):
        self.assertEqual(self.labels("소득세법 일부개정법률안", "세액공제율을 변경한다."), set())


if __name__ == "__main__":
    unittest.main()
