"""Two explicit population methods for infertility-treatment leave grants."""
from math import isfinite
from collections.abc import Mapping


def _number(value, name, *, ratio=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(name)
    value = float(value)
    if not isfinite(value) or value < 0 or (ratio and value > 1):
        raise ValueError(name)
    return value


def infertility_leave_recipients(basis, start_year, years, *, method):
    if not isinstance(basis, Mapping):
        raise ValueError("infertility_population_basis")
    if start_year is None:
        raise ValueError("start_year")
    def num(key, ratio=False):
        return _number(basis.get(key), key, ratio=ratio)
    base_year = num("base_year")
    if (isinstance(start_year, bool) or not isinstance(start_year, int)
            or not 1900 <= start_year <= 2200 or not 1900 <= base_year <= 2200
            or not base_year.is_integer() or start_year < base_year):
        raise ValueError("base_year")
    share = num("priority_company_share", True)
    growth = num("priority_share_growth_rate", True)
    result = []
    for year in range(start_year, start_year + years):
        offset = year - int(base_year)
        priority = share * (1 + growth) ** offset
        if not isfinite(priority) or priority > 1:
            raise ValueError("priority_company_share")
        if method == "civil_proxy":
            cohorts = basis.get("insured_cohorts")
            if not isinstance(cohorts, list) or not cohorts:
                raise ValueError("insured_cohorts")
            population = 0.0
            for cohort in cohorts:
                if not isinstance(cohort, Mapping):
                    raise ValueError("insured_cohorts")
                insured = _number(cohort.get("insured_population"), "insured_population")
                rate = _number(cohort.get("insured_growth_rate"), "insured_growth_rate", ratio=True)
                users = _number(cohort.get("civil_leave_users"), "civil_leave_users")
                staff = _number(cohort.get("civil_staff"), "civil_staff")
                if staff <= 0 or users > staff:
                    raise ValueError("civil_leave_users/civil_staff")
                population += insured * (1 + rate) ** offset * users / staff
            recipients = population * priority
        elif method == "budget_proxy":
            patients = basis.get("historical_infertility_patients")
            if not isinstance(patients, list) or not patients:
                raise ValueError("historical_infertility_patients")
            average = sum(_number(v, "historical_infertility_patients") for v in patients) / len(patients)
            recipients = (average * num("employee_share", True)
                          * num("insurance_enrollment_share", True)
                          * priority * num("leave_uptake_rate", True))
        else:
            raise ValueError("infertility_population_method")
        if not isfinite(recipients):
            raise ValueError("infertility_population_basis")
        result.append(recipients)
    return result
