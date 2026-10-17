"""지원금(subsidy) 항목을 산식 유형(shape)으로 분류한다 (격리 모듈, additive).

실측(전수조사, 904건): 지원금은 "무한히 다양"하지 않다 — 세금감면류 53.1%,
단순곱셈류 28.4%가 전체의 81.5%를 차지한다. 위원회가 change_kind로 8개
유형에 템플릿을 매핑하듯, 지원금도 shape로 분류한 뒤 유형별로 다르게
처리한다.

- 세금감면류: "최근 N년 평균 감면실적 유지" 또는 "총 감면액의 비율" —
  곱셈식이 아니라 기존 실적치를 그대로 쓰거나 비율을 곱하는 형태. 필요한
  전제는 "최근 실적 감면액"(국세청/지방세 통계) 하나뿐이다.
- 단순곱셈류: 대상자 수 × 단가 × 기간 — 위원회와 같은 방식으로 DB
  선례에서 값을 채운다.
- 인구캐스케이드류: 전체의 1%뿐이다. 인구추계 × 여러 비율 곱셈 — 이 유형은
  구조적으로 어려우므로(오늘 밤 실측 확인) 시도하지 않고 사람에게 넘긴다.
"""
from __future__ import annotations

import re

SUBSIDY_SHAPE_VERSION = "subsidy-shape-v1"

_TAX_RELIEF = re.compile(r"감면|세수|조세지출|세율|과세|공제")
_CASCADE = re.compile(r"인구추계|장래가구|집행계수")
_RECENT_ACTUAL = re.compile(r"(최근|202\d년).{0,20}(실적|잠정치)|(실적|잠정치).{0,10}유지")
_FRACTION_OF_TOTAL = re.compile(r"총\s*[가-힣]*세?\s*감면액.{0,10}[의]?\s*\d+\s*/\s*\d+")


def classify_subsidy_shape(formula_text: str) -> str:
    """산식 문자열을 shape로 분류한다.

    반환: "tax_relief_recent_actual" | "tax_relief_fraction" | "tax_relief_other"
          | "demographic_cascade" | "simple_multiplication" | "other"
    """
    text = formula_text or ""
    if _CASCADE.search(text):
        return "demographic_cascade"
    if _TAX_RELIEF.search(text):
        if _RECENT_ACTUAL.search(text):
            return "tax_relief_recent_actual"
        if _FRACTION_OF_TOTAL.search(text):
            return "tax_relief_fraction"
        return "tax_relief_other"
    if "×" in text or "*" in text:
        return "simple_multiplication"
    return "other"


_SHAPE_GUIDANCE = {
    "tax_relief_recent_actual": {
        "template": "최근 N년 평균(또는 최근 연도) 감면실적을 그대로 유지",
        "required_premise": ["최근 실적 감면액(국세청/지방세 통계)"],
    },
    "tax_relief_fraction": {
        "template": "관련 세목 총 감면액 × 비율(분수)",
        "required_premise": ["관련 세목 총 감면액", "적용 비율"],
    },
    "tax_relief_other": {
        "template": "조세지출 실적 기반 추계(세부 방식 확인 필요)",
        "required_premise": ["기준연도 조세지출 실적", "추계 방식"],
    },
    "simple_multiplication": {
        "template": "대상자 수 × 단가 × 기간(위원회와 동일 방식으로 DB 선례에서 값 탐색)",
        "required_premise": ["대상자 수", "단가", "기간"],
    },
    "demographic_cascade": {
        "template": "인구추계 × 다단계 비율 × 단가 (구조적으로 어려움, 자동화 시도 안 함)",
        "required_premise": ["전문 통계모형 또는 HITL 전체"],
    },
    "other": {
        "template": "미분류",
        "required_premise": ["산식 자체 확인 필요"],
    },
}


def shape_guidance(shape: str) -> dict:
    return _SHAPE_GUIDANCE.get(shape, _SHAPE_GUIDANCE["other"])
