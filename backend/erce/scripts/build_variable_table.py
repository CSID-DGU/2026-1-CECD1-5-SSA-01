"""Upsert reviewed ERCE variables locally; does not alter the full sidecar DB."""
from __future__ import annotations

import argparse
from pathlib import Path

from backend.erce.reviewed_variable_rows import reviewed_variable_rows, burial_comparable_rows
from backend.erce.variable_evidence_store import DEFAULT_VARIABLE_DB, save_variable_rows
from backend.erce.interagency_meeting_evidence import interagency_meeting_rows, unification_council_annual_rows
from backend.erce.legislative_committee_evidence import legislative_committee_rows, policy_review_committee_rows
from backend.erce.executive_compensation_evidence import executive_position_difference_rows
from backend.erce.transfer_payment_evidence import transfer_payment_rows, veteran_allowance_rows
from backend.erce.insurance_premium_evidence import insurance_premium_rows
from backend.erce.health_insurance_care_evidence import (
    health_insurance_care_rows, health_insurance_care_answer_rows,
)
from backend.erce.health_insurance_general_support_evidence import (
    health_insurance_general_support_rows, health_insurance_general_support_answer_rows,
)
from backend.erce.spouse_leave_evidence import spouse_leave_rows
from backend.erce.infertility_leave_evidence import infertility_leave_rows
from backend.erce.child_asset_evidence import child_asset_rows
from backend.erce.child_allowance_evidence import child_allowance_rows
from backend.erce.parent_benefit_evidence import parent_benefit_rows
from backend.erce.care_worker_survey_evidence import care_worker_survey_rows
from backend.erce.village_enterprise_evidence import village_enterprise_rows
from backend.erce.veteran_allowance_baselines import veteran_allowance_baseline_rows
from backend.erce.committee_annual_operation_evidence import committee_annual_operation_rows
from backend.erce.information_system_evidence import sports_information_system_rows
from backend.erce.court_organization_evidence import court_organization_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_VARIABLE_DB)
    args = parser.parse_args()
    count = save_variable_rows(reviewed_variable_rows() + burial_comparable_rows()
                              + interagency_meeting_rows() + unification_council_annual_rows()
                              + legislative_committee_rows() + policy_review_committee_rows()
                              + executive_position_difference_rows() + transfer_payment_rows()
                              + veteran_allowance_rows()
                              + insurance_premium_rows()
                              + health_insurance_care_rows()
                              + health_insurance_care_answer_rows()
                              + health_insurance_general_support_rows()
                              + health_insurance_general_support_answer_rows()
                              + spouse_leave_rows()
                              + infertility_leave_rows()
                              + child_asset_rows()
                              + child_allowance_rows()
                              + parent_benefit_rows()
                              + care_worker_survey_rows()
                              + village_enterprise_rows()
                              + veteran_allowance_baseline_rows()
                              + committee_annual_operation_rows()
                              + sports_information_system_rows()
                              + court_organization_rows(), args.db)
    print(f"ERCE reviewed variable rows upserted: {count}; local DB: {args.db}")


if __name__ == "__main__":
    main()
