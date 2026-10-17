"""[2][3][4a] 항목별 추계 스펙 — 추계가능성 판정 + 산식 구조 + 변수 출처.

감지된 각 비용항목에 대해 LLM이 조문 의미를 근거로:
 - 추계 가능한가 (변수를 확보해 실제 계산 가능 vs 시행령 위임·근거부족)
 - 산식 구조 (어떤 변수들을 어떻게: 곱/합)
 - 각 변수의 출처 (원문 명시 / 선례 / 외부데이터)와 원문에 있으면 그 값
를 만든다. 숫자는 원문에 명시된 것만 채우고, 나머지는 출처만 표시(환각 금지).
"""
from __future__ import annotations

from typing import Any

from ..analyzer_v2 import gemini_json


_SPEC_PROMPT = """당신은 국회예산정책처 비용추계 분석가다.
아래 '비용항목'과 관련 '조문'을 보고, 이 항목을 어떻게 추계할지 스펙을 만들어라.

1) estimable — 이 항목을 추계할 수 있는가? NABO의 실제 관행을 따르라:
   - **세부 사항이 대통령령·정관에 위임돼 있어도, 유사 선례(비슷한 위원회·조직·용역)로 변수값을
     준용해 추계할 수 있으면 estimable=true 다.** (NABO는 "유사 사례 단가를 준용하여 추계"한다.)
     예: "위원회를 둔다"(수당은 시행령 위임) → 유사 위원회 회의수당으로 추계 가능 → true.
          "종합계획을 수립한다"(규모 미정) → 유사 실태조사 용역비 준용 → true.
   - false(기술적 곤란/제외)는 다음일 때:
       · 임의규정("둘 수 있다","지원할 수 있다")이라 시행 여부 자체가 불확실
       · 선언·목적·정의 규정이라 비용 실체가 없음
       · 유사 선례조차 없어 준용 불가
       · **[중요] 비용이 '미정 규모'에 비례하는데 그 규모를 조문에서 확정할 수 없을 때.**
         예: 인건비(대상 인원 미정 × 보수), 사업비·지원금(대상 기관·인원 수 미정 × 단가).
         국립대병원처럼 '대상 병원 수'가 정해지지 않으면 인건비·사업비는 규모를 확정할 수 없어 기술적 곤란이다.
         반대로 위원회(위원 수가 제한적)·단일 계획수립 용역(규모 무관)은 규모가 확정되므로 estimable.
       · **[중요] 비용 발생의 '방법·기준·단가·주체'가 하위규정(시행령·부령·정관)에 위임돼 확정 불가할 때.**
         예: 평가(평가 방법·기준이 시행령 위임), 감독·지도·인가·등기 같은 행정행위(비용 실체·기준 불명),
         임원 보수(정관 위임). 이런 건 유사 선례가 있어도 이 의안 기준을 확정 못 해 기술적 곤란이다.
   - 판단 요령: "이 비용의 총규모를 결정하는 수량(인원·기관 수)과 단가·기준이 조문(또는 확정된 표준)에서 정해지는가?"
     정해지면 estimable, 미정이면 유사 선례가 있어도 기술적 곤란(false).
   - 위임됐다는 이유만으로 무조건 false는 아니지만(위원회 수당처럼 표준 준용 가능하면 true),
     방법·기준 자체가 불명확해 추계 근거를 세울 수 없으면 false. 핵심은 '규모·기준 확정 가능성'이다.

2) estimable=true이면 산식 구조:
   - operation: "product"(곱) | "sum"(합) | "sum_of_products"
   - recurrence: "annual"(5년 반복) | "one_time"(1회성, 예: 계획수립·시스템구축)
   - variables: 각 변수에 대해
       name: 변수명
       unit: 단위
       role: 이 변수의 계산 역할 — "count"(개수: 인원·횟수·기관 수) | "unit_price"(1단위당 단가: 회의수당·1인당 보수)
             | "amount"(이미 연간 총액인 값: 운영비 등) | "rate"(비율: 부담요율·집행률)
       source: "document"(조문에 값 명시) | "precedent"(선례 대표값) | "external"(행정통계 등 외부)
       document_value: source=document일 때 조문에서 읽은 숫자, 아니면 null
       db_key: source=precedent일 때 아래 목록에서 의미가 맞는 키 하나(없으면 null → 사실상 external):
           committee_meeting_count(위원회 연간 회의횟수), committee_paid_member_count(위원회 수당대상 민간위원 수),
           committee_allowance_unit(회의수당 단가), committee_operating_cost(위원회 연간 운영비),
           staffing_count(조직 정원/인력 수), grade_salary(직급별 1인당 보수),
           employer_contribution_rate(기관부담요율), basic_expense_ratio(기본경비 비율),
           asset_acquisition_unit_cost(1인당 자산취득비), consumer_price_growth_rate(물가상승률),
           public_official_wage_growth_rate(공무원 임금상승률), nominal_wage_growth_rate(명목임금상승률)

규칙:
- 원문에 없는 숫자는 만들지 마라(document_value는 조문에 실제 있을 때만).
- 대상자 수·정책단가처럼 조문에도 없고 위 db_key에도 없는 값은 source="external".
- **산식 정합성(중요)**: operation=product이면 변수들이 '하나의 정합한 곱'을 이뤄야 한다.
  서로 다른 차원(개수 × 단가 × 횟수)만 곱해라. 예: 위원회 회의비 = 회의횟수 × 수당대상 인원 × 회의수당 단가.
  · **이미 '연간 총액'인 값(운영비 committee_operating_cost, 보수 grade_salary 총액 등)을 개수·단가와 함께 곱하지 마라** — 둘 중 하나만.
  · **물가·임금 상승률(growth_rate)은 변수에 넣지 마라** — 5년 동일 가정이라 불필요.
  · 위원회 회의비 항목에는 보수·인건비 변수를 넣지 마라(회의수당만).
- **산식 선택 우선순위(중요)**: 같은 항목을 여러 방식으로 추계할 수 있으면 **'분해 산식'을 우선**하라.
  · 위원회 → **회의횟수 × 수당대상 인원 × 회의수당 단가** (committee_meeting_count, committee_paid_member_count,
    committee_allowance_unit)를 우선. 총액 준용(committee_operating_cost)은 분해 변수를 못 쓸 때만.
  · 인력조직 → 정원 × 1인당 보수(staffing_count × grade_salary) 분해를 우선.
  이유: 총액 키는 평균값이라 과대·과소가 크고, 분해가 대상 규모에 더 정확하다.
- 변수 3~4개를 넘기지 마라. 단순·정합하게.

JSON만 출력:
{"estimable": true, "reason": "...", "operation": "product", "recurrence": "annual",
 "variables": [{"name":"...","unit":"...","role":"count","source":"...","document_value": null, "db_key": null}]}

비용항목: %(item)s
관련 조문:
%(articles)s
"""


def build_item_spec(item: dict[str, Any], article_text: str) -> dict[str, Any]:
    prompt = _SPEC_PROMPT % {
        "item": f"{item.get('name')} (성격: {item.get('cost_kind')}; 이해: {item.get('cost_understanding')})",
        "articles": article_text[:6000],
    }
    parsed = gemini_json(prompt, temperature=0.0)
    if not isinstance(parsed, dict):
        return {"estimable": False, "reason": "스펙 생성 실패", "variables": []}
    variables = parsed.get("variables")
    if not isinstance(variables, list):
        variables = []
    return {
        "estimable": bool(parsed.get("estimable")),
        "reason": str(parsed.get("reason") or "")[:300],
        "operation": str(parsed.get("operation") or "product"),
        "recurrence": str(parsed.get("recurrence") or "annual"),
        "variables": [v for v in variables if isinstance(v, dict) and v.get("name")],
    }
