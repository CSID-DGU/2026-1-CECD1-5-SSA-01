from backend.estimator_v2.org_admin_resolver import (
    CanonicalInput,
    OrgAdminPlanRequest,
    resolve_org_admin_plan,
)


def _input(value, unit: str, source: str = "law_text") -> CanonicalInput:
    return CanonicalInput(value=value, unit=unit, source=source)


def test_single_committee_meeting_formula() -> None:
    result = resolve_org_admin_plan(
        OrgAdminPlanRequest(
            route="committee",
            components=("committee_meeting",),
            inputs={
                "paid_member_count": _input(7, "person"),
                "annual_meetings": _input(4, "meeting/year"),
                "meeting_unit_price": _input(300_000, "KRW/person/meeting"),
            },
        )
    )
    assert result.status == "computed_review"
    assert result.rows[0].formula_key == "COMMITTEE_MEETING_V1"
    assert result.year_totals_thousand == [8_400] * 5


def test_multi_instance_committee_includes_replication_count() -> None:
    result = resolve_org_admin_plan(
        OrgAdminPlanRequest(
            route="committee",
            components=("committee_meeting",),
            inputs={
                "committee_instance_count": _input(243, "instance"),
                "paid_member_count": _input(10, "person"),
                "annual_meetings": _input(4, "meeting/year"),
                "meeting_unit_price": _input(300_000, "KRW/person/meeting"),
            },
        )
    )
    assert result.rows[0].formula_key == "COMMITTEE_MULTI_INSTANCE_V1"
    assert result.year_totals_thousand == [2_916_000] * 5


def test_organization_bundle_derives_salary_for_follow_on_components() -> None:
    result = resolve_org_admin_plan(
        OrgAdminPlanRequest(
            route="organization",
            components=(
                "personnel",
                "employer_contribution",
                "basic_expense",
                "asset",
            ),
            inputs={
                "headcount": _input(10, "person", "user_input"),
                "salary_per_person": _input(50_000_000, "KRW/person/year", "official_standard"),
                "employer_contribution_rate": _input(0.13, "ratio", "official_standard"),
                "basic_expense_ratio": _input(0.10, "ratio", "verified_precedent"),
                "asset_unit_price_per_person": _input(5_000_000, "KRW/person", "official_standard"),
            },
        )
    )
    assert [row.formula_key for row in result.rows] == [
        "ORG_PERSONNEL_AVERAGE_V1",
        "ORG_EMPLOYER_CONTRIBUTION_V1",
        "ORG_BASIC_EXPENSE_RATIO_V1",
        "ORG_ASSET_PER_PERSON_V1",
    ]
    assert result.year_totals_thousand == [665_000, 615_000, 615_000, 615_000, 615_000]


def test_missing_target_scale_stops_personnel_calculation() -> None:
    result = resolve_org_admin_plan(
        OrgAdminPlanRequest(
            route="organization",
            components=("personnel",),
            inputs={
                "salary_per_person": _input(50_000_000, "KRW/person/year", "official_standard")
            },
        )
    )
    assert result.status == "partial"
    assert result.rows[0].status == "needs_user_input"
    assert result.rows[0].missing_variables == ["headcount"]


def test_unverified_profile_is_rejected_by_default() -> None:
    profile = {
        "profile_key": "p1",
        "source_item_key": "item1",
        "component": "committee_meeting",
    }
    evidence = [
        {
            "profile_key": "p1",
            "evidence_key": f"e{index}",
            "canonical_key": key,
            "normalized_value": value,
            "normalized_unit": unit,
            "unit_status": "normalized",
            "review_status": "candidate",
            "transfer_policy": "review_required",
        }
        for index, (key, value, unit) in enumerate(
            [
                ("paid_member_count", 7, "person"),
                ("annual_meetings", 4, "meeting/year"),
                ("meeting_unit_price", 300_000, "KRW/person/meeting"),
            ]
        )
    ]
    result = resolve_org_admin_plan(
        OrgAdminPlanRequest(
            route="committee",
            components=("committee_meeting",),
            selected_profile_keys={"committee_meeting": "p1"},
            context_gates_passed=True,
        ),
        profiles=[profile],
        evidence=evidence,
    )
    assert result.rows[0].status == "needs_evidence"
    assert "UNVERIFIED_EVIDENCE_REJECTED" in result.rows[0].reason_codes


def test_diagnostic_profile_never_looks_production_verified() -> None:
    profile = {
        "profile_key": "p1",
        "source_item_key": "item1",
        "component": "committee_operation",
    }
    values = [
        ("committee_instance_count", 17, "instance"),
        ("committee_instance_count", 226, "instance"),
        ("paid_member_count", 10, "person"),
        ("annual_meetings", 4, "meeting/year"),
        ("meeting_unit_price", 300_000, "KRW/person/meeting"),
    ]
    evidence = [
        {
            "profile_key": "p1",
            "evidence_key": f"e{index}",
            "canonical_key": key,
            "normalized_value": value,
            "normalized_unit": unit,
            "unit_status": "normalized",
            "review_status": "candidate",
            "transfer_policy": "review_required",
        }
        for index, (key, value, unit) in enumerate(values)
    ]
    result = resolve_org_admin_plan(
        OrgAdminPlanRequest(
            route="committee",
            components=("committee_meeting",),
            selected_profile_keys={"committee_meeting": "p1"},
            context_gates_passed=True,
            diagnostic_allow_candidate_evidence=True,
        ),
        profiles=[profile],
        evidence=evidence,
    )
    assert result.year_totals_thousand == [2_916_000] * 5
    assert "UNVERIFIED_EVIDENCE_USED_DIAGNOSTIC" in result.rows[0].reason_codes
    assert result.warnings


def test_target_profile_is_excluded_even_in_diagnostic_mode() -> None:
    profile = {
        "profile_key": "target-profile",
        "source_item_key": "target-item",
        "bill_id": "PRC_TARGET",
        "component": "personnel",
        "raw_attributes": {
            "bill_no": "2124970",
            "propose_date": "2023-09-27",
        },
    }
    evidence = [
        {
            "profile_key": "target-profile",
            "evidence_key": "target-salary",
            "canonical_key": "salary_per_person",
            "normalized_value": 50_000_000,
            "normalized_unit": "KRW/person/year",
            "unit_status": "normalized",
            "review_status": "candidate",
            "transfer_policy": "review_required",
        }
    ]
    result = resolve_org_admin_plan(
        OrgAdminPlanRequest(
            route="organization",
            components=("personnel",),
            target_bill_no="2124970",
            cutoff_date="2023-09-27",
            inputs={"headcount": _input(10, "person", "law_text")},
            selected_profile_keys={"personnel": "target-profile"},
            context_gates_passed=True,
            diagnostic_allow_candidate_evidence=True,
        ),
        profiles=[profile],
        evidence=evidence,
    )
    assert result.rows[0].status == "needs_evidence"
    assert result.rows[0].missing_variables == ["salary_per_person"]
    assert "TARGET_PROFILE_EXCLUDED" in result.rows[0].reason_codes


def test_future_profile_is_excluded() -> None:
    profile = {
        "profile_key": "future-profile",
        "source_item_key": "future-item",
        "component": "personnel",
        "raw_attributes": {
            "bill_no": "2219999",
            "propose_date": "2026-01-01",
        },
    }
    evidence = [
        {
            "profile_key": "future-profile",
            "evidence_key": "future-salary",
            "canonical_key": "salary_per_person",
            "normalized_value": 50_000_000,
            "normalized_unit": "KRW/person/year",
            "unit_status": "normalized",
            "review_status": "verified",
            "transfer_policy": "comparable_only",
        }
    ]
    result = resolve_org_admin_plan(
        OrgAdminPlanRequest(
            route="organization",
            components=("personnel",),
            cutoff_date="2025-12-31",
            inputs={"headcount": _input(10, "person", "law_text")},
            selected_profile_keys={"personnel": "future-profile"},
            context_gates_passed=True,
        ),
        profiles=[profile],
        evidence=evidence,
    )
    assert result.rows[0].status == "needs_evidence"
    assert "FUTURE_PROFILE_EXCLUDED" in result.rows[0].reason_codes
