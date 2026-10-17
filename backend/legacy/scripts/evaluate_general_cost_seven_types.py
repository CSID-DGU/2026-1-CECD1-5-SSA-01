"""Run one leakage-controlled precedent-selection case per fiscal nature."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from backend.legacy.engines.general_cost_precedent_selector import (
    DEFAULT_SIDECAR_DIR,
    GeneralCostEvidenceStore,
    select_precedent,
    target_from_dict,
)
from backend.erce_web.general_cost_resolver import request_from_dict, resolve_general_cost


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE = ROOT / "backend/legacy/fixtures/general_cost_seven_type_holdout.json"
DEFAULT_OUTPUT = ROOT / "backend/generated/general_cost_seven_type_benchmark"


def _load_target(case: dict[str, Any]) -> dict[str, Any]:
    if case.get("target"):
        return dict(case["target"])
    path = ROOT / str(case["target_path"])
    return json.loads(path.read_text(encoding="utf-8"))


def _ape(predicted: int, official: int) -> float:
    return round(abs(predicted - official) / max(abs(official), 1) * 100, 2)


def _status(decision: str, predicted: int | None, ape: float | None) -> str:
    if decision != "exact_precedent_candidate" or predicted is None:
        return "safe_hold"
    if ape is not None and ape <= 10:
        return "amount_correct"
    if ape is not None and ape <= 20:
        return "amount_acceptable"
    return "amount_incorrect"


def evaluate(
    fixture: Path = DEFAULT_FIXTURE,
    sidecar_dir: Path = DEFAULT_SIDECAR_DIR,
) -> dict[str, Any]:
    config = json.loads(fixture.read_text(encoding="utf-8"))
    store = GeneralCostEvidenceStore(sidecar_dir)
    rows: list[dict[str, Any]] = []
    for case in config["cases"]:
        target_payload = _load_target(case)
        target = target_from_dict(target_payload)
        selection = select_precedent(target, store=store, top_k=5)
        predicted: int | None = None
        resolution_status: str | None = None
        missing_variables: list[str] = []
        if selection.resolver_request is not None:
            resolution = resolve_general_cost(
                request_from_dict(selection.resolver_request)
            )
            resolution_status = resolution.status
            missing_variables = list(resolution.missing_variables)
            if resolution.status == "computed_review":
                first = resolution.annual_amounts_thousand[0]
                predicted = int(first * 1_000) if first is not None else None
        official = int(case["gold"]["annual_representative_won"])
        error = _ape(predicted, official) if predicted is not None else None
        rows.append(
            {
                "case_id": case["case_id"],
                "label": case["label"],
                "evaluation_mode": case["evaluation_mode"],
                "target_bill_no": target.bill_no,
                "target_item": target.item_name,
                "decision": selection.decision,
                "selected_bill_no": selection.selected.bill_no if selection.selected else None,
                "selected_item": selection.selected.item_name if selection.selected else None,
                "formula_key": selection.formula_key,
                "formula_source": selection.formula_source,
                "resolution_status": resolution_status,
                "missing_variables": missing_variables,
                "predicted_annual_won": predicted,
                "official_annual_representative_won": official,
                "absolute_percentage_error": error,
                "evaluation": _status(selection.decision, predicted, error),
                "warnings": list(selection.warnings),
                "top_candidates": [asdict(row) for row in selection.candidates],
            }
        )
    auto = [row for row in rows if row["predicted_annual_won"] is not None]
    correct = [row for row in auto if row["evaluation"] in {"amount_correct", "amount_acceptable"}]
    wrong = [row for row in auto if row["evaluation"] == "amount_incorrect"]
    held = [row for row in rows if row["evaluation"] == "safe_hold"]
    return {
        "benchmark_version": config["benchmark_version"],
        "summary": {
            "cases": len(rows),
            "automatic_predictions": len(auto),
            "correct_or_acceptable_predictions": len(correct),
            "incorrect_predictions": len(wrong),
            "safe_holds": len(held),
            "coverage_percent": round(len(auto) / max(len(rows), 1) * 100, 1),
        },
        "cases": rows,
    }


def _won(value: int | None) -> str:
    return "-" if value is None else f"{value:,}원"


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 범용 비용유형 7종 선례 선택기 평가",
        "",
        (
            f"자동 추계 {summary['automatic_predictions']}/7, "
            f"허용오차 내 {summary['correct_or_acceptable_predictions']}건, "
            f"오추계 {summary['incorrect_predictions']}건, "
            f"안전 보류 {summary['safe_holds']}건"
        ),
        "",
        "| 유형 | 대상 | 판단 | 선택 선례 | 선택 산식 | 부족 변수 | 예측 연액 | 공식 대표연액 | APE |",
        "|---|---|---|---|---|---|---:|---:|---:|",
    ]
    for row in report["cases"]:
        ape = "-" if row["absolute_percentage_error"] is None else f"{row['absolute_percentage_error']:.2f}%"
        lines.append(
            "| {label} | {bill} | {decision} | {selected} | {formula} | {missing} | {predicted} | {official} | {ape} |".format(
                label=row["label"],
                bill=row["target_bill_no"],
                decision=row["decision"],
                selected=row["selected_bill_no"] or "-",
                formula=row["formula_key"] or "-",
                missing=", ".join(row["missing_variables"]) or "-",
                predicted=_won(row["predicted_annual_won"]),
                official=_won(row["official_annual_representative_won"]),
                ape=ape,
            )
        )
    lines.extend(
        [
            "",
            "물건비는 법안 원문 기반 엄격 홀드아웃이다. 나머지 6건은 대상 의안 전체를 후보에서 제외하고 대상 금액·근거를 선택 후에만 여는 leave-one-bill-out 평가다.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--sidecar-dir", type=Path, default=DEFAULT_SIDECAR_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    report = evaluate(args.fixture, args.sidecar_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "report.json"
    md_path = args.output_dir / "report.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"report_json={json_path}")
    print(f"report_md={md_path}")


if __name__ == "__main__":
    main()
