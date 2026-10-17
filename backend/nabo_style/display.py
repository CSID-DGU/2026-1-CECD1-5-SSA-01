"""Short, human-readable labels for evidence (the full provenance stays in the detail panel)."""
from __future__ import annotations

import re

UNITS = {
    "person": "명", "persons": "명", "people": "명", "person/year": "명", "year_to_person": "명", "household": "가구", "KRW": "원", "won": "원", "KRW/person": "원/인",
    "KRW/person/month": "원/인·월", "KRW/person/year": "원/인·년", "KRW/year": "원/년", "KRW/case/day": "원/건·일",
    "year": "년", "month/year": "개월/년", "ratio/year": "비율/년", "thousand KRW/person": "천원/인",
}


def unit_ko(unit: str | None) -> str:
    return UNITS.get(unit or "", unit or "")


WORDS = {"total": "전체", "male": "남자", "female": "여자", "common": ""}


def clean_name(name: str) -> str:
    """'recipient_count — 2024년 5월말 전국 주민등록인구' → '2024년 5월말 전국 주민등록인구'."""
    name = re.sub(r"^[a-z0-9_:.]+\s*—\s*", "", name or "").strip()
    name = re.sub(r"\b(total|male|female|common)\b", lambda m: WORDS[m[1]], name).strip()
    return name[:60] + ("…" if len(name) > 60 else "")


def as_of_ko(value) -> str:
    text = str(value or "").strip()
    if m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text):
        y, mo, d = map(int, m.groups())
        return f"{y}년 {mo}월말" if d >= 28 else f"{y}년 {mo}월 {d}일"
    if m := re.fullmatch(r"(\d{4})-(\d{2})", text):
        return f"{m[1]}년 {int(m[2])}월"
    if re.fullmatch(r"\d{4}", text):
        return f"{text}년"
    return text


def short_origin(origin: str) -> dict:
    """Split a long provenance line into publisher/document and reference time."""
    origin = origin or ""
    if origin.startswith("원문 "):
        return dict(where=f"의안 {origin[3:]}", as_of="")
    as_of = ""
    if m := re.search(r"\(기준 ([^,)]+)", origin):
        as_of = m[1]
    elif m := re.search(r"(\d{4}(?:-\d{2}(?:-\d{2})?)?) 기준", origin):
        as_of = m[1]
    parts = [p.strip() for p in origin.split(" · ")]
    where = parts[1] if len(parts) > 1 and "기준" in parts[0] else parts[0]
    where = re.sub(r"\s*\(기준 [^)]*\).*", "", where)
    if "」" in where:
        where = where[: where.index("」") + 1]
    where = re.sub(r"^(사용자 입력|근거 없음)\s*[:—-]\s*", r"\1: ", where)
    return dict(where=where[:70] + ("…" if len(where) > 70 else ""), as_of=as_of_ko(as_of))


def by_year(row: dict):
    """A yearly series stored as a plain list → {year: value}, so it is never shown as a range."""
    v = row.get("value")
    if not isinstance(v, list) or len(v) < 2 or not all(isinstance(x, (int, float)) for x in v):
        return v
    m = re.search(r"(\d{4})-(\d{4})", row.get("id", ""))
    if m and int(m[2]) - int(m[1]) + 1 == len(v):
        start = int(m[1])
    elif isinstance(row.get("reference_year"), int):
        start = row["reference_year"]
    else:
        return v
    return {str(start + i): x for i, x in enumerate(v)}
