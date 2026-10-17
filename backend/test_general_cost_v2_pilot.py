from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from backend.scripts.build_general_cost_v2_pilot import build_database
from backend.scripts.search_general_cost_v2_pilot import search


class GeneralCostV2PilotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.database = Path(cls.temp.name) / "pilot.sqlite3"
        cls.metrics = build_database(cls.database)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def test_schema_integrity_and_holdout_isolation(self) -> None:
        connection = sqlite3.connect(self.database)
        self.assertEqual(connection.execute("pragma integrity_check").fetchone()[0], "ok")
        self.assertEqual(connection.execute("select count(*) from dataset_splits where split!='development'").fetchone()[0], 0)
        self.assertEqual(connection.execute("select count(*) from documents").fetchone()[0], 10)
        self.assertGreater(connection.execute("select count(*) from cost_items").fetchone()[0], 0)
        connection.close()

    def test_every_item_has_formula_and_page_evidence_record(self) -> None:
        connection = sqlite3.connect(self.database)
        item_count = connection.execute("select count(*) from cost_items").fetchone()[0]
        formula_count = connection.execute("select count(distinct item_id) from item_formula_links").fetchone()[0]
        evidence_count = connection.execute("select count(*) from evidence_links where entity_type='item'").fetchone()[0]
        self.assertEqual(item_count, formula_count)
        self.assertEqual(item_count, evidence_count)
        connection.close()

    def test_structured_route_search(self) -> None:
        rows = search(
            self.database,
            "정보시스템 구축 클라우드 운영",
            mechanism="information_system",
            limit=3,
        )
        self.assertTrue(rows)
        self.assertTrue(all(row["mechanism"].startswith("information_system") for row in rows))
        self.assertIn("시스템", rows[0]["item_name"])
        self.assertTrue(rows[0]["evidence"])


if __name__ == "__main__":
    unittest.main()
