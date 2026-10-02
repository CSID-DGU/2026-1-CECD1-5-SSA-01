"""Export/import the public ERCE evidence and official salary tables only."""
import argparse
import json
import sqlite3
from pathlib import Path

from backend.erce.variable_evidence_store import DEFAULT_VARIABLE_DB, save_variable_rows
from backend.erce.official_salary_store import save_official_salary_rates

DEFAULT_SNAPSHOT = Path(__file__).resolve().parents[1] / "data/reference_snapshot.json"


def export_snapshot(db_path, snapshot_path):
    with sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        variables = [json.loads(row[0]) for row in db.execute(
            "SELECT row_json FROM erce_variable_evidence ORDER BY evidence_key")]
        salaries = [dict(row) for row in db.execute(
            "SELECT * FROM erce_official_salary_rates ORDER BY year,schedule,grade,step")]
    snapshot_path = Path(snapshot_path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps({"version": 1, "variables": variables,
                                        "official_salary_rates": salaries}, ensure_ascii=False,
                                       indent=2) + "\n", encoding="utf-8")
    return len(variables), len(salaries)


def import_snapshot(db_path, snapshot_path):
    data = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise ValueError("unsupported ERCE snapshot version")
    return (save_variable_rows(data["variables"], Path(db_path)),
            save_official_salary_rates(data["official_salary_rates"], Path(db_path)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["export", "import"])
    parser.add_argument("--db", type=Path, default=DEFAULT_VARIABLE_DB)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    args = parser.parse_args()
    run = export_snapshot if args.action == "export" else import_snapshot
    print("ERCE variables / official salary rows:", run(args.db, args.snapshot))
