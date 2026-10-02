from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.erce.official_salary_store import (
    get_official_monthly_salary, parse_official_salary_html, save_official_salary_rates,
)


def _page() -> str:
    headers = "".join(f"<th>{grade}급</th>" for grade in range(1, 10))
    rows = "".join(
        "<tr><th>" + str(step) + "<span> 호봉</span></th>"
        + "".join(f"<td>{2_000_000 + grade * 1_000 + step:,}</td>" for grade in range(1, 10))
        + "</tr>" for step in range(1, 33)
    )
    table = f"<table><thead><tr><th>호봉</th>{headers}</tr></thead><tbody>{rows}</tbody></table>"
    return ("2026년 직종별 공무원 봉급표"
            + f'<dt id="resultPay_1"></dt>{table}'
            + f'<dt id="resultPay_3"></dt>{table}')


class OfficialSalaryStoreTest(unittest.TestCase):
    def test_import_and_exact_lookup(self) -> None:
        rows = parse_official_salary_html(_page(), 2026)
        self.assertEqual(len(rows), 576)
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "salary.sqlite3"
            self.assertEqual(save_official_salary_rates(rows, db_path), 576)
            self.assertEqual(save_official_salary_rates(rows, db_path), 576)
            rate = get_official_monthly_salary(
                year=2026, schedule="general", grade=9, step=1, db_path=db_path,
            )
            self.assertIsNotNone(rate)
            self.assertEqual(rate["monthly_base_won"], 2_009_001)
            self.assertEqual(rate["unit"], "KRW/person/month")
            self.assertIsNone(get_official_monthly_salary(
                year=2025, schedule="general", grade=9, step=1, db_path=db_path,
            ))
            self.assertIsNone(get_official_monthly_salary(
                year=2026, schedule="general", grade=9, step=33, db_path=db_path,
            ))

    def test_rejects_wrong_year_and_unknown_schedule(self) -> None:
        with self.assertRaisesRegex(ValueError, "year does not match"):
            parse_official_salary_html(_page(), 2025)
        with self.assertRaisesRegex(ValueError, "unknown salary schedule"):
            get_official_monthly_salary(
                year=2026, schedule="judge", grade=9, step=1,
                db_path=Path("/nonexistent/salary.db"),
            )


if __name__ == "__main__":
    unittest.main()
