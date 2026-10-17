"""범용 TAG 동적 참조 엔진 프로토타입 (test-only, 프로덕션 미연결).

`tag_reference_lookup.py`(상임위원 급여 전용, tag_rule_engine.py에 실제
배선됨)의 핵심 아이디어 — "TAG DB population이 안정적으로 좁게 수렴할 때만
동적 대표값을 쓰고, 아니면 정적 폴백으로 넘긴다" — 를 위원회 도메인 밖까지
일반화한 프로토타입이다. 아무 정규식 패턴이나 등록하면 코퍼스 전체
(위원회·인사·이전지급 등 모든 카테고리)에서 population을 뽑아 안정성을
검증한다.

주의: 이 스크립트는 탐색용이다. 여기서 "안정적"으로 나온 후보라도
tag_rule_engine.py에 실제로 배선하려면 상임위원 급여 때처럼 최소 1개
실제 의안으로 정답 대조까지 해야 한다 — 안정적 population과 "이 변수를
써도 되는 것"은 다른 문제다(회의횟수가 안정적이어도 그 자체가 필요한
질문에 답을 못 줄 수 있다).
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from backend.erce_web.committee_channel import _read_jsonl_records, _tag_roots  # noqa: E402


@dataclass(frozen=True)
class ReferenceResult:
    label: str
    value: float | None
    stable: bool
    n: int
    samples: tuple[float, ...] = field(default_factory=tuple)
    max_min_ratio: float | None = None
    reason: str = ""


class TagEngine:
    """위원회에 국한되지 않는 범용 TAG DB 동적 조회 엔진.

    사용법:
        engine = TagEngine()
        result = engine.query(
            label="상임위원_급여",
            match_re=r"상임위원.*(?:보수|인건비|연봉)",
            exclude_re=r"차관급|장관급|1급|2급|3급",
            value_range=(10_000_000, 500_000_000),
        )
    """

    MIN_SAMPLES = 3
    MAX_RATIO = 1.5

    def __init__(self) -> None:
        self._all_rows: list[dict] | None = None

    def _rows(self) -> list[dict]:
        if self._all_rows is None:
            rows: list[dict] = []
            for root in _tag_roots():
                rows.extend(_read_jsonl_records(root / "cost_estimate_variables.jsonl"))
            self._all_rows = rows
        return self._all_rows

    def query(
        self,
        *,
        label: str,
        match_re: str,
        exclude_re: str | None = None,
        value_range: tuple[float, float] = (0, float("inf")),
        variable_type: str | None = None,
        min_samples: int | None = None,
        max_ratio: float | None = None,
    ) -> ReferenceResult:
        match_pat = re.compile(match_re)
        exclude_pat = re.compile(exclude_re) if exclude_re else None
        low, high = value_range
        min_n = min_samples if min_samples is not None else self.MIN_SAMPLES
        max_r = max_ratio if max_ratio is not None else self.MAX_RATIO

        samples: list[float] = []
        for row in self._rows():
            if variable_type and row.get("variable_type") != variable_type:
                continue
            combined = str(row.get("variable_name") or "") + str(row.get("source_text") or "")
            if not match_pat.search(combined):
                continue
            if exclude_pat and exclude_pat.search(combined):
                continue
            value = row.get("variable_value")
            if isinstance(value, (int, float)) and low <= value <= high:
                samples.append(float(value))

        if len(samples) < min_n:
            return ReferenceResult(
                label=label, value=None, stable=False, n=len(samples),
                samples=tuple(samples),
                reason=f"표본 부족(n={len(samples)} < {min_n})",
            )
        ratio = max(samples) / min(samples) if min(samples) > 0 else float("inf")
        if ratio > max_r:
            return ReferenceResult(
                label=label, value=None, stable=False, n=len(samples),
                samples=tuple(samples), max_min_ratio=ratio,
                reason=f"표본 분산 과대(최대/최소={ratio:.2f} > {max_r})",
            )
        return ReferenceResult(
            label=label, value=statistics.median(samples), stable=True, n=len(samples),
            samples=tuple(samples), max_min_ratio=ratio, reason="안정적 수렴",
        )


# 탐색 후보 — 위원회 도메인 하나(이미 검증된 것, 대조군)에 인사·이전지급
# 도메인 후보 4개를 추가해 "위원회 전용이 아닌 범용 엔진"임을 실측으로 확인한다.
CANDIDATES = [
    dict(
        label="상임위원_급여(위원회, 대조군·이미검증)",
        match_re=r"상임위원.*(?:보수|인건비|연봉)",
        exclude_re=r"차관급|장관급|1급|2급|3급",
        value_range=(10_000_000, 500_000_000),
    ),
    dict(
        label="정부기관_1인당_자산취득비(범용, 인사/위원회 공통)",
        match_re=r"1인당\s*자산취득비",
        value_range=(1_000_000, 10_000_000),
    ),
    dict(
        label="공무원_신규채용_기관부담요율(범용)",
        match_re=r"신규\s*채용.{0,10}기관부담\s*요율|기관부담요율",
        value_range=(0.05, 0.20),
    ),
    dict(
        label="회의참석수당_단가(위원회, 이미 알려진 20~40만원 계열과 비교)",
        match_re=r"회의참석수당|참석\s*수당",
        variable_type="unit_cost",
        value_range=(100_000, 1_000_000),
    ),
    dict(
        label="아동복지시설_1인당_지원단가(이전지급 도메인)",
        match_re=r"아동.{0,10}(?:1인당|지급단가)|지급단가.{0,10}아동",
        value_range=(100_000, 100_000_000),
    ),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    engine = TagEngine()
    results = []
    for spec in CANDIDATES:
        result = engine.query(**spec)
        results.append(result)
        status = "✅ 안정적" if result.stable else "❌ 불안정"
        print(f"[{status}] {result.label}")
        print(f"    n={result.n}  ratio={result.max_min_ratio}  이유={result.reason}")
        if result.stable:
            print(f"    → 대표값={result.value:,.0f}")
        else:
            preview = result.samples[:10]
            print(f"    표본 미리보기: {preview}")
        print()

    if args.output:
        payload = [
            {
                "label": r.label, "value": r.value, "stable": r.stable, "n": r.n,
                "max_min_ratio": r.max_min_ratio, "reason": r.reason,
                "samples": list(r.samples),
            }
            for r in results
        ]
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
