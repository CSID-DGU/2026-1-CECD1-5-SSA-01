"""위원회 참석수당 규칙 엔진 (격리 모듈, additive).

역할 분리 원칙:
- LLM(`extract_committee_info`): 절대 계산·단가추론을 하지 않는다. 조문에 명시된
  숫자만 파싱해 CommitteeExtraction으로 반환한다. **명시 안 된 값은 지어내지 않고
  None으로 남긴다** — 0으로 단정하지 않는다(아래 "실측 교훈" 참고).
- Python(`calculate_committee_cost`): 추출된 값을 받아 고정 규칙으로만 계산한다.
  단가는 2024년 기재부 지침 기준 실무 관행값을 상수로 고정한다(TAG 선례 재사용 없음).

조문 분리(PDF → 조문 리스트)는 새로 만들지 않고 기존 `analyzer_v2.split_articles`를
재사용한다 — 이미 검증된 범용 인프라라 중복 구현하지 않는다.

프로젝트에 pydantic/openai SDK가 없어(requirements.txt 확인됨) dataclass +
기존 `_gemini_raw_json`(LLM_PROVIDER=upstage면 Upstage로 라우팅됨)을 그대로 쓴다.

실측 교훈(2213848 재생에너지자립단지위원회, 진짜 원문으로 검증):
법조문은 흔히 "대통령령으로 정하는 관계 중앙행정기관의 장"처럼 당연직 위원 수를
숫자로 명시하지 않는다. 이 경우 NABO 분석관은 "해당 업무와 관련성이 큰 부처가
몇 개인지" 자체 판단으로 가정한다(2024.9 「법안비용추계 이해와 실제」에 명시된
관행). 조문 파싱만으로는 알 수 없는 값이므로, ex_officio_members를 0으로
단정하면 위원 전원을 수당대상으로 계산해 과대추정(2213848 실측: +30.4%)이 난다.
그래서 이 엔진은 "명시 안 됨"을 None으로 구분하고, 그 경우 확정 계산 대신
상/하한 구간과 review_required 상태를 반환한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from backend.analyzer_v2 import _extract_pdf_text_from_bytes, _gemini_raw_json, split_articles

COMMITTEE_RULE_ENGINE_VERSION = "committee-rule-engine-v2"

# [룰 3] 2024년 「예산안 편성 및 기금운용계획안 작성 세부지침」 기준.
# 순수 참석비 법정 상한은 15만원(+2시간이상 5만원)=20만원이지만, 실무에서는
# 회의자료 인쇄비·참석경비·업무추진비 등을 포함해 대면회의 1회 25만원으로
# 편성하는 게 관행이다(실측: 2213848 재생에너지자립단지위원회, 25만원 그대로 채택).
ALLOWANCE_UNIT_COST_WON = 250_000

# [룰 2] 조문에 회의 횟수가 없을 때의 관행 기준값(분기별 1회 상당).
DEFAULT_MEETINGS_PER_YEAR = 4

DEFAULT_YEARS = 5

_COMMITTEE_NAME_RE = re.compile(r"[가-힣A-Za-z0-9·ㆍ]{2,40}(?:위원회|심의회|협의회)")
_COMMITTEE_ESTABLISH_RE = re.compile(r"(?:을|를)?\s*둔다|설치한다|구성한다|둘\s*수\s*있다")


@dataclass
class CommitteeExtraction:
    committee_name: str
    total_members_max: int
    ex_officio_members: int | None  # None = 조문에 숫자로 명시 안 됨
    meetings_per_year: int | None  # None = 조문에 명시 안 됨
    article_no: str = ""


def find_committee_establishing_articles(
    articles: list[dict[str, str]],
) -> list[dict[str, str]]:
    """'~위원회를 둔다/설치한다/구성한다' 조문만 골라낸다(기계적 정규식, LLM 아님)."""
    found: list[dict[str, str]] = []
    for article in articles:
        text = f"{article.get('title', '')} {article.get('text', '')}"
        if not _COMMITTEE_NAME_RE.search(text):
            continue
        if _COMMITTEE_ESTABLISH_RE.search(text):
            found.append(article)
    return found


_EXTRACTION_PROMPT = """당신은 법안 조문에서 위원회 구성 정보만 추출하는 파서다.

절대 금지: 비용 계산, 단가 추정, 조문에 없는 숫자를 만들어내는 것.
조문에 문자 그대로 명시된 숫자만 뽑아라.

추출 규칙:
- committee_name: 위원회의 법적 명칭.
- total_members_max: 위원회 위원 정수의 최대값(예: "30명 이내로 구성" → 30).
- ex_officio_members: 당연직(공무원 등) 위원 "수"가 조문에 숫자로 명시된 경우에만
  그 숫자를 쓴다. "대통령령으로 정하는 관계 중앙행정기관의 장"처럼 숫자 없이
  위임돼 있으면 반드시 null을 반환한다 — 0으로 추측하지 마라. 위원장 1인만 당연직임이
  명확하면 1로 쓴다.
- meetings_per_year: 연간 회의 횟수. 숫자로 명시돼 있으면 그 값, "분기별 1회"처럼
  주기로만 표현되면 연간 횟수로 환산한다(분기별=4, 반기별=2, 월별=12, 격월=6).
  전혀 언급이 없으면 null.

JSON만 반환한다. 다른 텍스트를 덧붙이지 마라.
{{"committee_name": "...", "total_members_max": 0, "ex_officio_members": 0 또는 null, "meetings_per_year": 0 또는 null}}

[조문]
{article_text}
"""


def extract_committee_info(article_text: str, *, article_no: str = "") -> CommitteeExtraction:
    """LLM으로 조문에서 순수 변수만 추출한다. 계산은 절대 하지 않는다."""
    parsed = _gemini_raw_json(_EXTRACTION_PROMPT.format(article_text=article_text))
    if not isinstance(parsed, dict):
        raise ValueError(f"LLM 추출 결과가 JSON 객체가 아닙니다: {parsed!r}")

    name = str(parsed.get("committee_name") or "").strip()
    if not name:
        raise ValueError("committee_name을 추출하지 못했습니다.")

    try:
        total_members_max = int(parsed["total_members_max"])
    except (KeyError, TypeError, ValueError):
        raise ValueError(
            f"total_members_max를 정수로 추출하지 못했습니다: {parsed.get('total_members_max')!r}"
        )

    ex_officio_raw = parsed.get("ex_officio_members")
    ex_officio_members = None
    if ex_officio_raw is not None:
        try:
            ex_officio_members = int(ex_officio_raw)
        except (TypeError, ValueError):
            ex_officio_members = None

    meetings_raw = parsed.get("meetings_per_year")
    meetings_per_year = None
    if meetings_raw is not None:
        try:
            meetings_per_year = int(meetings_raw)
        except (TypeError, ValueError):
            meetings_per_year = None

    return CommitteeExtraction(
        committee_name=name,
        total_members_max=total_members_max,
        ex_officio_members=ex_officio_members,
        meetings_per_year=meetings_per_year,
        article_no=article_no,
    )


def calculate_committee_cost(
    extraction: CommitteeExtraction, *, years: int = DEFAULT_YEARS
) -> dict:
    """추출된 변수를 고정 규칙(Rule Engine)으로만 계산한다. LLM 호출 없음."""
    meetings = (
        extraction.meetings_per_year
        if extraction.meetings_per_year is not None
        else DEFAULT_MEETINGS_PER_YEAR
    )
    base = {
        "committee_name": extraction.committee_name,
        "article_no": extraction.article_no,
        "total_members_max": extraction.total_members_max,
        "meetings_per_year": meetings,
        "meetings_per_year_is_default": extraction.meetings_per_year is None,
        "allowance_unit_cost_won": ALLOWANCE_UNIT_COST_WON,
        "years": years,
    }

    # [룰 1] 당연직 수가 조문에 없으면 확정 계산하지 않는다 — 상/하한만 제시.
    if extraction.ex_officio_members is None:
        upper_paid = extraction.total_members_max  # 당연직 0 가정(최대, 과대추정 가능)
        lower_paid = max(extraction.total_members_max - 1, 0)  # 위원장만 당연직 가정(최소)
        return {
            **base,
            "ex_officio_members": None,
            "status": "review_required",
            "reason": (
                "당연직 위원 수가 조문에 숫자로 명시돼 있지 않습니다"
                "(예: '대통령령으로 정하는 관계 중앙행정기관의 장'). "
                "NABO는 이런 경우 관련 부처 수를 자체 판단으로 가정합니다 — "
                "사용자 확인이 필요합니다."
            ),
            "paid_members_range": [lower_paid, upper_paid],
            "annual_cost_won_range": [
                lower_paid * ALLOWANCE_UNIT_COST_WON * meetings,
                upper_paid * ALLOWANCE_UNIT_COST_WON * meetings,
            ],
            "total_cost_won_range": [
                lower_paid * ALLOWANCE_UNIT_COST_WON * meetings * years,
                upper_paid * ALLOWANCE_UNIT_COST_WON * meetings * years,
            ],
        }

    # [룰 1] 당연직 수가 명시된 경우에만 확정 계산.
    paid_members = extraction.total_members_max - extraction.ex_officio_members
    if paid_members <= 0:
        return {
            **base,
            "ex_officio_members": extraction.ex_officio_members,
            "status": "blocked_invalid_members",
            "reason": (
                f"당연직({extraction.ex_officio_members}명)이 위원 정수"
                f"({extraction.total_members_max}명) 이상이라 수당 대상 민간위원을 "
                "산출할 수 없습니다."
            ),
        }

    # [룰 4][룰 5] (물가상승률 미반영, 단순 5년 반복)
    annual_cost_won = paid_members * ALLOWANCE_UNIT_COST_WON * meetings
    total_cost_won = annual_cost_won * years
    return {
        **base,
        "ex_officio_members": extraction.ex_officio_members,
        "paid_members": paid_members,
        "annual_cost_won": annual_cost_won,
        "total_cost_won": total_cost_won,
        "status": "calculated_with_rule",
    }


def analyze_committee_bill(pdf_bytes: bytes, *, years: int = DEFAULT_YEARS) -> list[dict]:
    """PDF 원문 → 조문 분리(재사용) → 위원회 탐지 → 추출 → 계산까지 전체 파이프라인."""
    text = _extract_pdf_text_from_bytes(pdf_bytes)
    articles, _doc_type = split_articles(text)
    committee_articles = find_committee_establishing_articles(articles)

    results: list[dict] = []
    for article in committee_articles:
        article_text = f"{article.get('title', '')}\n{article.get('text', '')}"
        try:
            extraction = extract_committee_info(
                article_text, article_no=str(article.get("no", ""))
            )
        except ValueError as exc:
            results.append({
                "article_no": article.get("no", ""),
                "status": "extraction_failed",
                "reason": str(exc),
            })
            continue
        results.append(calculate_committee_cost(extraction, years=years))
    return results


def main() -> None:
    import json
    from pathlib import Path

    pdf_path = Path(
        "backend/generated/subsidy_bills_diverse10/files/2213848/"
        "2213848_의사국 의안과_의안원문.pdf"
    )
    print(f"=== 실제 원문으로 전체 파이프라인 실행: {pdf_path.name} ===")
    results = analyze_committee_bill(pdf_path.read_bytes())
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(
        "\n실제 정답(2213848 비용추계서): paid_members=23, annual=23,000,000원, "
        "total=115,000,000원"
    )


if __name__ == "__main__":
    main()
