"""Post-answer 2209533 scenario regression; no API calls or holdout evaluation."""
import argparse
import json
from pathlib import Path

from backend.erce.scholarship_cap_evidence import reviewed_scholarship_point_estimate
from backend.erce.variable_evidence_store import DEFAULT_VARIABLE_DB


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_VARIABLE_DB)
    parser.add_argument("--output", type=Path,
        default=Path("docs/erce/cases/ERCE_REGRESSION_2209533_COMPLETE.json"))
    args = parser.parse_args()
    scenarios = [reviewed_scholarship_point_estimate(args.db, policy_scenario=key)
        for key in ("answer_table_reference", "all_second_full_tuition", "third_child_schedule_extension")]
    report = dict(evaluated_at="2026-10-03", independent_evaluation=False,
                  description="정답 확인 후 보강한 대학 구성비 대리 가정으로 전체 일부추계 범위 재계산",
                  scenarios=scenarios)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n",
                           encoding="utf-8")
    print(json.dumps(dict(output=str(args.output),
        totals_thousand={s["policy_scenario"]:s["total_thousand"] for s in scenarios},
        reference_total_error_percent=scenarios[0]["total_absolute_error_percent"]),
        ensure_ascii=False))


if __name__ == "__main__":
    main()
