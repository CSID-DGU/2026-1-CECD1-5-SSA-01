from __future__ import annotations

import re
from collections import Counter

from .types import AtomicEvent, Recurrence, TagCandidate


_EVERY_N_RE = re.compile(r"(\d+)\s*년\s*(?:마다|주기)")
_ANNUAL_RE = re.compile(r"매\s*년|연\s*간|매\s*회계연도|해마다")


def _candidate_pattern(candidate: TagCandidate) -> str:
    rows = [
        row
        for row in candidate.amounts
        if row.get("year_offset") is not None and row.get("amount_thousand") is not None
    ]
    if not rows:
        return ""
    by_offset = {
        int(row["year_offset"]): int(row["amount_thousand"])
        for row in rows
        if int(row["year_offset"]) >= 0
    }
    if not by_offset:
        return ""
    positive = sorted(offset for offset, amount in by_offset.items() if amount > 0)
    if len(positive) >= 3 and positive == list(range(positive[0], positive[-1] + 1)):
        return "annual"
    if len(positive) == 1 and len(by_offset) >= 3:
        return "one_time"
    if len(positive) >= 2:
        gaps = [b - a for a, b in zip(positive, positive[1:])]
        if gaps and len(set(gaps)) == 1 and gaps[0] > 1:
            return f"every_{gaps[0]}"
    return ""


def resolve_recurrence(
    event: AtomicEvent,
    source_text: str,
    candidates: list[TagCandidate],
) -> Recurrence:
    """Use explicit law text first, then repeated TAG time-series evidence."""
    explicit = f"{event.recurrence_text} {source_text}"
    match = _EVERY_N_RE.search(explicit)
    if match:
        interval = int(match.group(1))
        return Recurrence("every_n_years", interval, "law_text", match.group(0))
    if _ANNUAL_RE.search(explicit):
        return Recurrence("annual", 1, "law_text", "매년/연간 명시")

    formula_match = _EVERY_N_RE.search(" ".join(candidate.formula for candidate in candidates))
    if formula_match:
        interval = int(formula_match.group(1))
        return Recurrence("every_n_years", interval, "tag_formula", formula_match.group(0))

    patterns = [_candidate_pattern(candidate) for candidate in candidates]
    patterns = [pattern for pattern in patterns if pattern]
    if patterns:
        pattern, votes = Counter(patterns).most_common(1)[0]
        if votes >= 2 and votes / len(patterns) >= 0.6:
            if pattern == "annual":
                return Recurrence("annual", 1, "tag_time_series", f"{votes}/{len(patterns)}개 선례")
            if pattern == "one_time":
                return Recurrence("one_time", None, "tag_time_series", f"{votes}/{len(patterns)}개 선례")
            if pattern.startswith("every_"):
                interval = int(pattern.split("_", 1)[1])
                return Recurrence(
                    "every_n_years",
                    interval,
                    "tag_time_series",
                    f"{votes}/{len(patterns)}개 선례",
                )
    return Recurrence("unknown", None, "unresolved", "반복 주기 근거 부족")


def schedule_amount(annual_or_event_thousand: int, recurrence: Recurrence, years: int) -> list[int | None]:
    if recurrence.mode == "annual":
        return [annual_or_event_thousand] * years
    if recurrence.mode == "one_time":
        return [annual_or_event_thousand, *([0] * max(0, years - 1))]
    if recurrence.mode == "every_n_years" and recurrence.interval_years:
        return [
            annual_or_event_thousand if index % recurrence.interval_years == 0 else 0
            for index in range(years)
        ]
    return [None] * years
