"""Export saved estimates as a read-only static site (works with the server switched off).

  cd frontend && VITE_NABO_STATIC=1 npx vite build --config vite.nabo.config.js --outDir dist-static --base ./
  python3 -m backend.nabo_style.export_static frontend/dist-static

Writes data/runs.json, data/run/{id}.json, data/report/{id}.html and data/pdf/{id}.pdf next to nabo.html.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

from backend.nabo_style.ai_pipeline import compute
from backend.nabo_style.report import build
from backend.nabo_style.web import RUNS, _load_run, _read, ai_case, ai_runs


def export(out: Path) -> int:
    data = out / "data"
    for sub in ("run", "report", "pdf"):
        (data / sub).mkdir(parents=True, exist_ok=True)
    runs = ai_runs()
    (data / "runs.json").write_text(json.dumps(runs, ensure_ascii=False, default=str), encoding="utf-8")
    for r in runs:
        rid = r["run_id"]
        (data / "run" / f"{rid}.json").write_text(json.dumps(_load_run(rid), ensure_ascii=False, default=str),
                                                  encoding="utf-8")
        saved = _read(RUNS / f"{rid}.json")
        case = ai_case(compute(saved["state"], saved.get("overrides")))
        case["ai"]["run_id"] = rid
        html = build(case, saved["state"])
        html = re.sub(r'<div class="bar">.*?</div>', "", html, flags=re.S)  # Word/print need the server or a browser tab
        (data / "report" / f"{rid}.html").write_text(html, encoding="utf-8")
        if (RUNS / f"{rid}.pdf").exists():
            shutil.copy(RUNS / f"{rid}.pdf", data / "pdf" / f"{rid}.pdf")
    return len(runs)


if __name__ == "__main__":
    print(f"exported {export(Path(sys.argv[1]))} estimates")
