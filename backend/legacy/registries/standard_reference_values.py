"""정부 공식 통계·지침을 그대로 인용해 여러 의안에서 리터럴하게 반복되는
표준 참조값 (격리 모듈, additive).

실측(전수확인): 아래 세 계열은 DB 내 모든 해당 항목이 값이 100% 일치한다.
- 대법관후보추천위원회 계열 사례금: 3건 전부 350,000원
- 준보훈병원 진료지원: 7건 전부 (38,890명, 133,507원)
- 국립묘지 안장단가: 2건 전부 2,976천원

이런 계열은 DB 선례 검색(임베딩 유사도)보다 이 표를 직접 참조하는 게
정확도가 훨씬 높다 — 특정 선례의 개별 사정(회의횟수 등)이 아니라 정부가
공표한 단일 통계/지침이기 때문이다. court_staff_table.py와 같은 원리.
"""
from __future__ import annotations

STANDARD_REFERENCE_VALUES_VERSION = "standard-reference-values-v1"

SUPREME_COURT_COMMITTEE_STIPEND_RATE_WON = 350_000

# 실측(2024.9 "법안비용추계 이해와 실제" 공식 발간물, chunk 154):
# 「2024년도 예산안 편성 및 기금운용계획안 작성 세부지침」 기준 위원회 참석비 상한.
# 민간위원 1일당 150,000원 + 회의 2시간 이상 시 1회 50,000원 추가 = 최대 200,000원.
# DB 선례에서 20/25/30/35만원 등으로 흩어져 보였던 값들은 이 20만원 상한에
# 위원회별 "전문가 자문료·안건검토수당"이 별도로 얹힌 결과였음이 이 문서로 확인됨.
# DB에 선례가 전혀 없는 위원회형 의안의 최후 폴백(단순 참석수당만 있다고 가정할 때의
# 하한 추정치)으로 쓴다 — 자문료가 얹히는 위원회에는 과소추정일 수 있으므로 참고용.
COMMITTEE_ATTENDANCE_FEE_CEILING_WON = 200_000
COMMITTEE_ATTENDANCE_FEE_CEILING_YEAR = 2024

# 실측(2214325 준보훈병원 진료지원, 독립 원문 재확인 후 정정):
# 최초 7건 DB 값 일치(38,890명·133,507원)를 "표준화계열"로 오판했었음 — 실제로는
# 2025-11-17 동일 발의자가 하루에 낸 8개 자매법안(동일 계산을 8개 법률로 분할)이었고,
# 38,890명은 5개년 시리즈 중 최초연도(2027년) 추정치일 뿐 고정 상수가 아니었음.
# 표준값으로 재사용하지 말 것 — 미래 무관 의안에 이 수치를 적용하면 끼워맞추기가 된다.
VETERAN_HOSPITAL_REFERENCE_UNRELIABLE = {
    "진료대상인원_2027년_추정치": 38_890,
    "진료비단가원": 133_507,
    "주의": "8개 동시발의 자매법안의 분할값. 독립적 표준값 아님 — 참조 금지.",
}

# 실측: 2027년 기준값이며 연 4.9% 상승을 적용해 사용해야 함(단일 상수로 그대로 쓰면
# 목표 연도가 다른 의안에서 오차 발생). 상승 적용은 national_cemetery_interment_cost() 참고.
NATIONAL_CEMETERY_INTERMENT_UNIT_COST_THOUSAND_WON = 2_976
NATIONAL_CEMETERY_INTERMENT_BASE_YEAR = 2027
NATIONAL_CEMETERY_INTERMENT_ANNUAL_GROWTH = 0.049


def committee_attendance_fee_ceiling(article_text: str = "") -> int:
    """DB 선례가 없는 위원회형 의안의 참석수당 상한(2024년 기재부 지침 기준)을 반환한다."""
    return COMMITTEE_ATTENDANCE_FEE_CEILING_WON


def national_cemetery_interment_cost_thousand(target_year: int) -> int:
    """목표 연도의 국립묘지 안장단가(천원)를 2027년 기준값에서 연 4.9% 상승 적용해 반환한다."""
    years_ahead = target_year - NATIONAL_CEMETERY_INTERMENT_BASE_YEAR
    value = NATIONAL_CEMETERY_INTERMENT_UNIT_COST_THOUSAND_WON * (
        (1 + NATIONAL_CEMETERY_INTERMENT_ANNUAL_GROWTH) ** years_ahead
    )
    return int(round(value))


def is_supreme_court_committee(bill_title: str, description: str, article_text: str = "") -> bool:
    """대법원 소속(관할) 후보추천위원회류인지 판단한다.

    실측(2213116 전담재판부후보추천위원회): 위원회 이름 자체는 "대법관"이
    아니지만, NABO가 "대법관후보자추천위원회의 사례를 참고하여 350,000원을
    지급"이라고 명시 — 조문에 "대법원에... 위원회를 둔다"는 소속 신호가
    있으면(위원회 이름과 무관하게) 같은 표준 단가를 적용한다.
    """
    text = ((bill_title or "") + (description or "")).replace(" ", "")
    if ("대법관" in text or "헌법재판관" in text) and "추천위원회" in text:
        return True
    article_compact = (article_text or "").replace(" ", "")
    return "대법원에" in article_compact and "추천위원회" in article_compact


def is_veteran_hospital_reference_case(bill_title: str, description: str) -> bool:
    """준보훈병원(위탁병원) 진료지원 유형인지 판단한다."""
    text = ((bill_title or "") + (description or "")).replace(" ", "")
    return "준보훈병원" in text


def is_national_cemetery_interment_case(bill_title: str, description: str) -> bool:
    """국립묘지 안장 확대형인지 판단한다."""
    text = ((bill_title or "") + (description or "")).replace(" ", "")
    return "국립묘지" in text and "안장" in text
