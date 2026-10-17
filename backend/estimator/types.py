"""통합 비용추계기 — 테이블 생성 도메인 모델.

출력물은 비용추계서 테이블(행=비용항목, 열=5개년). 이 모듈은 그 테이블을
구성하는 자료구조를 정의한다. 계산·감지·해결 로직은 각 단계 모듈에 있고,
여기서는 "무엇을 담는가"만 정의한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class VariableStatus(str, Enum):
    """변수값이 어떻게 확보됐는지 — 자동화 가능/불가를 구분하는 핵심."""

    DOCUMENT = "document"            # 원문에 명시 → 결정적 파싱
    CONSTANT = "constant"            # 재사용 상수(행정구역 수, 표준단가 등)
    PRECEDENT = "precedent"          # 선례 대표값
    EXTERNAL_PENDING = "external"    # 외부데이터 필요(대상자 수 등) → 아직 미확보
    USER_CONFIRMED = "user"          # 사용자가 확인/입력
    MISSING = "missing"             # 확보 경로 없음


# 자동으로 값이 채워진 상태(계산 가능) vs 사람 개입 필요
_AUTO_FILLED = {VariableStatus.DOCUMENT, VariableStatus.CONSTANT,
                VariableStatus.PRECEDENT, VariableStatus.USER_CONFIRMED}


@dataclass
class ResolvedVariable:
    name: str
    value: float | None
    unit: str
    status: VariableStatus
    basis: str = ""
    source_ref: str = ""            # 선례 의안번호·통계 출처 등
    role: str = "count"             # count(개수) | unit_price(단가) | amount(총액) | rate(비율)

    @property
    def is_filled(self) -> bool:
        return self.value is not None and self.status in _AUTO_FILLED


class Operation(str, Enum):
    """LLM이 의미 파악 후 지정하는 산식 연산 구조. 표준 메뉴에 가두지 않고,
    이해한 비용 구조를 이 일반형으로 표현하면 코드가 결정적으로 계산한다."""

    PRODUCT = "product"          # 변수들의 곱 (예: 대상자 × 단가 × 횟수 × 집행률)
    SUM = "sum"                  # 변수들의 합
    SUM_OF_PRODUCTS = "sum_of_products"  # Σ(그룹별 곱) — 예: 직급별 인원 × 보수
    CUSTOM = "custom"            # 위로 안 되는 경우 (드묾) — 별도 처리


class RowStatus(str, Enum):
    COMPUTED = "computed"                    # 모든 변수 자동 확보 + 계산됨
    REVIEW_REQUIRED = "review_required"      # 계산은 됐으나 선례/가정/복제 등 검토 필요
    NEEDS_EXTERNAL = "needs_external"        # 외부데이터 변수 때문에 미계산
    BLOCKED = "blocked"                      # 확보 경로 없는 변수로 미계산


@dataclass
class Replication:
    """복제 스케일(×N): 한 실체가 여러 지역·기관에 설치될 때의 배수."""
    factor: int = 1
    basis: str = ""
    confident: bool = True


@dataclass
class CostItem:
    """비용추계서 테이블의 한 행."""

    name: str
    article_refs: list[str] = field(default_factory=list)   # 근거 조문(여러 개 가능)
    cost_understanding: str = ""                            # LLM이 파악한 이 항목의 비용 의미(핵심)
    formula: str = ""                                       # 사람이 읽는 산식 문자열(LLM 생성)
    operation: Operation = Operation.PRODUCT               # 계산 연산 구조
    recurrence: str = "annual"                             # annual | one_time
    variables: list[ResolvedVariable] = field(default_factory=list)
    replication: Replication = field(default_factory=Replication)
    year_amounts_thousand: list[int | None] = field(default_factory=list)
    status: RowStatus = RowStatus.BLOCKED
    evidence: list[dict[str, Any]] = field(default_factory=list)

    @property
    def unfilled_variables(self) -> list[str]:
        return [v.name for v in self.variables if not v.is_filled]

    @property
    def total_thousand(self) -> int | None:
        vals = [a for a in self.year_amounts_thousand if a is not None]
        return sum(vals) if vals else None


@dataclass
class EstimateTable:
    """비용추계서 테이블 전체."""

    bill_no: str | None
    bill_name: str
    doc_type: str
    years: int = 5
    items: list[CostItem] = field(default_factory=list)
    excluded_items: list[dict[str, Any]] = field(default_factory=list)  # grounding에서 제거된 것
    holdout_excluded: set[str] = field(default_factory=set)

    def year_totals_thousand(self) -> list[int | None]:
        totals: list[int | None] = []
        for i in range(self.years):
            cells = [
                it.year_amounts_thousand[i]
                for it in self.items
                if i < len(it.year_amounts_thousand) and it.year_amounts_thousand[i] is not None
            ]
            totals.append(sum(cells) if cells else None)
        return totals

    def computed_total_thousand(self) -> int:
        return sum(it.total_thousand or 0 for it in self.items)

    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for it in self.items:
            counts[it.status.value] = counts.get(it.status.value, 0) + 1
        return counts
