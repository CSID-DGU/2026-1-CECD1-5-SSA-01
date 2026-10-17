"""Answer-informed regression; never overwrites the pre-answer first run."""
import copy
import dataclasses
import json
from pathlib import Path

from backend.erce.engine import estimate_routed_item
from backend.erce.regional_child_allowance_evidence import regional_child_allowance_rows
from backend.erce.web_bridge import calculate_erce_web_item


def run_regression():
    first = json.loads(Path("docs/erce/first_runs/ERCE_FIRST_RUN_2210913.json").read_text())
    basic = estimate_routed_item(first["basic"]["payload"])
    regional = []
    web_checks = []
    for item, row in zip(first["regional"], regional_child_allowance_rows()):
        p = copy.deepcopy(item["payload"])
        p.update(cutoff_date="2026-10-04", evidence_mode="development_review",
            selected_evidence_keys=[row["evidence_key"]],
            child_population_geography=row["child_population_geography"],
            population_age_min=row["population_age_min"], population_age_max=row["population_age_max"],
            recipient_population_basis=row["recipient_population_basis"],
            evidence_selection_reasons={row["evidence_key"]:"동일 역사적 법안 정답의 지역·연령별 전망값 사후검증"})
        result = estimate_routed_item(p)
        regional.append(dict(payload=p, result=dataclasses.asdict(result)))
        # Synthetic reuse checks public bridge wiring; it is not a new real bill.
        web = calculate_erce_web_item({**p, "bill_no":"SYNTHETIC_REGIONAL_REUSE",
            "evidence_mode":"holdout"})
        web_checks.append(dict(synthetic=True, status=web["status"],
            annual_amounts_thousand=web["annualAmountsThousand"]))
    regional_total = sum(sum(x["result"]["annual_amounts_thousand"]) for x in regional)
    total = sum(basic.annual_amounts_thousand) + regional_total
    return dict(bill_no="2210913", post_answer_regression=True, independent_evaluation=False,
        basic=dataclasses.asdict(basic), regional=regional, synthetic_web_checks=web_checks,
        required_variables_filled=9, required_variable_count=9,
        regional_total_thousand=regional_total, total_thousand=total,
        gold_display_total_thousand=61000000000,
        display_total_difference_percent=abs(total-61000000000)/61000000000*100,
        gold_operand_total_thousand=60890413586.4,
        limitation="정답 열람 후 회귀검증. 지역인원은 정답 전망값 재사용이며 독립예측 성과 아님. 기본수당은 기존 수동DB매핑 유지. 상품권 행정비는 별도 미확정")


if __name__ == "__main__":
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
