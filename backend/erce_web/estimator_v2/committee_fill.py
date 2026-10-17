"""위원회 회의비 부분 채우기 (격리 모듈, additive).

현재 엔진은 위원회 회의비의 *산식*(위원 수 × 회의 횟수 × 수당)은 찾지만,
선택된 선례에 변수가 비어 있으면 **변수 0개로 막아버린다**(needs_user_input).
조문에 위원 수가 있고 수당·회의 횟수는 유사 위원회 코호트로 채울 수 있는데도
전부 포기하는 것은 과잉 블록이다.

이 모듈은 **막힌 위원회 행에 한해**:
 - 위원 수 → 조문(행 quotes)에서 추출, 없으면 코호트 중앙값
 - 연간 회의 횟수 → 위원회 코호트 중앙값
 - 1회 수당 → 위원회 코호트 중앙값
로 채워 **저신뢰 초안(review 필요)**을 만든다. 값은 특정 정답이 아니라 DB 코호트에서
오며, 출처·신뢰도를 근거에 명시한다. 완전 블라인드 정확도가 아니라 "0 대신 확인 가능한
초안 + 사람이 고칠 지점"을 제공하는 것이 목적이다.

**막힌 위원회 행에만 작동**하므로, 이미 계산된 위원회 행(회귀 케이스 등)은 손대지 않는다.
"""
from __future__ import annotations

import glob
import json
import re
import statistics
from functools import lru_cache

from .types import Recurrence, RowStatus

COMMITTEE_FILL_VERSION = "committee-fill-v1"
_GENERATED = "backend/generated"


@lru_cache(maxsize=1)
def committee_cohort() -> dict[str, int]:
    """DB 위원회 선례에서 위원 수·연간 회의·1회 수당의 중앙값(코호트 기준값)."""
    members: list[float] = []
    meetings: list[float] = []
    allowance: list[float] = []
    items: dict[str, str] = {}
    for path in glob.glob(f"{_GENERATED}/**/cost_estimate_items.jsonl", recursive=True):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                it = json.loads(line)
            except json.JSONDecodeError:
                continue
            items[it.get("item_id", "")] = str(it.get("item_name") or "")
    for path in glob.glob(f"{_GENERATED}/**/cost_estimate_variables.jsonl", recursive=True):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                v = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not re.search(r"위원회|심의회|협의회", items.get(v.get("item_id", ""), "")):
                continue
            value = v.get("variable_value")
            if value is None:
                continue
            try:
                fv = float(value)
            except (TypeError, ValueError):
                continue
            name = str(v.get("variable_name") or "")
            vtype = str(v.get("variable_type") or "")
            if vtype == "target_count" and re.search(r"위원|위촉|민간", name) and 3 <= fv <= 60:
                members.append(fv)
            elif vtype == "frequency" and re.search(r"회의|개최|횟수", name) and 1 <= fv <= 30:
                meetings.append(fv)
            elif vtype == "unit_cost" and re.search(r"수당|참석|검토", name):
                won = fv * 10000 if fv < 100 else fv
                if 100_000 <= won <= 700_000:
                    allowance.append(won)
    return {
        "members": int(statistics.median(members)) if members else 10,
        "meetings": int(statistics.median(meetings)) if meetings else 4,
        "allowance_won": int(statistics.median(allowance)) if allowance else 250_000,
    }


def _members_from_quotes(quotes: list[str]) -> int | None:
    text = " ".join(quotes or "")
    nums = [int(n) for n in re.findall(r"(\d+)\s*명", text)]
    reasonable = [n for n in nums if 3 <= n <= 60]
    return max(reasonable) if reasonable else None


def _is_blocked_committee_row(row) -> bool:
    return (
        row.status == RowStatus.NEEDS_USER_INPUT
        and row.event is not None
        and row.event.event_type == "committee_operation"
        and not row.variable_evidence  # 변수 0개로 막힌 경우
    )


def apply_committee_fill(result, *, years: int = 5) -> int:
    """막힌 위원회 행을 코호트·조문 기반 저신뢰 초안으로 채운다. 채운 행 수 반환."""
    cohort = committee_cohort()
    filled = 0
    for row in result.rows:
        if not _is_blocked_committee_row(row):
            continue
        bill_members = _members_from_quotes(row.event.quotes)
        members = bill_members if bill_members is not None else cohort["members"]
        member_src = "조문 명시" if bill_members is not None else "위원회 코호트 중앙값"
        meetings = cohort["meetings"]
        allowance = cohort["allowance_won"]
        annual_won = members * meetings * allowance
        annual_thousand = int(round(annual_won / 1000))
        row.status = RowStatus.COMPUTED_REVIEW
        row.reason_codes = [*row.reason_codes, "COMMITTEE_FILLED_DRAFT"]
        row.reason = (
            f"저신뢰 초안: 산식(위원 수 × 연간 회의 × 1회 수당)에 값을 채웠습니다. "
            f"위원 {members}명({member_src}), 연간 회의 {meetings}회(위원회 코호트 중앙값), "
            f"1회 수당 {allowance:,}원(위원회 코호트 중앙값). "
            "회의 횟수·수당은 유사 위원회 평균이라 실제와 다를 수 있으니 확인이 필요합니다."
        )
        row.formula = f"{members}명 × {meetings}회 × {allowance:,}원"
        row.recurrence = Recurrence("annual", None, COMMITTEE_FILL_VERSION, "코호트 채우기")
        row.year_amounts_thousand = [annual_thousand] * years
        row.selection_method = COMMITTEE_FILL_VERSION
        row.selection_confidence = 0.4
        row.variable_evidence = [
            {"name": "위원 수", "value": members, "unit": "명", "source": member_src},
            {"name": "연간 회의", "value": meetings, "unit": "회", "source": "cohort_median"},
            {"name": "1회 수당", "value": allowance, "unit": "원", "source": "cohort_median"},
        ]
        filled += 1
    return filled
