import unittest

from backend.estimator_v2.precedent_first import (
    FiscalFactor,
    LLMConclusion,
    LLMFactorDecision,
    LocalPrecedent,
    LocalPrecedentIndex,
    build_contexts,
    build_decision_prompt,
    route_llm_decisions,
)
from backend.estimator_v2.top_level_router import FinalDisposition, ROUTE_REVENUE


def _precedent(*, bill_no="2120001", date="2023-01-01"):
    return LocalPrecedent(
        bill_no=bill_no,
        bill_name="과거 종합부동산세법 일부개정법률안",
        propose_date=date,
        reason_type="B",
        reason_text="대상 주택 및 납세자 수를 파악하기 어려워 추계가 곤란함.",
        evidence_text="특례 적용 대상 주택 수와 공시가격 자료가 없어 추계하기 곤란함.",
        mechanisms=("revenue_change",),
        missing_roles=("tax_base",),
    )


class PrecedentFirstTests(unittest.TestCase):
    def setUp(self):
        self.factor = FiscalFactor(
            event_id="REV-1",
            route=ROUTE_REVENUE,
            description="종합부동산세 특례 신설",
            article_ref="안 제71조의2",
            quote="특례 적용 주택을 과세 대상에서 제외한다.",
            fiscal_effect=True,
            mechanisms=("revenue_change",),
            missing_variables=("tax_base",),
        )

    def test_target_and_future_precedents_are_excluded(self):
        index = LocalPrecedentIndex((
            _precedent(bill_no="2120001", date="2023-01-01"),
            _precedent(bill_no="2129999", date="2025-01-01"),
            _precedent(bill_no="2127777", date="2023-03-01"),
        ))
        contexts = build_contexts(
            (self.factor,), index=index,
            target_bill_no="2127777", cutoff_date="2024-01-01",
        )
        self.assertEqual([hit.precedent.bill_no for hit in contexts[0].precedents], ["2120001"])

    def test_grounded_llm_reason_3_reaches_router(self):
        index = LocalPrecedentIndex((_precedent(),))
        contexts = build_contexts(
            (self.factor,), index=index,
            target_bill_no="2127777", cutoff_date="2024-01-01",
        )
        result = route_llm_decisions(
            contexts,
            (LLMFactorDecision(
                event_id="REV-1",
                conclusion=LLMConclusion.TECHNICALLY_UNESTIMABLE,
                reason="적용 대상과 과세표준 자료가 없어 세수 감소액을 산정할 수 없습니다.",
                precedent_bill_nos=("2120001",),
            ),),
        )
        self.assertEqual(result.decision.disposition, FinalDisposition.NON_ATTACHMENT_3)

    def test_ungrounded_reason_3_stays_review_required(self):
        contexts = build_contexts(
            (self.factor,), index=LocalPrecedentIndex(()),
            target_bill_no="2127777", cutoff_date="2024-01-01",
        )
        result = route_llm_decisions(
            contexts,
            (LLMFactorDecision(
                event_id="REV-1",
                conclusion=LLMConclusion.TECHNICALLY_UNESTIMABLE,
                reason="자료가 부족합니다.",
            ),),
        )
        self.assertEqual(result.decision.disposition, FinalDisposition.REVIEW_REQUIRED)

    def test_prompt_has_precedents_but_not_methodology_rag(self):
        contexts = build_contexts(
            (self.factor,), index=LocalPrecedentIndex((_precedent(),)),
            target_bill_no="2127777", cutoff_date="2024-01-01",
        )
        prompt = build_decision_prompt(contexts)
        self.assertIn("2120001", prompt)
        self.assertNotIn("비용추계의 이해", prompt)

