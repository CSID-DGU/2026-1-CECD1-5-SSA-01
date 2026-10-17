"""지원금 제도명(프로그램명)으로 후보를 먼저 좁히는 게이트 (격리 모듈, additive).

실측(2212685 아동수당): 임베딩 유사도만으로 965개 지원금 항목을 통째로
rank하면, 진짜 정답 산식(2124771, "지급대상자×월지급액×지원개월×집행계수")이
sim=0.59로 다른 무관 항목들과 뒤섞여 0.80 임계값 아래로 묻힌다.

원인: 유사도는 "무슨 행위인지"(연령확대·금액인상·국외체류 등 세부 문구)는
잘 잡지만 "같은 제도인지"(아동수당)는 약하게만 반영한다. 반면 제도명은
조문/추계서에 고유명사로 리터럴하게 등장하므로, 이걸 먼저 문자열 게이트로
거르면 후보 풀이 965개 -> 9개로 좁혀지고, 그 안에서는 유사도가 낮아도
(0.53~0.60) 신뢰할 수 있다(토픽+산식모양이 게이트로 이미 보장됨).

3단계 우선순위:
  1. 제도명 게이트 통과 후보가 있으면 그걸 최우선으로 반환 (낮은 유사도도 허용)
  2. 없으면 기존 shape 기반 검색으로 폴백
  3. 그래도 없으면 빈 결과 (정직한 HITL)
"""
from __future__ import annotations

import re

from .estimator import tag_db

SUBSIDY_PROGRAM_GATE_VERSION = "subsidy-program-gate-v1"

_PROGRAM_NAME_RE = re.compile(r"[가-힣]{2,10}(?:수당|지원금|급여|연금|장려금|보조금)")

_MIN_GATE_SIMILARITY = 0.30


def extract_program_names(text: str) -> set[str]:
    """텍스트에서 제도명 후보(고유명사+수당/지원금/급여/연금/장려금/보조금)를 뽑는다."""
    return set(_PROGRAM_NAME_RE.findall(text or ""))


def search_subsidy_by_program(
    query_vector: list[float],
    description: str,
    *,
    exclude_bill_nos: set[str],
    k: int = 5,
    bill_title: str = "",
) -> tuple[list[dict], bool]:
    """제도명이 문자 그대로 겹치는 지원금 항목만 후보로 삼아 검색한다.

    실측: 조문 단위 LLM 설명("월 20만원 지급 대상 확대")은 제도명 고유명사를
    거의 반복하지 않는다(대명사·구체 행위 위주). 반면 의안 제목("아동수당법
    일부개정법률안")에는 항상 리터럴하게 들어있다. 그래서 제도명은 설명이
    아니라 의안 제목에서 우선 뽑고, 설명에서도 보조로 뽑아 합친다.

    반환: (후보 목록, gate_matched) — gate_matched=True면 제도명 게이트를
    통과한 후보라 유사도가 낮아도 신뢰할 수 있다는 뜻.
    """
    target_programs = extract_program_names(bill_title) | extract_program_names(description)
    if not target_programs:
        return [], False

    data = tag_db._load()
    embeddings = tag_db._load_embeddings()
    formulas = tag_db._formula_by_item()

    scored: list[tuple[float, str]] = []
    for item_id, vector in embeddings.items():
        meta = data["items"].get(item_id, {})
        if meta.get("category") != "지원금":
            continue
        if str(meta.get("bill_no") or "") in exclude_bill_nos:
            continue
        item_programs = extract_program_names(meta.get("name", ""))
        if not (target_programs & item_programs):
            continue
        similarity = tag_db._cosine(query_vector, vector)
        if similarity < _MIN_GATE_SIMILARITY:
            continue
        scored.append((similarity, item_id))
    scored.sort(key=lambda value: -value[0])

    results = []
    for similarity, item_id in scored[:k]:
        meta = data["items"].get(item_id, {})
        results.append(
            {
                "bill_no": meta.get("bill_no", ""),
                "item_name": meta.get("name", ""),
                "similarity": round(similarity, 4),
                "formula": formulas.get(item_id, ""),
                "matched_program": "+".join(sorted(target_programs)),
            }
        )
    return results, bool(results)
