"""법원공무원 직급별 평균연봉액 표준 참조표 (격리 모듈, additive).

실측: 안양지방법원(2213969)·고양지방법원(2212273) 두 신설 의안의 "2025년
예산 기준" 직급별 평균연봉액이 3~9급까지 완전히 동일하다(대법원 제출자료
기반, NABO가 그대로 재사용). 인천회생법원(2213022)은 한 해 전인 "2024년
기준" 표를 썼는데 그것도 다른 의안(2211733)과 일치했다 — 즉 매년 갱신되는
표준표가 있고, 그 표를 그대로 재사용하는 게 관행이다.

grade_salary.py의 범용 DB 중앙값(여러 위원회·기관이 섞인 값)을 법원 신설
의안에 쓰면 -12~-19% 과소추정이 났다(법원공무원/공안직 수당이 일반직보다
높음). 법원 신설 의안임을 인식하면 이 표를 대신 써야 정확하다.
"""
from __future__ import annotations

COURT_STAFF_TABLE_VERSION = "court-staff-table-2025"

# 2025년 예산 기준(안양·고양지방법원 의안 공통, 단위: 원/년)
COURT_STAFF_SALARY_2025 = {
    "3급": 134_897_659,
    "4급": 122_008_949,
    "5급": 100_863_123,
    "6급": 83_431_626,
    "7급": 81_864_430,
    "8급": 52_218_181,
    "9급": 42_271_410,
}

# 2024년 기준(인천회생법원 등, 참고용 — 새 의안엔 2025년 기준을 우선 써야 함)
COURT_STAFF_SALARY_2024 = {
    "3급": 129_600_800,
    "4급": 116_324_810,
    "5급": 98_143_414,
    "6급": 80_914_516,
    "7급": 74_258_001,
    "8급": 50_521_375,
    "9급": 41_088_234,
}

_COURT_KEYWORDS = ("지방법원", "고등법원", "회생법원", "가정법원", "행정법원", "법원의설치")


def is_court_establishment_bill(bill_title: str, description: str) -> bool:
    """의안명·조문설명이 법원 신설/증설 유형인지 판단한다(기계적 키워드 체크).

    의안명에 법원 종류(지방법원·고등법원 등)가 있으면 그 자체로 충분하다
    (법원 설치/관할구역 개정안은 거의 항상 의안명에 명시됨). 의안명이
    애매하면 조문설명에 "법원공무원"이 같이 나오는지로 보강한다.
    """
    title = (bill_title or "").replace(" ", "")
    if any(kw in title for kw in _COURT_KEYWORDS):
        return True
    desc = (description or "").replace(" ", "")
    return "법원공무원" in desc and any(kw in desc for kw in _COURT_KEYWORDS)


def court_staff_annual_salary(grade: str, *, year_basis: int = 2025) -> int | None:
    """직급별 법원공무원 평균연봉액(원)을 반환한다. 없으면 None."""
    table = COURT_STAFF_SALARY_2025 if year_basis >= 2025 else COURT_STAFF_SALARY_2024
    return table.get(grade)
