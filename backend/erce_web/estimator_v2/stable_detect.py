"""사건 추출 다수결 안정화 (격리 모듈, additive).

detect_atomic_events는 temperature=0으로 불러도 동일 입력에 다른 사건 집합을
낼 수 있다(실측: 2214559를 3회 반복 호출 시 2/3는 동일, 1/3은 누락·다른 이름).
단일 호출 결과를 그대로 믿는 대신, N회 반복 호출해 과반수(majority)에서
나타나는 사건만 채택한다. 한 번만 나온 사건(불안정/환각 가능성)은 버리지
않고 별도로 보고해, 조용히 사라지지 않게 한다.

이 모듈은 detect_atomic_events를 감싸기만 하고 대체하지 않는다. 호출 측이
opt-in(예: stable_detection=True)해야 동작하며, 기본 경로는 기존 단일 호출
그대로 유지된다.
"""
from __future__ import annotations

import re
from collections import Counter

from .detect import detect_atomic_events

STABLE_DETECT_VERSION = "stable-detect-majority-v1"


def _canonical_key(event) -> str:
    return re.sub(r"\s+", "", event.object or "")


def detect_atomic_events_stable(
    articles: list[dict],
    *,
    samples: int = 3,
) -> tuple[list, list, dict]:
    """N회 반복 호출해 과반수에서 나온 사건만 채택한다.

    반환: (안정 사건 목록, segments, 보고서 dict)
    보고서 = {"samples": N, "kept": [...], "dropped_unstable": [...]}
    """
    runs: list[list] = []
    segments = None
    for _ in range(samples):
        events, seg, _cache_hit, _pv = detect_atomic_events(articles, refresh=True)
        runs.append(events)
        segments = seg

    counts: Counter[str] = Counter()
    by_key: dict[str, object] = {}
    for events in runs:
        seen_this_run: set[str] = set()
        for event in events:
            key = _canonical_key(event)
            if key in seen_this_run:
                continue
            seen_this_run.add(key)
            counts[key] += 1
            by_key.setdefault(key, event)

    majority = samples // 2 + 1
    kept = []
    dropped = []
    for key, count in counts.items():
        if count >= majority:
            kept.append(by_key[key])
        else:
            dropped.append({"object": key, "appeared_in": count, "of": samples})

    report = {
        "version": STABLE_DETECT_VERSION,
        "samples": samples,
        "majority_threshold": majority,
        "kept_count": len(kept),
        "dropped_unstable": dropped,
    }
    return kept, segments, report
