"""Build source-only inputs for the isolated hierarchical evidence engine."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

from backend.erce_web.article_extraction_engine import extract_pdf_text, split_articles_regex
from backend.legacy.scripts.build_committee50_manifest import build_manifest
from backend.scripts.evaluate_committee_precedent_routes import _load_metadata


ROOT = Path(__file__).resolve().parents[3]
TARGET_LABELS = ROOT / "backend/legacy/fixtures/committee50_target_terms.json"


def _compact(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value or "")


def build_cases() -> list[dict[str, Any]]:
    manifest = build_manifest()
    labels = json.loads(TARGET_LABELS.read_text(encoding="utf-8"))["cases"]
    metadata = _load_metadata()
    bill_nos = [case["bill_no"] for case in manifest["cases"]]
    if set(labels) != set(bill_nos):
        missing = sorted(set(bill_nos) - set(labels))
        extra = sorted(set(labels) - set(bill_nos))
        raise ValueError(f"target label mismatch missing={missing} extra={extra}")

    output: list[dict[str, Any]] = []
    for entry in manifest["cases"]:
        bill_no = entry["bill_no"]
        source = Path(entry["source_pdf"]["resolved_path"])
        terms = labels[bill_no]
        compact_terms = [_compact(term) for term in terms]
        text = extract_pdf_text(source.read_bytes())
        articles = split_articles_regex(text)
        anchor_indices: set[int] = set()
        for index, article in enumerate(articles):
            rendered = (
                f"{article.get('no', '')}({article.get('title', '')}) "
                f"{article.get('text', '')}"
            ).strip()
            compact = _compact(rendered)
            if any(term and term in compact for term in compact_terms):
                anchor_indices.add(index)

        # Committee statutes usually define the full name in the installation
        # article, then use only the short alias in the following composition
        # and operation articles. Include a bounded forward window so those
        # operands are not lost merely because the full name is absent.
        selected_indices: set[int] = set()
        for index in anchor_indices:
            selected_indices.update(range(index, min(len(articles), index + 5)))
        passages = [
            (
                f"{articles[index].get('no', '')}({articles[index].get('title', '')}) "
                f"{articles[index].get('text', '')}"
            ).strip()[:4000]
            for index in sorted(selected_indices)
        ]
        meta = metadata.get(bill_no) or {}
        propose_date = str(meta.get("propose_date") or "")
        if not propose_date:
            raise ValueError(f"missing propose_date: {bill_no}")
        output.append(
            {
                "bill_no": bill_no,
                "bill_name": str(meta.get("bill_name") or ""),
                "propose_date": propose_date,
                "cutoff_date": propose_date,
                "source_pdf": entry["source_pdf"]["resolved_path"],
                "source_pdf_sha256": entry["source_pdf"]["sha256"],
                "target_terms": terms,
                # Diagnostic only.  The resolver must construct its own
                # bounded passages from source_pdf + target_terms; injecting
                # this wider window changes retrieval behavior and can leak
                # facts between adjacent cost events.
                "source_validation_passages": passages,
                "evaluation_only_target_label": True,
            }
        )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = build_cases()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    no_passage = [
        case["bill_no"] for case in cases if not case["source_validation_passages"]
    ]
    print(f"cases={len(cases)} no_target_passage={len(no_passage)} output={args.output}")
    if no_passage:
        print("no_target_passage=" + ",".join(no_passage))


if __name__ == "__main__":
    main()
