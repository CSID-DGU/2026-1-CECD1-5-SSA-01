"""Versioned ERCE assumption and unit-cost registries.

Counts and frequencies are comparable-case assumptions.  Unit rates are kept
separately so a later official rate can be updated without changing a formula.
Every row is cutoff-aware to prevent future evidence from entering a backtest.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MeetingUnitRate:
    key: str
    won_per_person_meeting: int
    available_at: str
    source: str
    source_ref: str


@dataclass(frozen=True)
class CommitteeAssumptionPack:
    key: str
    agency: str
    subtype: str
    paid_members: int
    annual_meetings: int
    committee_instances: int
    unit_rate_key: str
    available_at: str
    source_bill_no: str
    source_item: str
    source_ref: str
    growth_series_key: str | None = None
    growth_application_start_year: int | None = None
    policy_domain: str = ""


MEETING_UNIT_RATES: dict[str, MeetingUnitRate] = {
    "meeting_allowance_200k_2026": MeetingUnitRate(
        key="meeting_allowance_200k_2026",
        won_per_person_meeting=200_000,
        available_at="2026-05-13",
        source="2026년도 예산 및 기금운용계획 집행지침 인용 근거",
        source_ref=("의안 2218618, 26B2346, p.3 각주 2; 집행지침 2026.1 p.150 "
                    "참석비 1일 20만원 이내, 2시간 이상 10만원 이내 추가. "
                    "본 비교사례는 회당 20만원, 기간 중 동결 가정. "
                    "원 지침 발표일과 별도로 로컬 근거 확인 가능일을 회답일로 제한"),
    ),
    "meeting_allowance_250k_2023": MeetingUnitRate(
        key="meeting_allowance_250k_2023",
        won_per_person_meeting=250_000,
        available_at="2023-10-13",
        source="국회예산정책처 비용추계 선례",
        source_ref="의안 2124586; 최저임금위원회 회의수당 회당 25만원",
    ),
    "meeting_allowance_230k_2023": MeetingUnitRate(
        key="meeting_allowance_230k_2023",
        won_per_person_meeting=230_000,
        available_at="2023-10-13",
        source="국회예산정책처 비용추계 선례",
        source_ref="의안 2124586; 최저임금위원회 연구위원회 회의수당 회당 23만원",
    ),
    "meeting_allowance_250k_2025": MeetingUnitRate(
        key="meeting_allowance_250k_2025",
        won_per_person_meeting=250_000,
        available_at="2025-02-10",
        source="기획재정부 예산 및 기금운용계획 집행지침 준용",
        source_ref="의안 2205576 비용추계서; 민간위원 회의수당 회당 25만원",
    ),
}


COMMITTEE_ASSUMPTION_PACKS: tuple[CommitteeAssumptionPack, ...] = (
    CommitteeAssumptionPack(
        key="circular_economy_regulatory_committee_2026",
        agency="기후에너지환경부",
        subtype="regulatory_special_zone",
        paid_members=12,
        annual_meetings=4,
        committee_instances=1,
        unit_rate_key="meeting_allowance_200k_2026",
        available_at="2026-05-13",
        source_bill_no="2218618",
        source_item="순환경제규제특구위원회",
        source_ref=("의안 2218618 비용추계서 p.2~5; 순환경제 신기술·서비스 "
                    "심의위원회 위촉직 12명, 2026년 분기 1회 개최계획 준용. "
                    "새 위원회 정원·횟수는 선례 가정"),
        policy_domain="순환경제",
    ),
    CommitteeAssumptionPack(
        key="public_wage_committee_main_2023",
        agency="기획재정부",
        subtype="main_committee",
        paid_members=24,
        annual_meetings=15,
        committee_instances=1,
        unit_rate_key="meeting_allowance_250k_2023",
        available_at="2023-10-13",
        source_bill_no="2124586",
        source_item="공공기관 임금·근로조건 결정위원회",
        source_ref="최저임금위원회를 준용한 21대 동일 법률안 선례",
    ),
    CommitteeAssumptionPack(
        key="public_wage_committee_advisory_2023",
        agency="기획재정부",
        subtype="advisory_body",
        paid_members=5,
        annual_meetings=7,
        committee_instances=1,
        unit_rate_key="meeting_allowance_230k_2023",
        available_at="2023-10-13",
        source_bill_no="2124586",
        source_item="공공기관 임금·근로조건 자문기구",
        source_ref="최저임금위원회 실무자협의회를 준용한 21대 동일 법률안 선례",
    ),
    CommitteeAssumptionPack(
        key="public_wage_committee_main_2025",
        agency="기획재정부",
        subtype="main_committee",
        paid_members=27,
        annual_meetings=11,
        committee_instances=1,
        unit_rate_key="meeting_allowance_250k_2025",
        available_at="2025-02-10",
        source_bill_no="2205576",
        source_item="공공기관 임금·근로조건 결정위원회",
        source_ref="2024년 최저임금위원회 구성·개최실적 준용",
        growth_series_key="nabo_macro_2024_10_consumer_price",
        growth_application_start_year=2027,
    ),
    CommitteeAssumptionPack(
        key="public_wage_committee_advisory_2025",
        agency="기획재정부",
        subtype="advisory_body",
        paid_members=7,
        annual_meetings=3,
        committee_instances=2,
        unit_rate_key="meeting_allowance_250k_2025",
        available_at="2025-02-10",
        source_bill_no="2205576",
        source_item="공공기관 임금·근로조건 조사·자문기구",
        source_ref="최저임금위원회 연구위원회 준용; 조사·자문기구 각 1개 가정",
        growth_series_key="nabo_macro_2024_10_consumer_price",
        growth_application_start_year=2027,
    ),
)


def select_committee_pack(
    *,
    agency: str,
    subtype: str,
    as_of_date: str,
    policy_domain: str = "",
    target_bill_no: str = "",
) -> tuple[CommitteeAssumptionPack, MeetingUnitRate]:
    cutoff = date.fromisoformat(as_of_date)
    rows = [
        row for row in COMMITTEE_ASSUMPTION_PACKS
        if row.agency == agency
        and row.subtype == subtype
        and (not row.policy_domain or row.policy_domain == policy_domain)
        and (not target_bill_no or row.source_bill_no != target_bill_no)
        and date.fromisoformat(row.available_at) <= cutoff
    ]
    if not rows:
        raise KeyError(f"no committee evidence pack for {agency}/{subtype} at {as_of_date}")
    pack = max(rows, key=lambda row: row.available_at)
    rate = MEETING_UNIT_RATES[pack.unit_rate_key]
    if date.fromisoformat(rate.available_at) > cutoff:
        raise KeyError(f"unit rate {rate.key} was unavailable at {as_of_date}")
    return pack, rate


__all__ = [
    "COMMITTEE_ASSUMPTION_PACKS",
    "MEETING_UNIT_RATES",
    "CommitteeAssumptionPack",
    "MeetingUnitRate",
    "select_committee_pack",
]
