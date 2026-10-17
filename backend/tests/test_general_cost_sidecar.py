from __future__ import annotations

import unittest

from backend.legacy.scripts.build_general_cost_sidecar import (
    classify_component,
    classify_cost_nature,
    formula_readiness,
    infer_canonical_key,
    infer_formula_family,
    load_validation_holdout,
    normalize_value_unit,
)
from pathlib import Path
import tempfile


class GeneralCostSidecarTest(unittest.TestCase):
    def test_validation_holdout_manifest_loads_both_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "manifest.jsonl"
            path.write_text(
                '{"bill_id":"PRC_HOLDOUT","bill_no":"2299999"}\n',
                encoding="utf-8",
            )
            bill_ids, bill_nos = load_validation_holdout(path)
            self.assertEqual(bill_ids, {"PRC_HOLDOUT"})
            self.assertEqual(bill_nos, {"2299999"})

    def test_tax_expenditure_wins_over_equity_word(self) -> None:
        nature, confidence, _ = classify_cost_nature(
            {
                "item_category": "지원금",
                "item_name": "조합 출자금 비과세 적용기한 연장",
            }
        )
        self.assertEqual(nature, "tax_expenditure")
        self.assertEqual(confidence, "high")

    def test_transfer_category_is_not_swallowed_by_cost_composition(self) -> None:
        nature, _, _ = classify_cost_nature(
            {"item_category": "지원금", "item_name": "주거유지지원서비스 지원"},
            variables=[
                {
                    "variable_name": "1인당 서비스 비용",
                    "source_text": "사례관리사 인건비와 운영비를 포함하여 가정",
                }
            ],
        )
        self.assertEqual(nature, "transfers")

    def test_personnel_variable_and_formula_binding(self) -> None:
        item = {"item_category": "인건비", "item_name": "상임위원 보수"}
        nature, _, _ = classify_cost_nature(item)
        component = classify_component(nature, item)
        headcount, _ = infer_canonical_key(
            nature,
            component,
            {"variable_type": "target_count", "variable_name": "증원 인원", "variable_unit": "명"},
        )
        salary, _ = infer_canonical_key(
            nature,
            component,
            {"variable_type": "unit_cost", "variable_name": "1인당 연봉", "variable_unit": "천원"},
        )
        keys = {headcount, salary}
        formula = infer_formula_family(nature, {key for key in keys if key})
        readiness, missing = formula_readiness(formula, {key for key in keys if key})
        self.assertEqual(formula, "PERSONNEL_AVERAGE_V1")
        self.assertEqual(readiness, "ready")
        self.assertEqual(missing, [])

    def test_operation_staff_salary_is_not_mapped_as_headcount(self) -> None:
        key, confidence = infer_canonical_key(
            "personnel",
            "salary",
            {
                "variable_type": "unit_cost",
                "variable_name": "운영인력 1인당 연봉 (2023년 기준)",
                "variable_unit": "원",
            },
        )
        self.assertEqual(key, "salary_per_person")
        self.assertEqual(confidence, "high")
        value, unit, status, _ = normalize_value_unit(key, 80_000_000, "원")
        self.assertEqual(value, 80_000_000)
        self.assertEqual(unit, "KRW/person/year")
        self.assertEqual(status, "normalized")

        headcount_key, _ = infer_canonical_key(
            "personnel",
            "salary",
            {
                "variable_type": "target_count",
                "variable_name": "데이터 입력원 수",
                "variable_unit": "명",
            },
        )
        self.assertEqual(headcount_key, "headcount")

    def test_transfer_variable_normalization(self) -> None:
        key, confidence = infer_canonical_key(
            "transfers",
            "cash_benefit",
            {
                "variable_type": "unit_cost",
                "variable_name": "1인당 지원금액",
                "variable_unit": "만원/명",
            },
        )
        self.assertEqual(key, "benefit_per_recipient")
        self.assertEqual(confidence, "high")
        value, unit, status, flags = normalize_value_unit(key, 30, "만원/명")
        self.assertEqual(value, 300000)
        self.assertEqual(unit, "KRW/person")
        self.assertEqual(status, "normalized")
        self.assertEqual(flags, [])

    def test_aggregate_item_is_not_executable(self) -> None:
        nature, _, reason = classify_cost_nature(
            {"item_category": "사업비", "item_name": "합계"}
        )
        self.assertEqual(nature, "review_required")
        self.assertEqual(reason, "aggregate_row_not_estimable")

    def test_system_maintenance_is_goods_not_salary(self) -> None:
        nature, _, _ = classify_cost_nature(
            {"item_category": "운영비", "item_name": "정보시스템 유지보수"}
        )
        self.assertEqual(nature, "goods_services")


if __name__ == "__main__":
    unittest.main()
