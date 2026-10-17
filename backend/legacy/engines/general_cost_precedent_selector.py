"""Evidence-gated precedent selection for general cost estimates.

Semantic or lexical similarity may create a shortlist, but it must never be
the reason a historical amount is executed.  This selector follows the same
contract as the committee/organization engine:

* exclude evidence that was unavailable at the target cutoff;
* require the same fiscal nature and cost mechanism;
* require compatible priced scope;
* prefer the same implementing agency and policy domain;
* execute only a coherent historical annual amount;
* abstain when similarly qualified precedents materially disagree.

The target profile is produced from the bill text by AI/HITL.  Historical
amounts and their provenance come only from the sidecar evidence store.  The
selector does not inspect the target bill's official cost estimate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
import statistics
from typing import Any, Iterable, Mapping

from backend.erce_web.general_cost_resolver import FORMULAS
from backend.erce_web.research_service_unit_cost_registry import (
    research_service_formula_inputs,
)


SELECTOR_VERSION = "general-cost-precedent-selector-v2"
DEFAULT_SIDECAR_DIR = Path("backend/generated/general_cost_sidecar_v1")
MIN_EXECUTABLE_SCORE = 0.75

_COMMEMORATIVE = re.compile(r"기념(?:일|행사|식)|국경일|의날")
_COMMITTEE = re.compile(r"위원회|심의회|협의회")
_SYSTEM = re.compile(r"시스템|전산|플랫폼|데이터베이스|소프트웨어")
_SYSTEM_BUILD = re.compile(r"구축|재구축|개발|도입|구입")
_SYSTEM_UPGRADE = re.compile(r"고도화|기능\s*(?:개선|추가)|저장용량\s*확대|시스템\s*정비")
_SYSTEM_OPERATION = re.compile(
    r"운영비|운영\s*관련|유지\s*(?:관리|보수)|이용료|운영"
)
_SYSTEM_OPERATION_STAFF = re.compile(r"운영\s*인력|유지관리\s*인력|기술자|상주\s*인력")
_SURVEY = re.compile(r"실태\s*조사|현황\s*조사|통계\s*조사|조사\s*(?:실시|시행|연구|용역)")
_PLAN = re.compile(r"기본\s*계획|종합\s*계획|지원\s*계획|계획\s*(?:수립|마련)")
_RESEARCH = re.compile(r"연구|용역")
_EDUCATION = re.compile(r"교육|훈련")
_PUBLICITY = re.compile(r"홍보|캠페인|인식개선")
_EVENT = re.compile(r"행사|기념식|박람회|세미나|포럼")
_FACILITY = re.compile(r"조형물|기념관|시설|건립|공사비|건설공사|공사시행")


def _compact(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", str(value or "")).lower()


def _string_tuple(values: Iterable[Any] | None) -> tuple[str, ...]:
    return tuple(str(value).strip() for value in (values or ()) if str(value).strip())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
    return rows


def infer_mechanism(text: str, component: str = "") -> str:
    compact = _compact(text)
    if _COMMEMORATIVE.search(compact):
        return "commemorative_event"
    if _COMMITTEE.search(compact):
        return "committee_operation"
    if _SYSTEM.search(compact):
        is_build = bool(_SYSTEM_BUILD.search(compact))
        is_upgrade = bool(_SYSTEM_UPGRADE.search(compact))
        is_operation = bool(_SYSTEM_OPERATION.search(compact))
        if is_operation and _SYSTEM_OPERATION_STAFF.search(compact):
            return "information_system_operation_staff"
        if is_operation and (is_build or is_upgrade):
            return "information_system_mixed"
        if is_operation:
            return "information_system_operation"
        if is_upgrade:
            return "information_system_upgrade"
        if is_build:
            return "information_system_build"
        return "information_system"
    if _SURVEY.search(compact):
        return "research_survey"
    if _PLAN.search(compact):
        return "research_plan"
    if _RESEARCH.search(compact):
        return "research_service"
    if _EDUCATION.search(compact) or _PUBLICITY.search(compact):
        return "education_publicity"
    return component or "unknown"


def infer_priced_scopes(text: str, mechanism: str) -> tuple[str, ...]:
    compact = _compact(text)
    scopes: set[str] = set()
    if mechanism == "commemorative_event" or _EVENT.search(compact):
        scopes.add("event")
    if _EDUCATION.search(compact):
        scopes.add("education")
    if _PUBLICITY.search(compact):
        scopes.add("publicity")
    if _FACILITY.search(compact):
        scopes.add("facility")
    return tuple(sorted(scopes))


@dataclass(frozen=True)
class GeneralCostTarget:
    bill_no: str
    bill_name: str
    propose_date: str
    cutoff_date: str
    committee: str
    cost_nature: str
    component: str
    item_name: str
    mechanism: str
    estimated_scopes: tuple[str, ...]
    non_estimable_scopes: tuple[str, ...]
    implementing_agencies: tuple[str, ...]
    agency_source_refs: tuple[str, ...]
    policy_domains: tuple[str, ...]
    years: int = 5
    start_year: int | None = None
    first_year_fraction: float = 1.0
    formula_inputs: Mapping[str, Any] = field(default_factory=dict)


def target_from_dict(payload: Mapping[str, Any]) -> GeneralCostTarget:
    item_name = str(payload.get("item_name") or payload.get("bill_name") or "")
    component = str(payload.get("component") or "")
    supplied_mechanism = str(payload.get("mechanism") or "")
    inferred_mechanism = infer_mechanism(item_name, component)
    # Older target profiles used one broad information-system label. Refine
    # those profiles from their item name so build, upgrade and operation
    # precedents are not mixed together.
    mechanism = (
        inferred_mechanism
        if supplied_mechanism in {"", "information_system"}
        and inferred_mechanism.startswith("information_system_")
        else (
            inferred_mechanism
            if supplied_mechanism == "research_survey"
            and inferred_mechanism == "research_plan"
            else supplied_mechanism or inferred_mechanism
        )
    )
    scopes = _string_tuple(payload.get("estimated_scopes"))
    if "estimated_scopes" not in payload:
        scopes = infer_priced_scopes(item_name, mechanism)
    propose_date = str(payload.get("propose_date") or "")
    return GeneralCostTarget(
        bill_no=str(payload.get("bill_no") or ""),
        bill_name=str(payload.get("bill_name") or ""),
        propose_date=propose_date,
        cutoff_date=str(payload.get("cutoff_date") or propose_date),
        committee=str(payload.get("committee") or ""),
        cost_nature=str(payload.get("cost_nature") or ""),
        component=component,
        item_name=item_name,
        mechanism=mechanism,
        estimated_scopes=scopes,
        non_estimable_scopes=_string_tuple(payload.get("non_estimable_scopes")),
        implementing_agencies=_string_tuple(payload.get("implementing_agencies")),
        agency_source_refs=_string_tuple(payload.get("agency_source_refs")),
        policy_domains=_string_tuple(payload.get("policy_domains")),
        years=int(payload.get("years") or 5),
        start_year=(int(payload["start_year"]) if payload.get("start_year") is not None else None),
        first_year_fraction=float(payload.get("first_year_fraction", 1.0)),
        formula_inputs=dict(payload.get("formula_inputs") or {}),
    )


@dataclass(frozen=True)
class CandidateAudit:
    profile_key: str
    bill_no: str
    bill_name: str
    item_name: str
    propose_date: str
    available_date: str
    committee: str
    mechanism: str
    priced_scopes: tuple[str, ...]
    annual_amount_won: int | None
    amount_evidence_count: int
    amount_spread_ratio: float | None
    amount_source_text: str
    agency_match: str
    matched_agencies: tuple[str, ...]
    matched_policy_domains: tuple[str, ...]
    item_similarity: float
    score: float
    eligible: bool
    blockers: tuple[str, ...]
    reasons: tuple[str, ...]
    review_status: str
    formula_family: str
    formula_readiness: str
    missing_formula_variables: tuple[str, ...]


@dataclass(frozen=True)
class PrecedentSelection:
    selector_version: str
    target_bill_no: str
    decision: str
    selected: CandidateAudit | None
    candidates: tuple[CandidateAudit, ...]
    formula_key: str
    formula_source: str
    resolver_request: dict[str, Any] | None
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GeneralCostEvidenceStore:
    def __init__(self, sidecar_dir: Path = DEFAULT_SIDECAR_DIR) -> None:
        self.sidecar_dir = Path(sidecar_dir)
        self.profiles = _read_jsonl(self.sidecar_dir / "item_profiles.jsonl")
        self.profiles_by_key = {
            str(row.get("profile_key") or ""): row for row in self.profiles
        }
        self.evidence_by_profile: dict[str, list[dict[str, Any]]] = {}
        self.observations_by_profile: dict[str, list[dict[str, Any]]] = {}
        for row in _read_jsonl(self.sidecar_dir / "variable_evidence.jsonl"):
            self.evidence_by_profile.setdefault(str(row.get("profile_key") or ""), []).append(row)
        for row in _read_jsonl(self.sidecar_dir / "amount_observations.jsonl"):
            self.observations_by_profile.setdefault(str(row.get("profile_key") or ""), []).append(row)


def _historical_amount(
    profile_key: str,
    store: GeneralCostEvidenceStore,
) -> tuple[int | None, int, float | None, str]:
    observations = store.observations_by_profile.get(profile_key, [])
    values = [
        int(row["amount_thousand"]) * 1_000
        for row in observations
        if not row.get("is_total")
        and isinstance(row.get("amount_thousand"), (int, float))
        and float(row["amount_thousand"]) > 0
    ]
    evidence = store.evidence_by_profile.get(profile_key, [])
    if not values:
        annual_rows = [
            row for row in evidence
            if str(row.get("canonical_key") or "").startswith("annual_")
            and isinstance(row.get("normalized_value"), (int, float))
            and float(row["normalized_value"]) > 0
        ]
        values = [int(round(float(row["normalized_value"]))) for row in annual_rows]
    if not values:
        return None, 0, None, ""
    median = int(round(statistics.median(values)))
    spread = (max(values) - min(values)) / max(median, 1)
    source_rows = [
        row for row in evidence
        if isinstance(row.get("normalized_value"), (int, float))
        and abs(float(row["normalized_value"]) - median) / max(median, 1) <= 0.05
    ]
    source_text = str(source_rows[0].get("source_text") or "") if source_rows else ""
    return median, len(values), round(spread, 6), source_text


def _candidate_text(profile: Mapping[str, Any], evidence: Iterable[Mapping[str, Any]]) -> str:
    return " ".join(
        [
            str(profile.get("bill_name") or ""),
            str(profile.get("item_name") or ""),
            str(profile.get("trigger_ref") or ""),
            *(str(row.get("source_text") or "") for row in evidence),
        ]
    )


def _matches(values: Iterable[str], text: str) -> tuple[str, ...]:
    compact = _compact(text)
    return tuple(sorted({value for value in values if _compact(value) in compact}))


def _char_ngrams(value: str, size: int = 2) -> set[str]:
    compact = _compact(value)
    if len(compact) <= size:
        return {compact} if compact else set()
    return {compact[index:index + size] for index in range(len(compact) - size + 1)}


def item_similarity(left: str, right: str) -> float:
    left_compact = _compact(left)
    right_compact = _compact(right)
    if not left_compact or not right_compact:
        return 0.0
    if left_compact == right_compact:
        return 1.0
    left_grams = _char_ngrams(left_compact)
    right_grams = _char_ngrams(right_compact)
    union = left_grams | right_grams
    return len(left_grams & right_grams) / len(union) if union else 0.0


def _audit_candidate(
    target: GeneralCostTarget,
    profile: Mapping[str, Any],
    store: GeneralCostEvidenceStore,
) -> CandidateAudit:
    profile_key = str(profile.get("profile_key") or "")
    evidence = store.evidence_by_profile.get(profile_key, [])
    text = _candidate_text(profile, evidence)
    # Mechanism identity is item-level.  A bill may contain several unrelated
    # fiscal items, so its title must not turn every row into (for example) a
    # commemorative-event candidate merely because the bill is a memorial act.
    item_text = f"{profile.get('item_name', '')} {profile.get('trigger_ref', '')}"
    mechanism = infer_mechanism(item_text, str(profile.get("component") or ""))
    scopes = infer_priced_scopes(str(profile.get("item_name") or ""), mechanism)
    amount, evidence_count, spread, source_text = _historical_amount(profile_key, store)
    matched_agencies = _matches(target.implementing_agencies, text)
    matched_domains = _matches(target.policy_domains, text)
    name_similarity = item_similarity(
        target.item_name,
        str(profile.get("item_name") or ""),
    )
    agency_match = (
        "not_required"
        if not target.implementing_agencies
        else ("exact" if matched_agencies else "unknown")
    )

    blockers: list[str] = []
    reasons: list[str] = []
    bill_no = str(profile.get("bill_no") or "")
    available_date = str(profile.get("available_date") or "")
    if bill_no == target.bill_no:
        blockers.append("TARGET_BILL_EXCLUDED")
    if not available_date:
        blockers.append("OFFICIAL_AVAILABLE_DATE_MISSING")
    elif target.cutoff_date and available_date > target.cutoff_date:
        blockers.append("AVAILABLE_AFTER_TARGET_CUTOFF")
    if str(profile.get("cost_nature") or "") != target.cost_nature:
        blockers.append("COST_NATURE_MISMATCH")
    if mechanism != target.mechanism:
        blockers.append("COST_MECHANISM_MISMATCH")

    required_scopes = set(target.estimated_scopes)
    candidate_scopes = set(scopes)
    missing_scopes = required_scopes - candidate_scopes
    extra_scopes = candidate_scopes - required_scopes
    if missing_scopes:
        blockers.append("PRICED_SCOPE_MISSING:" + ",".join(sorted(missing_scopes)))
    if extra_scopes:
        blockers.append("PRICED_SCOPE_EXTRA:" + ",".join(sorted(extra_scopes)))
    if amount is None:
        blockers.append("ANNUAL_AMOUNT_MISSING")
    elif spread is not None and spread > 0.20:
        blockers.append("ANNUAL_AMOUNT_INCOHERENT")

    if mechanism == target.mechanism:
        reasons.append("same_cost_mechanism")
    if required_scopes == candidate_scopes:
        reasons.append("same_priced_scope")
    if agency_match == "exact":
        reasons.append("same_implementing_agency")
    if matched_domains:
        reasons.append("same_policy_domain")
    if target.committee and str(profile.get("committee") or "") == target.committee:
        reasons.append("same_committee")
    if amount is not None and (spread is None or spread <= 0.20):
        reasons.append("coherent_historical_amount")

    score = 0.0
    score += 0.30 if mechanism == target.mechanism else 0.0
    score += 0.15 if required_scopes == candidate_scopes else 0.0
    score += 0.15 * name_similarity
    if agency_match == "exact":
        score += 0.20
    elif agency_match == "unknown":
        score += 0.03
    if target.policy_domains:
        score += 0.10 * len(matched_domains) / len(set(target.policy_domains))
    if target.committee and str(profile.get("committee") or "") == target.committee:
        score += 0.05
    if amount is not None and (spread is None or spread <= 0.20):
        score += 0.05

    return CandidateAudit(
        profile_key=profile_key,
        bill_no=bill_no,
        bill_name=str(profile.get("bill_name") or ""),
        item_name=str(profile.get("item_name") or ""),
        propose_date=str(profile.get("propose_date") or ""),
        available_date=available_date,
        committee=str(profile.get("committee") or ""),
        mechanism=mechanism,
        priced_scopes=scopes,
        annual_amount_won=amount,
        amount_evidence_count=evidence_count,
        amount_spread_ratio=spread,
        amount_source_text=source_text,
        agency_match=agency_match,
        matched_agencies=matched_agencies,
        matched_policy_domains=matched_domains,
        item_similarity=round(name_similarity, 6),
        score=round(score, 6),
        eligible=not blockers,
        blockers=tuple(blockers),
        reasons=tuple(reasons),
        review_status=str(profile.get("review_status") or "candidate"),
        formula_family=str(profile.get("formula_family") or ""),
        formula_readiness=str(profile.get("formula_readiness") or "unresolved"),
        missing_formula_variables=tuple(
            str(value) for value in profile.get("missing_formula_variables") or ()
        ),
    )


def _materially_disagree(left: CandidateAudit, right: CandidateAudit) -> bool:
    if left.annual_amount_won is None or right.annual_amount_won is None:
        return False
    smaller = min(left.annual_amount_won, right.annual_amount_won)
    larger = max(left.annual_amount_won, right.annual_amount_won)
    return bool(smaller > 0 and larger / smaller > 1.20)


def select_formula_key(
    target: GeneralCostTarget,
    selected: CandidateAudit | None = None,
    *,
    store: GeneralCostEvidenceStore | None = None,
) -> tuple[str, str]:
    """Choose a versioned formula; never choose a monetary value here."""
    available: set[str] = set()
    if selected and store:
        available = {
            str(row.get("canonical_key") or "")
            for row in store.evidence_by_profile.get(selected.profile_key, [])
            if row.get("normalized_value") is not None
            and str(row.get("unit_status") or "") == "normalized"
            and str(row.get("transfer_policy") or "")
            not in {"target_specific", "do_not_transfer"}
        }
    available.update(str(key) for key in target.formula_inputs)

    if (
        target.cost_nature == "goods_services"
        and target.mechanism == "information_system_operation"
        and {"operation_headcount", "annual_labor_cost_per_person"} <= available
        and "annual_operating_amount" not in available
    ):
        return "INFORMATION_SYSTEM_OPERATION_STAFF_V1", "available_operand_subroute"
    if (
        target.cost_nature == "goods_services"
        and target.mechanism == "information_system_operation_staff"
    ):
        return "INFORMATION_SYSTEM_OPERATION_STAFF_V1", "fixed_mechanism_route"
    if (
        target.cost_nature == "goods_services"
        and target.mechanism == "information_system_operation"
    ):
        return "INFORMATION_SYSTEM_OPERATION_V1", "fixed_mechanism_route"
    if target.cost_nature == "goods_services" and target.mechanism == "research_plan":
        return "PERIODIC_RESEARCH_PLAN_V1", "fixed_mechanism_route"
    if target.cost_nature == "goods_services" and target.mechanism == "research_survey":
        return "ANNUAL_RESEARCH_SURVEY_V1", "fixed_mechanism_route"

    if (
        selected
        and selected.formula_family == "DIRECT_ANNUAL_AMOUNT_V1"
        and selected.formula_readiness == "ready"
    ):
        return selected.formula_family, "selected_precedent_profile"
    if selected and selected.formula_family in FORMULAS:
        required = set(FORMULAS[selected.formula_family]["required"])
        if required <= available:
            return selected.formula_family, "selected_precedent_profile"

    if target.cost_nature == "personnel":
        if target.component == "employer_contribution":
            return "PERSONNEL_EMPLOYER_CONTRIBUTION_V1", "component_rule"
        if target.component == "basic_expense":
            return "PERSONNEL_BASIC_EXPENSE_V1", "component_rule"
        if target.component == "asset":
            return "PERSONNEL_ASSET_V1", "component_rule"
        if {"headcount_by_grade", "salary_by_grade"} <= available:
            return "PERSONNEL_GRADE_V1", "available_operand_rule"
        return "PERSONNEL_AVERAGE_V1", "component_rule"
    if target.cost_nature == "goods_services":
        if target.mechanism == "committee_operation":
            return "COMMITTEE_MEETING_ALLOWANCE_V1", "fixed_mechanism_route"
        if target.mechanism == "commemorative_event" or {"quantity", "unit_cost"} <= available:
            return "COMMON_QUANTITY_UNIT_V1", "mechanism_rule"
        return "GOODS_SERVICE_ACTIVITY_V1", "cost_nature_rule"
    if target.cost_nature == "transfers":
        if {"project_cost", "subsidy_rate"} <= available:
            return "TRANSFER_SUBSIDY_RATE_V1", "available_operand_rule"
        return "TRANSFER_RECIPIENT_V1", "cost_nature_rule"
    if target.cost_nature == "capital":
        if target.component == "equipment_asset":
            return "CAPITAL_ASSET_V1", "component_rule"
        if target.component in {"construction", "design_supervision", "land_acquisition"}:
            return "CAPITAL_AREA_V1", "component_rule"
        return "COMMON_QUANTITY_UNIT_V1", "cost_nature_rule"
    if target.cost_nature == "tax_expenditure":
        if target.component == "tax_credit_deduction" or "deduction_change" in available:
            return "TAX_DEDUCTION_CHANGE_V1", "component_rule"
        return "TAX_RATE_CHANGE_V1", "cost_nature_rule"
    if target.cost_nature == "non_tax_revenue_loss":
        return "NON_TAX_FEE_CHANGE_V1", "cost_nature_rule"
    if target.cost_nature == "equity_contribution":
        if {"institution_count", "contribution_per_institution"} <= available:
            return "EQUITY_INSTITUTION_UNIT_V1", "available_operand_rule"
        return "EQUITY_PROJECT_SHARE_V1", "cost_nature_rule"
    return "", "unsupported_cost_nature"


def _target_input(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {
            "value": value.get("value"),
            "unit": str(value.get("unit") or ""),
            "source": str(value.get("source") or "target_document"),
            "source_ref": str(value.get("source_ref") or ""),
            "evidence_keys": list(value.get("evidence_keys") or ()),
        }
    return {
        "value": value,
        "unit": "",
        "source": "target_document",
        "source_ref": "",
        "evidence_keys": [],
    }


def _precedent_inputs(
    selected: CandidateAudit,
    store: GeneralCostEvidenceStore,
) -> dict[str, dict[str, Any]]:
    """Load operands from one precedent profile using org-engine transfer rules."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in store.evidence_by_profile.get(selected.profile_key, []):
        key = str(row.get("canonical_key") or "")
        value = row.get("normalized_value")
        if not key or not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        if str(row.get("unit_status") or "") != "normalized":
            continue
        if str(row.get("transfer_policy") or "") in {"target_specific", "do_not_transfer"}:
            continue
        grouped.setdefault(key, []).append(row)

    inputs: dict[str, dict[str, Any]] = {}
    for key, rows in grouped.items():
        units = {str(row.get("normalized_unit") or "") for row in rows}
        values = {float(row["normalized_value"]) for row in rows}
        if len(units) != 1 or "" in units or len(values) != 1:
            continue
        inputs[key] = {
            "value": next(iter(values)),
            "unit": next(iter(units)),
            "source": "sidecar_candidate_diagnostic",
            "source_ref": (
                f"{selected.bill_no} {selected.item_name}: "
                f"{str(rows[0].get('source_text') or '')}"
            ).strip(),
            "evidence_keys": [str(row.get("evidence_key") or "") for row in rows],
        }
    return inputs


def _resolver_request(
    target: GeneralCostTarget,
    selected: CandidateAudit,
    store: GeneralCostEvidenceStore,
    formula_key: str,
) -> dict[str, Any]:
    inputs = _precedent_inputs(selected, store)
    if target.mechanism in {"research_plan", "research_survey"}:
        for agency in target.implementing_agencies:
            try:
                inputs.update(research_service_formula_inputs(
                    target.mechanism,
                    agency,
                    as_of_date=target.cutoff_date,
                ))
                break
            except KeyError:
                continue
    # Target-law/user-confirmed values always override historical operands.
    inputs.update({key: _target_input(value) for key, value in target.formula_inputs.items()})

    if formula_key == "DIRECT_ANNUAL_AMOUNT_V1":
        inputs["annual_amount"] = {
            "value": selected.annual_amount_won,
            "unit": "KRW/year",
            "source": "evidence_gated_precedent",
            "source_ref": (
                f"{selected.bill_no} {selected.item_name}: "
                f"{selected.amount_source_text}"
            ).strip(),
            "evidence_keys": [],
        }
    if formula_key == "INFORMATION_SYSTEM_OPERATION_V1":
        inputs.setdefault(
            "annual_operating_amount",
            {
                "value": selected.annual_amount_won,
                "unit": "KRW/year",
                "source": "evidence_gated_precedent",
                "source_ref": (
                    f"{selected.bill_no} {selected.item_name}: "
                    f"{selected.amount_source_text}"
                ).strip(),
                "evidence_keys": [],
            },
        )
    if formula_key == "COMMON_QUANTITY_UNIT_V1" and target.mechanism == "commemorative_event":
        inputs.setdefault(
            "quantity",
            {
                "value": 1,
                "unit": "event/year",
                "source": "formula_rule",
                "source_ref": "기념일 행사 연 1회 개최",
                "evidence_keys": [],
            },
        )
        inputs.setdefault(
            "unit_cost",
            {
                "value": selected.annual_amount_won,
                "unit": "KRW/event",
                "source": "evidence_gated_precedent",
                "source_ref": f"{selected.bill_no} 유사 기념행사 연액",
                "evidence_keys": [],
            },
        )
    inputs["first_year_fraction"] = {
        "value": target.first_year_fraction,
        "unit": "ratio",
        "source": "target_effective_date_review",
        "source_ref": "대상 법안 시행시점에서 별도 산정",
        "evidence_keys": [],
    }
    return {
        "cost_nature": target.cost_nature,
        "component": target.component,
        "formula_key": formula_key,
        "target_bill_no": target.bill_no,
        "years": target.years,
        "start_year": target.start_year,
        "inputs": inputs,
    }


def _research_benchmark_request(
    target: GeneralCostTarget,
    formula_key: str,
) -> dict[str, Any] | None:
    if target.mechanism not in {"research_plan", "research_survey"}:
        return None
    inputs: dict[str, dict[str, Any]] | None = None
    for agency in target.implementing_agencies:
        try:
            inputs = research_service_formula_inputs(
                target.mechanism,
                agency,
                as_of_date=target.cutoff_date,
            )
            break
        except KeyError:
            continue
    if inputs is None:
        return None
    inputs.update({key: _target_input(value) for key, value in target.formula_inputs.items()})
    inputs["first_year_fraction"] = {
        "value": target.first_year_fraction,
        "unit": "ratio",
        "source": "target_effective_date_review",
        "source_ref": "대상 법안 시행시점에서 별도 산정",
        "evidence_keys": [],
    }
    return {
        "cost_nature": target.cost_nature,
        "component": target.component,
        "formula_key": formula_key,
        "target_bill_no": target.bill_no,
        "years": target.years,
        "start_year": target.start_year,
        "inputs": inputs,
    }


def select_precedent(
    target: GeneralCostTarget,
    *,
    store: GeneralCostEvidenceStore | None = None,
    top_k: int = 10,
) -> PrecedentSelection:
    store = store or GeneralCostEvidenceStore()
    audits = [
        _audit_candidate(target, profile, store)
        for profile in store.profiles
        if str(profile.get("cost_nature") or "") == target.cost_nature
    ]
    ranked = sorted(
        audits,
        key=lambda row: (
            1 if row.eligible else 0,
            1 if row.agency_match == "exact" else 0,
            row.score,
            row.available_date,
            row.profile_key,
        ),
        reverse=True,
    )
    eligible = [row for row in ranked if row.eligible]
    warnings: list[str] = []
    fallback_formula_key, fallback_formula_source = select_formula_key(
        target, store=store
    )
    benchmark_request = _research_benchmark_request(target, fallback_formula_key)
    if benchmark_request is not None:
        return PrecedentSelection(
            selector_version=SELECTOR_VERSION,
            target_bill_no=target.bill_no,
            decision="official_benchmark",
            selected=None,
            candidates=tuple(ranked[:top_k]),
            formula_key=fallback_formula_key,
            formula_source="official_benchmark_registry",
            resolver_request=benchmark_request,
            warnings=(),
        )

    if target.implementing_agencies:
        if not eligible:
            return PrecedentSelection(
                selector_version=SELECTOR_VERSION,
                target_bill_no=target.bill_no,
                decision="abstain",
                selected=None,
                candidates=tuple(ranked[:top_k]),
                formula_key=fallback_formula_key,
                formula_source=fallback_formula_source,
                resolver_request=None,
                warnings=("No precedent passed every evidence gate.",),
            )
        executable = [
            row for row in eligible
            if row.agency_match == "exact" and row.score >= MIN_EXECUTABLE_SCORE
        ]
        if not executable:
            review_selected = eligible[0] if eligible else None
            formula_key, formula_source = select_formula_key(
                target, review_selected, store=store
            )
            return PrecedentSelection(
                selector_version=SELECTOR_VERSION,
                target_bill_no=target.bill_no,
                decision="needs_review",
                selected=review_selected,
                candidates=tuple(ranked[:top_k]),
                formula_key=formula_key,
                formula_source=formula_source,
                resolver_request=None,
                warnings=(
                    "No complete precedent passes both the agency gate and minimum score.",
                ),
            )
    else:
        executable = [row for row in eligible if row.score >= MIN_EXECUTABLE_SCORE]
        if not executable and eligible:
            formula_key, formula_source = select_formula_key(
                target, eligible[0], store=store
            )
            return PrecedentSelection(
                selector_version=SELECTOR_VERSION,
                target_bill_no=target.bill_no,
                decision="needs_review",
                selected=eligible[0],
                candidates=tuple(ranked[:top_k]),
                formula_key=formula_key,
                formula_source=formula_source,
                resolver_request=None,
                warnings=("Compatible precedents exist, but none meets the execution threshold.",),
            )

    if not executable:
        return PrecedentSelection(
            selector_version=SELECTOR_VERSION,
            target_bill_no=target.bill_no,
            decision="abstain",
            selected=None,
            candidates=tuple(ranked[:top_k]),
            formula_key=fallback_formula_key,
            formula_source=fallback_formula_source,
            resolver_request=None,
            warnings=("No precedent passed every evidence gate.",),
        )

    selected = executable[0]
    for challenger in executable[1:]:
        if selected.score - challenger.score > 0.08:
            break
        if _materially_disagree(selected, challenger):
            formula_key, formula_source = select_formula_key(
                target, selected, store=store
            )
            return PrecedentSelection(
                selector_version=SELECTOR_VERSION,
                target_bill_no=target.bill_no,
                decision="needs_review",
                selected=selected,
                candidates=tuple(ranked[:top_k]),
                formula_key=formula_key,
                formula_source=formula_source,
                resolver_request=None,
                warnings=("Similarly qualified precedents disagree by more than 20%.",),
            )

    if selected.review_status != "verified":
        warnings.append("Selected sidecar evidence remains candidate and requires reviewer confirmation.")
    formula_key, formula_source = select_formula_key(target, selected, store=store)
    return PrecedentSelection(
        selector_version=SELECTOR_VERSION,
        target_bill_no=target.bill_no,
        decision="exact_precedent_candidate",
        selected=selected,
        candidates=tuple(ranked[:top_k]),
        formula_key=formula_key,
        formula_source=formula_source,
        resolver_request=_resolver_request(target, selected, store, formula_key),
        warnings=tuple(warnings),
    )


__all__ = [
    "CandidateAudit",
    "GeneralCostEvidenceStore",
    "GeneralCostTarget",
    "PrecedentSelection",
    "infer_mechanism",
    "infer_priced_scopes",
    "item_similarity",
    "select_formula_key",
    "select_precedent",
    "target_from_dict",
]
