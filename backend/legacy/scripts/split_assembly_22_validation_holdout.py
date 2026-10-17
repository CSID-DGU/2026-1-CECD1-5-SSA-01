"""Freeze a diverse document-level validation holdout before DB development.

The original collection manifest remains immutable.  This script creates a
development manifest with the held-out bills removed and, with ``--apply``,
moves the corresponding ``by_bill`` directories into a separate validation
root.  Selection is deterministic so the split cannot drift while rules are
being tuned.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = ROOT / "backend/generated/assembly_22_pdfs"
DEFAULT_MANIFEST = SOURCE_ROOT / "manifest.jsonl"
DEFAULT_DEVELOPMENT_MANIFEST = SOURCE_ROOT / "development_manifest.jsonl"
DEFAULT_HOLDOUT_ROOT = ROOT / "backend/generated/assembly_22_validation_holdout_v1"
DEFAULT_STRUCTURED_SEED = ROOT / "backend/generated/assembly_rag_seed_22_ce"
DEFAULT_SIZE = 100
SPLIT_VERSION = "assembly-22-validation-holdout-v1"
SELECTION_SEED = "2026-09-27-general-cost-validation-v1"

# Rare fiscal natures are deliberately oversampled.  ``분류검토`` remains in
# the split so routing failures are measured instead of silently discarded.
CATEGORY_QUOTAS = {
    "물건비": 25,
    "이전지출": 20,
    "인건비": 15,
    "조세감면": 15,
    "세외수입감소": 8,
    "자본지출": 6,
    "출자출연": 6,
    "분류검토": 5,
}
FORCED_BILL_NOS = {
    "2215482", "2216681", "2217750", "2218721", "2219945",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _stable_rank(row: dict[str, Any]) -> str:
    payload = f"{SELECTION_SEED}|{row.get('bill_id')}|{row.get('bill_no')}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _choose_diverse(
    candidates: list[dict[str, Any]],
    count: int,
    selected_ids: set[str],
) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    committee_counts: Counter[str] = Counter()
    year_counts: Counter[str] = Counter()
    remaining = [
        row for row in candidates
        if str(row.get("bill_id") or "") not in selected_ids
    ]
    while remaining and len(chosen) < count:
        row = min(
            remaining,
            key=lambda value: (
                committee_counts[str(value.get("committee") or "")],
                year_counts[str(value.get("propose_date") or "")[:4]],
                _stable_rank(value),
            ),
        )
        remaining.remove(row)
        chosen.append(row)
        selected_ids.add(str(row.get("bill_id") or ""))
        committee_counts[str(row.get("committee") or "")] += 1
        year_counts[str(row.get("propose_date") or "")[:4]] += 1
    return chosen


def select_holdout(rows: list[dict[str, Any]], size: int = DEFAULT_SIZE) -> list[dict[str, Any]]:
    complete = [
        row for row in rows
        if row.get("status") == "complete"
        and row.get("bill_id")
        and row.get("bill_no")
    ]
    by_bill_no = {str(row["bill_no"]): row for row in complete}
    missing_forced = sorted(FORCED_BILL_NOS - set(by_bill_no))
    if missing_forced:
        raise ValueError(f"forced validation bills missing: {missing_forced}")

    selected = [by_bill_no[bill_no] for bill_no in sorted(FORCED_BILL_NOS)]
    selected_ids = {str(row["bill_id"]) for row in selected}
    assigned = Counter(str(row.get("primary_category") or "분류검토") for row in selected)

    for category, quota in CATEGORY_QUOTAS.items():
        need = max(0, quota - assigned[category])
        candidates = [
            row for row in complete
            if str(row.get("primary_category") or "분류검토") == category
        ]
        additions = _choose_diverse(candidates, need, selected_ids)
        selected.extend(additions)
        assigned[category] += len(additions)

    if len(selected) < size:
        additions = _choose_diverse(complete, size - len(selected), selected_ids)
        selected.extend(additions)
    if len(selected) != size:
        raise ValueError(f"unable to create {size}-document holdout: {len(selected)}")
    return sorted(selected, key=lambda row: str(row.get("bill_no") or ""))


def _row_bill_identity(row: dict[str, Any]) -> tuple[str, str]:
    bill_id = str(row.get("bill_id") or row.get("billId") or "")
    bill_no = str(row.get("bill_no") or row.get("billNo") or "")
    if not bill_id:
        for key in (
            "struct_id", "item_id", "chunkId", "documentId", "source_item_key"
        ):
            value = str(row.get(key) or "")
            if value.startswith("PRC_"):
                bill_id = value.split(":", 1)[0]
                break
    return bill_id, bill_no


def quarantine_structured_seed(
    *,
    seed_dir: Path,
    holdout_root: Path,
    holdout: list[dict[str, Any]],
) -> dict[str, int]:
    """Remove held-out rows from the development seed without deleting them.

    Quarantined files deliberately end in ``.jsonl.holdout`` so recursive
    development loaders that glob ``*.jsonl`` cannot ingest validation gold.
    """
    holdout_ids = {str(row.get("bill_id") or "") for row in holdout}
    holdout_nos = {str(row.get("bill_no") or "") for row in holdout}
    quarantine_dir = holdout_root / "quarantined_structured_seed"
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for source in sorted(seed_dir.glob("*.jsonl")):
        destination = quarantine_dir / f"{source.name}.holdout"
        if destination.exists():
            counts[source.name] = sum(
                1 for line in destination.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
            continue
        development_lines: list[str] = []
        holdout_lines: list[str] = []
        for line in source.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            bill_id, bill_no = _row_bill_identity(row)
            if bill_id in holdout_ids or bill_no in holdout_nos:
                holdout_lines.append(line)
            else:
                development_lines.append(line)
        temporary = source.with_suffix(source.suffix + ".development_tmp")
        temporary.write_text(
            "\n".join(development_lines) + ("\n" if development_lines else ""),
            encoding="utf-8",
        )
        temporary.replace(source)
        destination.write_text(
            "\n".join(holdout_lines) + ("\n" if holdout_lines else ""),
            encoding="utf-8",
        )
        counts[source.name] = len(holdout_lines)
    return counts


def split_files(
    *,
    manifest: Path,
    development_manifest: Path,
    holdout_root: Path,
    structured_seed: Path,
    size: int,
    apply: bool,
) -> dict[str, Any]:
    rows = read_jsonl(manifest)
    holdout = select_holdout(rows, size)
    holdout_ids = {str(row["bill_id"]) for row in holdout}
    development = [row for row in rows if str(row.get("bill_id") or "") not in holdout_ids]

    source_by_bill = manifest.parent / "by_bill"
    destination_by_bill = holdout_root / "by_bill"
    missing_directories: list[str] = []
    for row in holdout:
        bill_no = str(row["bill_no"])
        source = source_by_bill / bill_no
        destination = destination_by_bill / bill_no
        if not source.exists() and not destination.exists():
            missing_directories.append(bill_no)
    if missing_directories:
        raise FileNotFoundError(f"holdout bill directories missing: {missing_directories}")

    summary: dict[str, Any] = {
        "split_version": SPLIT_VERSION,
        "selection_seed": SELECTION_SEED,
        "holdout_documents": len(holdout),
        "development_manifest_rows": len(development),
        "primary_category": dict(Counter(
            str(row.get("primary_category") or "분류검토") for row in holdout
        )),
        "committees": len({str(row.get("committee") or "") for row in holdout}),
        "forced_bill_nos": sorted(FORCED_BILL_NOS),
        "files_moved": bool(apply),
        "quarantined_seed_rows": {},
    }
    if not apply:
        return summary

    holdout_root.mkdir(parents=True, exist_ok=True)
    destination_by_bill.mkdir(parents=True, exist_ok=True)
    for row in holdout:
        bill_no = str(row["bill_no"])
        source = source_by_bill / bill_no
        destination = destination_by_bill / bill_no
        if destination.exists():
            if source.exists():
                raise FileExistsError(f"both source and destination exist: {bill_no}")
            continue
        shutil.move(str(source), str(destination))

    summary["quarantined_seed_rows"] = quarantine_structured_seed(
        seed_dir=structured_seed,
        holdout_root=holdout_root,
        holdout=holdout,
    )

    write_jsonl(holdout_root / "manifest.jsonl", holdout)
    write_jsonl(development_manifest, development)
    (holdout_root / "split_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--development-manifest", type=Path, default=DEFAULT_DEVELOPMENT_MANIFEST
    )
    parser.add_argument("--holdout-root", type=Path, default=DEFAULT_HOLDOUT_ROOT)
    parser.add_argument("--structured-seed", type=Path, default=DEFAULT_STRUCTURED_SEED)
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    summary = split_files(
        manifest=args.manifest,
        development_manifest=args.development_manifest,
        holdout_root=args.holdout_root,
        structured_seed=args.structured_seed,
        size=args.size,
        apply=args.apply,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
