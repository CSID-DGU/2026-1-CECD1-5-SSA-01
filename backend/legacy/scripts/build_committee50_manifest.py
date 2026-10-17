"""Build a reproducible manifest for the local 50-case committee dataset.

The manifest deliberately does not extract or expose answer amounts.  It
freezes file identity, prior diagnostic status, and the availability of a
structured missing-input label.  The answer PDFs remain evaluator-only data.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import runpy
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET = ROOT / "backend/generated/위원회_평가셋"
_README_BILL = re.compile(r"^-\s+(\d{7})\s*$", re.MULTILINE)
_RESULT_ROW = re.compile(
    r"^\|\s*(\d+)\s*\|\s*(\d{7})\s*\|.*?\|\s*([^|]+?)\s*\|\s*$",
    re.MULTILINE,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_backfill(dataset_dir: Path) -> dict[str, dict[str, Any]]:
    namespace = runpy.run_path(str(dataset_dir / "missing_inputs_backfill.py"))
    return dict(namespace.get("BACKFILL") or {})


def _read_result_statuses(dataset_dir: Path) -> dict[str, dict[str, Any]]:
    text = (dataset_dir / "test_result.md").read_text(encoding="utf-8")
    rows: dict[str, dict[str, Any]] = {}
    for match in _RESULT_ROW.finditer(text):
        index, bill_no, status = match.groups()
        rows[bill_no] = {"index": int(index), "status": status.strip()}
    return rows


def build_manifest(dataset_dir: Path = DEFAULT_DATASET) -> dict[str, Any]:
    readme = (dataset_dir / "README.md").read_text(encoding="utf-8")
    bill_nos = _README_BILL.findall(readme)
    if len(bill_nos) != len(set(bill_nos)):
        raise ValueError("README contains duplicate bill numbers")

    backfill = _read_backfill(dataset_dir)
    statuses = _read_result_statuses(dataset_dir)
    cases: list[dict[str, Any]] = []
    for position, bill_no in enumerate(bill_nos, start=1):
        case_dir = dataset_dir / bill_no
        source_link = case_dir / "원문.pdf"
        answer_link = case_dir / "정답_비용추계서.pdf"
        source_real = source_link.resolve(strict=False)
        answer_real = answer_link.resolve(strict=False)
        source_exists = source_link.exists()
        answer_exists = answer_link.exists()
        label = backfill.get(bill_no)
        result = statuses.get(bill_no) or {}
        missing_inputs = None if label is None else label.get("missing_inputs")
        cases.append(
            {
                "index": position,
                "bill_no": bill_no,
                "source_pdf": {
                    "link": str(source_link.relative_to(ROOT)),
                    "resolved_path": str(source_real),
                    "exists": source_exists,
                    "size_bytes": source_real.stat().st_size if source_exists else None,
                    "sha256": sha256_file(source_real) if source_exists else None,
                },
                "answer_pdf": {
                    "link": str(answer_link.relative_to(ROOT)),
                    "resolved_path": str(answer_real),
                    "exists": answer_exists,
                    "size_bytes": answer_real.stat().st_size if answer_exists else None,
                    "sha256": sha256_file(answer_real) if answer_exists else None,
                    "access_policy": "evaluator_only",
                },
                "prior_diagnosis_status": result.get("status"),
                "structured_label": label,
                "has_structured_label": label is not None,
                "has_missing_input_details": missing_inputs is not None,
                "needs_structured_label": label is None,
            }
        )

    missing_kinds = Counter(
        item["kind"]
        for case in cases
        for item in ((case.get("structured_label") or {}).get("missing_inputs") or [])
    )
    return {
        "schema_version": "committee50-manifest-v1",
        "dataset_role": "development_and_regression_not_blind_holdout",
        "answer_leakage_policy": "answer PDFs and their amounts must never enter runtime retrieval or inference",
        "dataset_dir": str(dataset_dir.relative_to(ROOT)),
        "summary": {
            "case_count": len(cases),
            "source_pdf_count": sum(bool(case["source_pdf"]["exists"]) for case in cases),
            "answer_pdf_count": sum(bool(case["answer_pdf"]["exists"]) for case in cases),
            "prior_diagnosis_count": sum(case["prior_diagnosis_status"] is not None for case in cases),
            "structured_label_count": sum(bool(case["has_structured_label"]) for case in cases),
            "structured_missing_input_detail_count": sum(
                bool(case["has_missing_input_details"]) for case in cases
            ),
            "missing_kind_distribution": dict(sorted(missing_kinds.items())),
            "needs_structured_label": [
                case["bill_no"] for case in cases if case["needs_structured_label"]
            ],
        },
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = build_manifest(args.dataset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary = manifest["summary"]
    print(
        f"cases={summary['case_count']} source={summary['source_pdf_count']} "
        f"answer={summary['answer_pdf_count']} diagnosis={summary['prior_diagnosis_count']} "
        f"labels={summary['structured_label_count']} output={args.output}"
    )
    if summary["needs_structured_label"]:
        print("needs_structured_label=" + ",".join(summary["needs_structured_label"]))


if __name__ == "__main__":
    main()
