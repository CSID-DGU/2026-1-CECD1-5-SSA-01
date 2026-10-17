import unittest

from backend.erce_web.estimator_v2.top_level_router import (
    BillRoutingRequest,
    CostProfile,
    FinalDisposition,
    FiscalRouteRequest,
    ROUTE_FACILITY,
    ROUTE_ORGANIZATION,
    ROUTE_WELFARE,
    RouteReadiness,
    RoutingEvidence,
    route_bill,
)


def _value(value, unit: str, source: str = "official_standard") -> dict:
    return {"value": value, "unit": unit, "source": source}


def _organization_route(*, headcount=None, annual_operating_amount=None):
    inputs = {
        "salary_per_person": _value(50_000_000, "KRW/person/year"),
    }
    components = ["personnel"]
    if headcount is not None:
        inputs["headcount"] = _value(headcount, "person", "user_input")
    if annual_operating_amount is not None:
        components.append("operating_expense")
        inputs["annual_operating_amount"] = _value(
            annual_operating_amount,
            "KRW/year",
            "user_input",
        )
    return FiscalRouteRequest(
        event_id="ORG-1",
        route=ROUTE_ORGANIZATION,
        description="조직 신설",
        payload={"components": components, "inputs": inputs},
    )


class TopLevelRouterTests(unittest.TestCase):
    def test_no_fiscal_effect_routes_to_not_applicable(self) -> None:
        decision = route_bill(
            BillRoutingRequest(
                routes=(
                    FiscalRouteRequest(
                        event_id="E1",
                        route=ROUTE_WELFARE,
                        description="명칭 변경",
                        readiness=RouteReadiness.NO_FISCAL_EFFECT,
                    ),
                )
            )
        )
        self.assertEqual(decision.disposition, FinalDisposition.NOT_APPLICABLE)

    def test_verified_security_only_routes_to_reason_2(self) -> None:
        decision = route_bill(
            BillRoutingRequest(
                routes=(
                    FiscalRouteRequest(
                        event_id="SEC-1",
                        route=ROUTE_FACILITY,
                        description="군사기밀 관련 비용",
                        readiness=RouteReadiness.SECURITY_RESTRICTED,
                        evidence=(
                            RoutingEvidence(
                                kind="security_review",
                                source_ref="보안검토-1",
                                quote="비용추계 대상이 군사기밀에 관한 사항임",
                                verified=True,
                            ),
                        ),
                    ),
                )
            )
        )
        self.assertEqual(decision.disposition, FinalDisposition.NON_ATTACHMENT_2)

    def test_unverified_security_candidate_requires_review(self) -> None:
        decision = route_bill(
            BillRoutingRequest(
                routes=(
                    FiscalRouteRequest(
                        event_id="SEC-1",
                        route=ROUTE_FACILITY,
                        description="국방 관련 조문",
                        readiness=RouteReadiness.SECURITY_RESTRICTED,
                        evidence=(
                            RoutingEvidence(
                                kind="law_text",
                                source_ref="제4조",
                                quote="국방부장관은 시설을 설치할 수 있다",
                                verified=False,
                            ),
                        ),
                    ),
                )
            )
        )
        self.assertEqual(decision.disposition, FinalDisposition.REVIEW_REQUIRED)

    def test_reason_3_requires_missing_variables_and_verified_official_evidence(self) -> None:
        decision = route_bill(
            BillRoutingRequest(
                routes=(
                    FiscalRouteRequest(
                        event_id="ORG-UNKNOWN",
                        route=ROUTE_ORGANIZATION,
                        description="조직 규모 전부 위임",
                        readiness=RouteReadiness.TECHNICALLY_UNESTIMABLE,
                        missing_variables=("organization_scale", "headcount"),
                        evidence=(
                            RoutingEvidence(
                                kind="official_non_attachment",
                                source_ref="2217239",
                                quote="직제와 정원을 대통령령으로 정하도록 함",
                                verified=True,
                            ),
                        ),
                    ),
                )
            )
        )
        self.assertEqual(decision.disposition, FinalDisposition.NON_ATTACHMENT_3)

    def test_reason_3_without_official_evidence_stays_review_required(self) -> None:
        decision = route_bill(
            BillRoutingRequest(
                routes=(
                    FiscalRouteRequest(
                        event_id="ORG-UNKNOWN",
                        route=ROUTE_ORGANIZATION,
                        description="정원 미상",
                        readiness=RouteReadiness.TECHNICALLY_UNESTIMABLE,
                        missing_variables=("headcount",),
                    ),
                )
            )
        )
        self.assertEqual(decision.disposition, FinalDisposition.REVIEW_REQUIRED)

    def test_small_complete_organization_estimate_routes_to_reason_1(self) -> None:
        decision = route_bill(
            BillRoutingRequest(routes=(_organization_route(headcount=10),))
        )
        self.assertEqual(decision.year_totals_thousand, (500_000,) * 5)
        self.assertEqual(decision.disposition, FinalDisposition.NON_ATTACHMENT_1)

    def test_large_complete_organization_estimate_routes_to_cost_estimate(self) -> None:
        decision = route_bill(
            BillRoutingRequest(routes=(_organization_route(headcount=30),))
        )
        self.assertEqual(decision.year_totals_thousand, (1_500_000,) * 5)
        self.assertEqual(decision.disposition, FinalDisposition.COST_ESTIMATE)

    def test_computed_and_missing_organization_components_route_to_partial(self) -> None:
        decision = route_bill(
            BillRoutingRequest(
                routes=(
                    _organization_route(
                        headcount=None,
                        annual_operating_amount=2_000_000_000,
                    ),
                )
            )
        )
        self.assertEqual(decision.year_totals_thousand, (2_000_000,) * 5)
        self.assertEqual(decision.disposition, FinalDisposition.PARTIAL_ESTIMATE)

    def test_missing_org_input_is_not_reason_3(self) -> None:
        decision = route_bill(
            BillRoutingRequest(routes=(_organization_route(headcount=None),))
        )
        self.assertEqual(decision.disposition, FinalDisposition.REVIEW_REQUIRED)

    def test_unimplemented_domain_is_not_reason_3(self) -> None:
        decision = route_bill(
            BillRoutingRequest(
                routes=(
                    FiscalRouteRequest(
                        event_id="WELFARE-1",
                        route=ROUTE_WELFARE,
                        description="급여 지급",
                    ),
                )
            )
        )
        self.assertEqual(decision.disposition, FinalDisposition.REVIEW_REQUIRED)
        self.assertIn(
            "ROUTE_ENGINE_NOT_IMPLEMENTED",
            decision.outcomes[0].reason_codes,
        )

    def test_computable_event_prevents_whole_bill_reason_3(self) -> None:
        decision = route_bill(
            BillRoutingRequest(
                routes=(
                    _organization_route(headcount=30),
                    FiscalRouteRequest(
                        event_id="FACILITY-UNKNOWN",
                        route=ROUTE_FACILITY,
                        description="시설 규모 미정",
                        readiness=RouteReadiness.TECHNICALLY_UNESTIMABLE,
                        missing_variables=("facility_scale",),
                        evidence=(
                            RoutingEvidence(
                                kind="official_non_attachment",
                                source_ref="2125200",
                                quote="구체적인 시설 수와 사업규모를 예측하기 어려움",
                                verified=True,
                            ),
                        ),
                    ),
                )
            )
        )
        self.assertEqual(decision.disposition, FinalDisposition.PARTIAL_ESTIMATE)

    def test_temporary_cost_uses_total_threshold(self) -> None:
        route = FiscalRouteRequest(
            event_id="ORG-ASSET",
            route=ROUTE_ORGANIZATION,
            description="일회성 자산취득",
            payload={
                "components": ["asset"],
                "inputs": {
                    "headcount": _value(400, "person", "user_input"),
                    "asset_unit_price_per_person": _value(
                        5_000_000,
                        "KRW/person",
                    ),
                },
            },
        )
        decision = route_bill(
            BillRoutingRequest(
                routes=(route,),
                cost_profile=CostProfile.TEMPORARY,
            )
        )
        self.assertEqual(sum(decision.year_totals_thousand), 2_000_000)
        self.assertEqual(decision.disposition, FinalDisposition.NON_ATTACHMENT_1)


if __name__ == "__main__":
    unittest.main()
