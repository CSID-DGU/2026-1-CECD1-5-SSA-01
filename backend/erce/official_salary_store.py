"""Official monthly civil-service base salaries, separate from annual staff costs.

The Ministry of Personnel Management tables are monthly *base pay*.  They do
not include allowances, employer contributions, or operating costs and must
not be substituted for ERCE's annual ``salary_by_grade`` evidence.
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from html.parser import HTMLParser
from pathlib import Path

from backend.erce.variable_evidence_store import DEFAULT_VARIABLE_DB

SOURCE_URL_TEMPLATE = "https://www.mpm.go.kr/mpm/info/resultPay/bizSalary/{year}/"
SCHEDULES = {
    "general": ("resultPay_1", "별표 3", "일반직공무원 등"),
    "public_safety": ("resultPay_3", "별표 4", "공안업무 등에 종사하는 공무원"),
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS erce_official_salary_rates (
    year INTEGER NOT NULL,
    schedule TEXT NOT NULL,
    schedule_name TEXT NOT NULL,
    regulation_table TEXT NOT NULL,
    grade INTEGER NOT NULL,
    step INTEGER NOT NULL,
    monthly_base_won INTEGER NOT NULL,
    unit TEXT NOT NULL DEFAULT 'KRW/person/month',
    source_url TEXT NOT NULL,
    PRIMARY KEY (year, schedule, grade, step),
    CHECK (year >= 2000),
    CHECK (grade BETWEEN 1 AND 9),
    CHECK (step BETWEEN 1 AND 40),
    CHECK (monthly_base_won > 0)
);
"""


class _SalaryTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.section = ""
        self.cell_tag: str | None = None
        self.cell_text: list[str] = []
        self.row: list[str] | None = None
        self.headers: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"thead", "tbody"}:
            self.section = tag
        elif tag == "tr" and self.section:
            self.row = []
        elif tag in {"th", "td"} and self.row is not None:
            self.cell_tag = tag
            self.cell_text = []

    def handle_data(self, data: str) -> None:
        if self.cell_tag:
            self.cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == self.cell_tag:
            assert self.row is not None
            self.row.append(" ".join("".join(self.cell_text).split()))
            self.cell_tag = None
        elif tag == "tr" and self.row is not None:
            if self.section == "thead":
                self.headers = self.row
            elif self.section == "tbody":
                self.rows.append(self.row)
            self.row = None
        elif tag == self.section:
            self.section = ""


def parse_official_salary_html(html: str, year: int) -> list[dict]:
    """Read the complete general/public-safety grade-by-step tables from MPM."""
    if f"{year}년 직종별 공무원 봉급표" not in html:
        raise ValueError(f"official salary page year does not match {year}")
    records: list[dict] = []
    for schedule, (section_id, regulation_table, schedule_name) in SCHEDULES.items():
        match = re.search(
            rf'<dt id="{section_id}".*?<table\b[^>]*>(.*?)</table>', html, re.S
        )
        if not match:
            raise ValueError(f"missing official salary schedule: {schedule}")
        parser = _SalaryTableParser()
        parser.feed(match.group(1))
        grades = [int(found.group(1)) for header in parser.headers[1:]
                  if (found := re.search(r"([1-9])급", header))]
        if grades != list(range(1, 10)) or len(parser.rows) != 32:
            raise ValueError(f"unexpected {schedule} salary table shape")
        for row in parser.rows:
            step_match = re.match(r"(\d+)", row[0])
            if not step_match or len(row) != 10:
                raise ValueError(f"invalid {schedule} salary row: {row}")
            step = int(step_match.group(1))
            for grade, raw_value in zip(grades, row[1:], strict=True):
                value = raw_value.replace(",", "").strip()
                if not value:
                    continue  # Blank cells are inapplicable grade/step pairs.
                if not value.isdecimal():
                    raise ValueError(f"invalid salary amount: {raw_value!r}")
                records.append({
                    "year": year, "schedule": schedule, "schedule_name": schedule_name,
                    "regulation_table": regulation_table, "grade": grade, "step": step,
                    "monthly_base_won": int(value), "unit": "KRW/person/month",
                    "source_url": SOURCE_URL_TEMPLATE.format(year=year),
                })
    if len({(r["year"], r["schedule"], r["grade"], r["step"]) for r in records}) != len(records):
        raise ValueError("duplicate official salary rate")
    return records


def save_official_salary_rates(rows: list[dict], db_path: Path = DEFAULT_VARIABLE_DB) -> int:
    if not rows:
        raise ValueError("no salary rates to save")
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as db, db:
        db.executescript(SCHEMA)
        db.executemany("""
            INSERT INTO erce_official_salary_rates
            (year, schedule, schedule_name, regulation_table, grade, step,
             monthly_base_won, unit, source_url)
            VALUES (:year, :schedule, :schedule_name, :regulation_table, :grade,
                    :step, :monthly_base_won, :unit, :source_url)
            ON CONFLICT(year, schedule, grade, step) DO UPDATE SET
                schedule_name=excluded.schedule_name,
                regulation_table=excluded.regulation_table,
                monthly_base_won=excluded.monthly_base_won,
                unit=excluded.unit, source_url=excluded.source_url
        """, rows)
    return len(rows)


def get_official_monthly_salary(
    *, year: int, schedule: str, grade: int, step: int,
    db_path: Path = DEFAULT_VARIABLE_DB,
) -> dict | None:
    """Return a rate only for an exact, explicit schedule/grade/step match."""
    if schedule not in SCHEDULES:
        raise ValueError(f"unknown salary schedule: {schedule}")
    if not Path(db_path).exists():
        return None
    with closing(sqlite3.connect(db_path)) as db:
        db.row_factory = sqlite3.Row
        try:
            row = db.execute("""
                SELECT * FROM erce_official_salary_rates
                WHERE year=? AND schedule=? AND grade=? AND step=?
            """, (year, schedule, grade, step)).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc):
                return None
            raise
    return dict(row) if row else None
