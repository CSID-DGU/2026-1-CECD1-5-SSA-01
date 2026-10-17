from __future__ import annotations

from dataclasses import dataclass


YEARS = ["1차년도", "2차년도", "3차년도", "4차년도", "5차년도"]


@dataclass(frozen=True)
class CostRule:
    id: str
    keywords: tuple[str, ...]
    category: str
    item: str
    unit_cost_thousand_krw: int
    quantity: int
    unit_label: str
    quantity_label: str
    occurrence: str
    evidence_source: str
    evidence_detail: str
    legal_hint: str


COST_RULES: tuple[CostRule, ...] = (
    CostRule(
        id="shared_electricity",
        keywords=("전기요금", "공용시설", "관리비"),
        category="운영비",
        item="공용시설 전기요금 지원",
        unit_cost_thousand_krw=24_000,
        quantity=50,
        unit_label="연 24,000천원/단지",
        quantity_label="지원대상 50개 단지",
        occurrence="annual",
        evidence_source="프로토타입 단가표 - 공공임대주택 공용 전기요금 가정(2026)",
        evidence_detail="단지별 공용부 전기요금 연 24,000천원 기준을 적용한 시범사업 추계",
        legal_hint="제6조 제1항 제1호",
    ),
    CostRule(
        id="shared_water",
        keywords=("수도요금", "하수도", "공공요금", "관리비"),
        category="운영비",
        item="공용부분 수도·하수도 요금 지원",
        unit_cost_thousand_krw=12_000,
        quantity=50,
        unit_label="연 12,000천원/단지",
        quantity_label="지원대상 50개 단지",
        occurrence="annual",
        evidence_source="프로토타입 단가표 - 공공임대주택 공공요금 가정(2026)",
        evidence_detail="단지별 수도·하수도 공공요금 연 12,000천원 기준 적용",
        legal_hint="제6조 제1항 제2호",
    ),
    CostRule(
        id="energy_diagnosis",
        keywords=("에너지", "효율화", "기술자문"),
        category="사업비",
        item="에너지 이용 효율화 기술진단",
        unit_cost_thousand_krw=5_000,
        quantity=20,
        unit_label="5,000천원/단지",
        quantity_label="우선개선 20개 단지",
        occurrence="year1_only",
        evidence_source="프로토타입 단가표 - 공동주택 기술진단 가정(2026)",
        evidence_detail="사업 착수 1차년도에 20개 단지 기술진단을 실시하는 가정",
        legal_hint="제7조 제2항",
    ),
    CostRule(
        id="led_retrofit",
        keywords=("조명기기", "단열", "창호", "에너지"),
        category="사업비",
        item="고효율 조명·단열 개선 지원",
        unit_cost_thousand_krw=35_000,
        quantity=20,
        unit_label="35,000천원/단지",
        quantity_label="개선사업 20개 단지",
        occurrence="year1_only",
        evidence_source="프로토타입 단가표 - 공동주택 에너지 절감 개선 가정(2026)",
        evidence_detail="LED 조명 교체와 공용부 단열 개선 비용을 합산한 단지별 평균 단가",
        legal_hint="제7조 제1항 제1호",
    ),
    CostRule(
        id="smart_metering",
        keywords=("지능형", "모니터링", "스마트", "전력계량기"),
        category="사업비",
        item="실시간 에너지 모니터링 시스템 구축",
        unit_cost_thousand_krw=22_000,
        quantity=20,
        unit_label="22,000천원/단지",
        quantity_label="구축대상 20개 단지",
        occurrence="year1_only",
        evidence_source="프로토타입 단가표 - 스마트 에너지 모니터링 구축 가정(2026)",
        evidence_detail="센서, 계량기, 대시보드 구축비를 포함한 단지별 초기 구축 단가",
        legal_hint="제7조 제1항 제2호 및 제3호",
    ),
    CostRule(
        id="system_maintenance",
        keywords=("모니터링", "스마트", "운영"),
        category="운영비",
        item="에너지 모니터링 시스템 유지관리",
        unit_cost_thousand_krw=3_000,
        quantity=20,
        unit_label="연 3,000천원/단지",
        quantity_label="구축단지 20개 단지",
        occurrence="annual",
        evidence_source="프로토타입 단가표 - 스마트 시스템 유지관리 가정(2026)",
        evidence_detail="구축 이후 소프트웨어 운영 및 유지관리비를 연간 단가로 반영",
        legal_hint="제7조 제1항 제2호 및 제3호",
    ),
    CostRule(
        id="program_operations",
        keywords=("위탁", "지원계획", "협력체계"),
        category="인건비",
        item="사업 운영 및 위탁관리 인력",
        unit_cost_thousand_krw=180_000,
        quantity=1,
        unit_label="연 180,000천원/운영단위",
        quantity_label="전담 운영 1식",
        occurrence="annual",
        evidence_source="프로토타입 단가표 - 사업관리 운영비 가정(2026)",
        evidence_detail="전담인력, 행정지원, 사업관리 용역을 포함한 연간 운영비 1식",
        legal_hint="제8조 및 제9조",
    ),
)


PRECEDENTS: tuple[dict[str, str], ...] = (
    {
        "title": "공공임대주택 주거비 경감 지원 시범사업",
        "summary": "공용 관리비 지원은 반복적 세출 구조를 형성하므로 대상 단지 수와 지원 상한을 전제조건으로 명시해야 함.",
    },
    {
        "title": "에너지 효율화 공동주택 개선사업",
        "summary": "조명 교체, 모니터링 시스템 구축은 1차년도 집중투자와 이후 유지관리비로 구분하여 추계하는 것이 일반적임.",
    },
    {
        "title": "지자체 위탁형 주거복지 사업",
        "summary": "사무 위탁 조항이 있으면 사업운영 인건비 또는 관리용역비를 별도 비용항목으로 분리하는 것이 타당함.",
    },
)

