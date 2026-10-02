"""Project a changed veterans' allowance from selected historical evidence IDs.

No target-year recipient counts or payouts are read from another bill's answer.
This is a retrospective reusable adapter, not an automatic evidence selector.
"""
from __future__ import annotations

from math import isfinite
from typing import Any, Mapping

from backend.erce.engine import ERCEEstimate, estimate_routed_item
from backend.erce.variable_evidence_store import evidence_payload_from_db


REQUIRED_BASELINES = (
    "concurrent_excluded_2023", "existing_recipients_2019",
    "existing_recipients_2023", "existing_monthly_benefit_2020",
    "existing_monthly_benefit_2024", "median_income_2020", "median_income_2024",
)


def estimate_veteran_allowance_delta_from_baselines(
    payload: Mapping[str, Any], *, legal_median_share: float,
) -> tuple[ERCEEstimate, ERCEEstimate]:
    """Return (new concurrent recipients, raise for existing recipients)."""
    if not isfinite(legal_median_share) or not 0 < legal_median_share <= 1:
        raise ValueError("legal_median_share")
    if payload.get("agency") != "국가보훈부" or payload.get("policy_domain") != "참전유공자 예우":
        raise ValueError("veteran allowance source scope")
    start_year = int(payload["start_year"])
    years = int(payload["years"])
    if start_year <= 2024 or not 1 <= years <= 10:
        raise ValueError("forecast years")
    # The shared DB gate checks cutoff, target/self-leakage, route and each
    # cross-bill applicability note before any historical value is used.
    hydrated = evidence_payload_from_db({**payload, "route_key": "transfer_recipient"})
    rows = {**hydrated.get("selected_variable_inputs", {}),
            **hydrated.get("official_inputs", {})}
    missing = [key for key in REQUIRED_BASELINES if key not in rows]
    if missing:
        raise ValueError("missing historical veteran baselines: " + ", ".join(missing))
    values = {key: float(rows[key]["value"]) for key in REQUIRED_BASELINES}
    if any(not isfinite(value) or value <= 0 for value in values.values()):
        raise ValueError("invalid historical veteran baselines")

    count_factor = (values["existing_recipients_2023"] /
                    values["existing_recipients_2019"]) ** (1 / 4)
    median_factor = (values["median_income_2024"] /
                     values["median_income_2020"]) ** (1 / 4)
    existing_pay_factor = (values["existing_monthly_benefit_2024"] /
                           values["existing_monthly_benefit_2020"]) ** (1 / 4)
    calendar_years = range(start_year, start_year + years)
    concurrent_counts = [values["concurrent_excluded_2023"] * count_factor ** (year - 2023)
                         for year in calendar_years]
    existing_counts = [values["existing_recipients_2023"] * count_factor ** (year - 2023)
                       for year in calendar_years]
    proposed_monthly = [values["median_income_2024"] * median_factor ** (year - 2024)
                        * legal_median_share for year in calendar_years]
    existing_monthly = [values["existing_monthly_benefit_2024"]
                        * existing_pay_factor ** (year - 2024) for year in calendar_years]
    refs = "; ".join(sorted({rows[key]["source_ref"] for key in REQUIRED_BASELINES}))
    def input_row(value, unit):
        return {"value": value, "unit": unit, "source_ref": refs,
                "is_assumption": True}
    common = dict(bill_no=payload.get("bill_no"), cutoff_date=payload.get("cutoff_date"),
                  start_year=start_year, years=years,
                  evidence_mode=payload.get("evidence_mode", "holdout"))
    new = estimate_routed_item({**common, "route_key": "transfer_recipient",
        "calculated_inputs": {
            "recipient_count": input_row(concurrent_counts, "person/year"),
            "benefit_per_recipient": input_row(proposed_monthly, "KRW/person/month"),
        }, "explicit_inputs": {"payments_per_year":12}})
    raise_existing = estimate_routed_item({**common, "route_key": "transfer_recipient_delta",
        "calculated_inputs": {
            "recipient_count": input_row(existing_counts, "person/year"),
            "benefit_per_recipient": input_row(proposed_monthly, "KRW/person/month"),
            "existing_benefit_per_recipient": input_row(existing_monthly, "KRW/person/month"),
        }, "explicit_inputs": {"payments_per_year":12}})
    return new, raise_existing
