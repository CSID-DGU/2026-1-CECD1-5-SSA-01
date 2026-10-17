"""Build a general-purpose cost-estimation evidence sidecar.

The existing TAG JSONL files remain the immutable raw layer.  This script
normalizes their cost items, variables and observed yearly amounts into the
same profile/evidence shape used by the organization resolver, but extends it
to the seven broad fiscal natures used by the top-level router.

It also writes document-level profiles for every locally collected 22nd
Assembly cost-estimate pair.  A document profile is not treated as an
item-level extraction: unstructured documents remain explicitly queued.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "backend/generated/assembly_22_pdfs/development_manifest.jsonl"
DEFAULT_VALIDATION_MANIFEST = (
    ROOT / "backend/generated/assembly_22_validation_holdout_v1/manifest.jsonl"
)
DEFAULT_SEED_DIRS = (
    ROOT / "backend/generated/assembly_rag_seed",
    ROOT / "backend/generated/assembly_rag_seed_22_ce",
)
DEFAULT_OUTPUT_DIR = ROOT / "backend/generated/general_cost_sidecar_v1"

SCHEMA_VERSION = "general-cost-sidecar-v1"
CLASSIFIER_VERSION = "general-cost-nature-rules-v1"
MAPPER_VERSION = "general-cost-variable-mapper-v1"

_REPLY_DATE_RE = re.compile(
    r"회답일\s*(?P<year>20\d{2})\s*[.년]\s*"
    r"(?P<month>\d{1,2})\s*[.월]\s*(?P<day>\d{1,2})"
)

COST_NATURE_LABELS = {
    "personnel": "인건비",
    "goods_services": "물건비",
    "transfers": "이전지출",
    "capital": "자본지출",
    "tax_expenditure": "조세감면",
    "non_tax_revenue_loss": "세외수입감소",
    "equity_contribution": "출자출연",
    "review_required": "분류검토",
}
LABEL_TO_COST_NATURE = {label: key for key, label in COST_NATURE_LABELS.items()}


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _number(value: Any) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def stable_key(prefix: str, *parts: Any) -> str:
    payload = "|".join(_compact(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL: {path}:{line_number}") from exc
            if isinstance(value, dict):
                yield value


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False) + "\n")


def load_validation_holdout(path: Path) -> tuple[set[str], set[str]]:
    bill_ids: set[str] = set()
    bill_nos: set[str] = set()
    for row in read_jsonl(path):
        bill_id = str(row.get("bill_id") or "")
        bill_no = str(row.get("bill_no") or "")
        if bill_id:
            bill_ids.add(bill_id)
        if bill_no:
            bill_nos.add(bill_no)
    return bill_ids, bill_nos


_TAX_RE = re.compile(
    r"조세|세액|세율|세수|과세|소득세|법인세|부가가치세|양도소득세|"
    r"상속세|증여세|관세|취득세|재산세|종합부동산세|공제|감면|비과세"
)
_EXPLICIT_TAX_EXPENDITURE_RE = re.compile(
    r"세액공제|소득공제|비과세|과세특례|영세율|조세특례|세율인하|"
    r"세금감면|조세감면|감면적용기한|면제적용기한"
)
_NON_TAX_RE = re.compile(
    r"수수료|사용료|부담금|과태료|과징금|벌금|변상금|입장료|통행료|"
    r"세외수입|국유재산.*대부료"
)
_LOSS_RE = re.compile(r"감면|면제|인하|폐지|감소|손실|미징수|유예")
_EQUITY_RE = re.compile(r"출자금|출연금|정부출자|정부출연|기금출연|자본금출자|현물출자")
_PERSONNEL_RE = re.compile(
    r"인건비|봉급|연봉|기관부담|사용자부담|신규채용|증원|"
    r"정원|직급|상임위원|비서실인력|공무원.*(?:인건비|보수|봉급|증원|정원)"
)
_CAPITAL_RE = re.compile(
    r"건설|공사비|시설비|설계비|감리비|토지|부지|청사|건축|증축|개축|"
    r"장비구입|장비도입|자산취득|매입비|구축공사"
)
_TRANSFER_RE = re.compile(
    r"지원금|보조금|급여지급|연금|수당지급|장학금|바우처|이용권|보험급여|"
    r"손실보상|피해보상|위로금|융자지원|이차보전|현금지원|생계비|의료비지원"
)
_AGGREGATE_RE = re.compile(r"^(합계|총계|총합계|추가재정소요|재정소요합계)$")


def classify_cost_nature(
    item: Mapping[str, Any],
    *,
    variables: Iterable[Mapping[str, Any]] = (),
    amounts: Iterable[Mapping[str, Any]] = (),
    document_natures: Iterable[str] = (),
) -> tuple[str, str, str]:
    """Return cost nature, confidence and an auditable rule reason."""
    category = _compact(item.get("item_category"))
    item_name = _compact(item.get("item_name"))
    blob = " ".join(
        str(value or "")
        for value in (
            item.get("item_name"),
            item.get("item_category"),
            item.get("trigger_ref"),
            " ".join(str(v.get("variable_name") or "") for v in variables),
            " ".join(str(v.get("source_text") or "") for v in variables),
            " ".join(str(a.get("formula_text") or "") for a in amounts),
        )
    )
    compact = _compact(blob)

    if _AGGREGATE_RE.match(item_name):
        return "review_required", "high", "aggregate_row_not_estimable"
    if _EXPLICIT_TAX_EXPENDITURE_RE.search(compact) or (
        _TAX_RE.search(compact) and _LOSS_RE.search(compact)
    ):
        return "tax_expenditure", "high", "tax_term_with_reduction"
    if _NON_TAX_RE.search(compact) and _LOSS_RE.search(compact):
        return "non_tax_revenue_loss", "high", "non_tax_charge_with_reduction"
    if _EQUITY_RE.search(compact):
        return "equity_contribution", "high", "explicit_equity_or_contribution"
    if category in {"지원금", "복지비"}:
        return "transfers", "high", "transfer_category"
    if category == "인건비" or (
        _PERSONNEL_RE.search(item_name)
        and not re.search(r"유지보수|보수공사|시설보수", item_name)
    ):
        return "personnel", "high", "personnel_category_or_term"
    if _CAPITAL_RE.search(compact):
        return "capital", "high", "capital_asset_or_construction_term"
    if category in {"운영비", "위탁비"}:
        return "goods_services", "high", "goods_service_category"
    if _TRANSFER_RE.search(item_name):
        return "transfers", "high", "transfer_category_or_term"

    natures = [value for value in document_natures if value != "review_required"]
    if len(set(natures)) == 1:
        return natures[0], "medium", "single_document_nature_fallback"
    if category == "사업비":
        return "goods_services", "medium", "generic_project_cost_fallback"
    return "review_required", "low", "insufficient_item_signal"


_COMPONENT_RULES: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    "personnel": (
        ("employer_contribution", re.compile(r"기관부담|사용자부담")),
        ("basic_expense", re.compile(r"기본경비|행정운영경비")),
        ("asset", re.compile(r"자산취득|비품|집기")),
        ("salary", re.compile(r"인건비|보수|봉급|연봉|급여|증원|신규채용|정원|직급")),
    ),
    "goods_services": (
        ("research_survey", re.compile(r"연구|조사|실태|용역|기본계획")),
        ("information_system", re.compile(r"정보시스템|전산|플랫폼|데이터베이스|소프트웨어|시스템구축")),
        ("education_publicity", re.compile(r"교육|훈련|홍보|캠페인|인식개선")),
        ("event_meeting", re.compile(r"행사|회의|위원회|세미나|박람회|포럼")),
        ("rental_operation", re.compile(r"임차|임대|관리비|운영비|유지보수")),
        ("commissioned_service", re.compile(r"위탁|대행")),
    ),
    "transfers": (
        ("compensation", re.compile(r"보상|배상|위로금")),
        ("insurance_pension", re.compile(r"보험|연금")),
        ("voucher_service", re.compile(r"바우처|이용권|서비스지원")),
        ("subsidy", re.compile(r"보조금|지원금|출연금")),
        ("cash_benefit", re.compile(r"급여|수당|장학금|생계비|의료비|지급")),
    ),
    "capital": (
        ("land_acquisition", re.compile(r"토지|부지|매입")),
        ("design_supervision", re.compile(r"설계|감리")),
        ("construction", re.compile(r"건설|공사|건축|증축|개축|시설")),
        ("equipment_asset", re.compile(r"장비|자산취득|비품|기기")),
    ),
    "tax_expenditure": (
        ("tax_credit_deduction", re.compile(r"세액공제|소득공제|공제")),
        ("rate_reduction", re.compile(r"세율|감면율")),
        ("exemption_extension", re.compile(r"적용기한|연장|면제|비과세")),
        ("tax_base_change", re.compile(r"과세표준|과세대상")),
    ),
    "non_tax_revenue_loss": (
        ("fee_reduction", re.compile(r"수수료|사용료|입장료|통행료")),
        ("charge_reduction", re.compile(r"부담금")),
        ("penalty_reduction", re.compile(r"과태료|과징금|벌금|변상금")),
    ),
    "equity_contribution": (
        ("equity_investment", re.compile(r"출자|자본금")),
        ("fund_contribution", re.compile(r"기금.*출연|출연금")),
    ),
}


def classify_component(cost_nature: str, item: Mapping[str, Any]) -> str:
    blob = _compact(
        f"{item.get('item_name', '')} {item.get('item_category', '')} "
        f"{item.get('trigger_ref', '')}"
    )
    for component, pattern in _COMPONENT_RULES.get(cost_nature, ()):
        if pattern.search(blob):
            return component
    return {
        "personnel": "salary",
        "goods_services": "other_goods_service",
        "transfers": "other_transfer",
        "capital": "other_capital",
        "tax_expenditure": "other_tax_expenditure",
        "non_tax_revenue_loss": "other_non_tax_revenue_loss",
        "equity_contribution": "other_equity_contribution",
    }.get(cost_nature, "review_required")


_YEAR_RE = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


def infer_canonical_key(
    cost_nature: str,
    component: str,
    variable: Mapping[str, Any],
) -> tuple[str | None, str]:
    variable_type = _compact(variable.get("variable_type"))
    name = _compact(variable.get("variable_name"))
    unit = _compact(variable.get("variable_unit"))

    common_rules: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("first_year_fraction", re.compile(r"첫해.*(?:개월|월분|적용비율)|시행연도.*비율")),
        ("start_year", re.compile(r"시행연도|발생연도|지급개시연도|착수연도|시작연도")),
        ("duration", re.compile(r"기간|존속|운영기간|적용기한|연장기간")),
        ("growth_rate", re.compile(r"증가율|상승률|인상률|물가|임금상승")),
        ("participation_rate", re.compile(r"참여율|신청률|수급률|이용률|집행률|선정률")),
        ("payments_per_year", re.compile(r"지급횟수|연간지급|회/년|월수")),
        ("recurrence_interval_years", re.compile(r"주기|매\d+년|년마다")),
        ("frequency_per_year", re.compile(r"연간.*횟수|수행빈도|개최횟수|실시횟수|회수")),
    )
    for key, pattern in common_rules:
        if pattern.search(name) or (key == "frequency_per_year" and unit == "회/년"):
            return key, "high"

    rules: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
        "personnel": (
            ("employer_contribution_rate", re.compile(r"기관부담.*(?:률|요율)|사용자부담.*(?:률|요율)")),
            ("basic_expense_ratio", re.compile(r"기본경비.*(?:률|비율)|인건비대비기본경비")),
            ("headcount_by_grade", re.compile(r"직급별.*(?:인원|정원)|계급별.*(?:인원|정원)")),
            ("salary_by_grade", re.compile(r"직급별.*(?:보수|봉급|인건비)|계급별.*(?:보수|봉급)|[1-9]급.*(?:보수|봉급|인건비)")),
            ("salary_per_person", re.compile(r"1인당.*(?:보수|봉급|인건비|연봉)|연봉|월보수|(?:팀장|팀원|전담인력).*인건비")),
            ("headcount", re.compile(
                r"인원|인력|정원|채용|증원|직원수|공무원수|"
                r"(?:입력원|상담원|운영요원).*\s*수"
            )),
            ("annual_salary_amount", re.compile(r"보수총액|인건비총액|연간인건비")),
            ("asset_unit_price_per_person", re.compile(r"1인당.*자산|자산.*단가")),
        ),
        "goods_services": (
            ("service_quantity", re.compile(r"수량|대상기관|대상시설|사업개수|과업수")),
            ("service_unit_cost", re.compile(r"용역.*단가|사업.*단가|회당.*비용|건당.*비용|비용단가")),
            ("annual_goods_amount", re.compile(r"연간.*(?:운영비|사업비|용역비)|연구용역비용")),
        ),
        "transfers": (
            ("recipient_count", re.compile(r"대상자|필요대상|수급자|수혜자|지원인원|지원대상|가구수|학생수|기업수")),
            ("benefit_per_recipient", re.compile(r"1인당|인당|가구당|기업당|지원단가|지급액|급여액|보조금액")),
            ("subsidy_rate", re.compile(r"보조율|지원비율|국고보조율")),
            ("annual_transfer_amount", re.compile(r"연간.*(?:지원액|급여액|보조금)|총지원액")),
        ),
        "capital": (
            ("required_area", re.compile(r"면적|연면적|부지면적|건축면적")),
            ("construction_unit_cost", re.compile(r"공사비.*단가|건축.*단가|면적당.*공사|㎡당|평당")),
            ("land_unit_price", re.compile(r"토지.*단가|부지.*단가|공시지가")),
            ("asset_quantity", re.compile(r"장비수|시설수|수량|개소수|대수")),
            ("asset_unit_cost", re.compile(r"장비.*단가|시설.*단가|자산.*단가|구입단가")),
            ("design_supervision_rate", re.compile(r"설계.*요율|감리.*요율|설계비율|감리비율")),
            ("annual_capital_amount", re.compile(r"총공사비|총사업비|자산취득비총액")),
        ),
        "tax_expenditure": (
            ("tax_base", re.compile(r"과세표준|과세대상금액|세원|소득금액|거래금액")),
            ("taxpayer_count", re.compile(r"납세자|신고인원|적용인원|과세인원")),
            ("tax_rate_change", re.compile(r"세율.*(?:변화|인하|차이)|감면율")),
            ("deduction_change", re.compile(r"공제.*(?:증가|확대|차액|금액)|공제액")),
            ("take_up_rate", re.compile(r"적용률|신청률|이용률")),
            ("annual_tax_reduction", re.compile(r"연간감면액|감면실적|세수효과|세수감소")),
        ),
        "non_tax_revenue_loss": (
            ("transaction_count", re.compile(r"이용건수|부과건수|납부건수|발급건수|대상건수")),
            ("fee_change_per_case", re.compile(r"건당.*(?:수수료|사용료|부담금)|(?:수수료|사용료|부담금).*차액")),
            ("exemption_rate", re.compile(r"면제율|감면율|미징수율")),
            ("annual_revenue_loss", re.compile(r"연간.*(?:수입감소|세외수입감소)|수입감소액")),
            ("annual_non_tax_revenue_base", re.compile(r"수수료수입액|사용료수입액|부담금수입액|세외수입액")),
        ),
        "equity_contribution": (
            ("institution_count", re.compile(r"기관수|법인수|기금수|출자대상")),
            ("contribution_per_institution", re.compile(r"기관당.*(?:출자|출연)|출연단가|출자단가")),
            ("project_cost", re.compile(r"총사업비|사업비규모|필요재원")),
            ("government_share", re.compile(r"정부.*(?:분담률|출자비율|출연비율)|국비비율")),
            ("annual_contribution_amount", re.compile(r"연간.*(?:출자|출연)|출자금|출연금")),
        ),
    }
    for key, pattern in rules.get(cost_nature, ()):
        if pattern.search(name):
            return key, "high"

    if variable_type == "target_count":
        return "quantity", "medium"
    if variable_type == "unit_cost":
        return "unit_cost", "medium"
    if variable_type == "frequency":
        return "frequency_per_year", "medium"
    if variable_type == "rate":
        return "generic_rate", "medium"
    if variable_type == "period":
        return "duration", "medium"
    return None, "low"


_CURRENCY_SCALE = {
    "억원": 100_000_000.0,
    "백만원": 1_000_000.0,
    "천만원": 10_000_000.0,
    "만원": 10_000.0,
    "천원": 1_000.0,
    "원": 1.0,
}
_COUNT_UNITS = {
    "명": "person",
    "인": "person",
    "가구": "household",
    "건": "case",
    "회": "event",
    "개": "unit",
    "개소": "site",
    "곳": "site",
    "대": "unit",
    "기관": "institution",
    "기업": "company",
    "법인": "institution",
    "㎡": "m2",
    "m2": "m2",
    "평": "pyeong",
}


def normalize_value_unit(
    canonical_key: str | None,
    value: Any,
    raw_unit: str,
) -> tuple[float | int | None, str | None, str, list[str]]:
    numeric = _number(value)
    unit = _compact(raw_unit).replace("제곱미터", "m2")
    if numeric is None:
        return None, None, "missing", ["missing_numeric_value"]
    if canonical_key is None:
        return None, None, "not_normalized", ["unmapped_variable"]

    if canonical_key.endswith("_rate") or canonical_key in {
        "generic_rate", "participation_rate", "take_up_rate", "government_share",
        "tax_rate_change", "exemption_rate", "first_year_fraction",
        "basic_expense_ratio", "employer_contribution_rate", "subsidy_rate",
        "design_supervision_rate",
    }:
        if "%" in unit:
            return float(numeric) / 100.0, "ratio", "normalized", []
        if unit in {"비율", "ratio", ""} and 0 <= float(numeric) <= 1:
            return numeric, "ratio", "normalized", []
        return None, None, "ambiguous", ["rate_unit_or_scale_ambiguous"]

    if canonical_key in {"duration", "recurrence_interval_years"}:
        if "개월" in unit or unit == "월":
            return numeric, "month", "normalized", []
        if "년" in unit:
            return numeric, "year", "normalized", []
    if canonical_key == "start_year" and ("년" in unit or 2000 <= float(numeric) <= 2200):
        return numeric, "year", "normalized", []
    if canonical_key in {"frequency_per_year", "payments_per_year"}:
        if "회/년" in unit or "회" in unit:
            return numeric, "event/year", "normalized", []

    currency = next((name for name in _CURRENCY_SCALE if unit.startswith(name)), None)
    if currency:
        normalized = float(numeric) * _CURRENCY_SCALE[currency]
        suffix = unit[len(currency):].lstrip("/")
        denominator = _COUNT_UNITS.get(suffix)
        if denominator:
            return normalized, f"KRW/{denominator}", "normalized", []
        if "㎡" in unit or "m2" in unit:
            return normalized, "KRW/m2", "normalized", []
        if "명" in unit or "인" in unit:
            return normalized, "KRW/person", "normalized", []
        if "가구" in unit:
            return normalized, "KRW/household", "normalized", []
        if "건" in unit:
            return normalized, "KRW/case", "normalized", []
        if canonical_key == "salary_per_person":
            return normalized, "KRW/person/year", "normalized", []
        annual_keys = {
            "annual_salary_amount", "annual_goods_amount", "annual_transfer_amount",
            "annual_capital_amount", "annual_tax_reduction", "annual_revenue_loss",
            "annual_contribution_amount",
        }
        return normalized, "KRW/year" if canonical_key in annual_keys else "KRW", "normalized", []

    for raw, normalized_unit in _COUNT_UNITS.items():
        if unit == raw or unit.startswith(f"{raw}/"):
            return numeric, normalized_unit, "normalized", []
    if unit in {"년", "개월", "월"}:
        return numeric, "year" if unit == "년" else "month", "normalized", []
    return None, None, "ambiguous", ["unit_not_safely_normalized"]


def infer_source_class(source_text: str) -> str:
    text = _compact(source_text)
    if re.search(r"통계청|kosis|국가통계|행정통계", text):
        return "official_statistics"
    if re.search(r"예산|결산|각목명세서", text):
        return "budget_or_settlement"
    if re.search(r"전망|물가상승률|임금상승률", text):
        return "official_forecast"
    if re.search(r"법정단가|고시|시행령|시행규칙|공식단가", text):
        return "official_standard"
    if re.search(r"유사사례|준용|비슷한사례", text):
        return "similar_case"
    if re.search(r"가정|추정|예상", text):
        return "analyst_assumption"
    if re.search(r"개정안|법률안|안제\d+조|조문", text):
        return "bill_or_target_document"
    return "unclassified_source"


def infer_transfer_policy(
    canonical_key: str | None,
    source_class: str,
    normalized_value: Any,
) -> str:
    if normalized_value is None or canonical_key is None:
        return "do_not_transfer"
    if canonical_key in {
        "recipient_count", "taxpayer_count", "transaction_count", "headcount",
        "headcount_by_grade", "quantity", "service_quantity", "asset_quantity",
        "required_area", "institution_count", "project_cost", "tax_base",
    }:
        return "target_specific"
    if source_class in {"official_standard", "official_forecast"}:
        return "versioned_official"
    if source_class == "official_statistics":
        return "scope_check_required"
    if source_class in {"similar_case", "budget_or_settlement"}:
        return "comparable_only"
    return "review_required"


FORMULA_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {"formula_key":"PERSONNEL_GRADE_V1","cost_natures":["personnel"],"label":"직급별 인건비","expression":"Σ(직급별 순증인원 × 직급별 1인당 보수)","required_variables":["headcount_by_grade","salary_by_grade"],"optional_variables":["growth_rate"],"recurrence":"annual"},
    {"formula_key":"PERSONNEL_AVERAGE_V1","cost_natures":["personnel"],"label":"평균단가 인건비","expression":"순증인원 × 1인당 보수","required_variables":["headcount","salary_per_person"],"optional_variables":["growth_rate"],"recurrence":"annual"},
    {"formula_key":"PERSONNEL_EMPLOYER_CONTRIBUTION_V1","cost_natures":["personnel"],"label":"기관부담금","expression":"보수총액 × 기관부담률","required_variables":["annual_salary_amount","employer_contribution_rate"],"optional_variables":[],"recurrence":"annual"},
    {"formula_key":"PERSONNEL_BASIC_EXPENSE_V1","cost_natures":["personnel"],"label":"비율형 기본경비","expression":"보수총액 × 기본경비 비율","required_variables":["annual_salary_amount","basic_expense_ratio"],"optional_variables":["growth_rate"],"recurrence":"annual"},
    {"formula_key":"PERSONNEL_ASSET_V1","cost_natures":["personnel"],"label":"인력 자산취득비","expression":"순증인원 × 1인당 자산취득비","required_variables":["headcount","asset_unit_price_per_person"],"optional_variables":["start_year"],"recurrence":"one_time"},
    {"formula_key":"COMMON_QUANTITY_UNIT_V1","cost_natures":["goods_services","capital"],"label":"수량·단가형","expression":"수량 × 단가","required_variables":["quantity","unit_cost"],"optional_variables":["growth_rate"],"recurrence":"mixed"},
    {"formula_key":"GOODS_SERVICE_ACTIVITY_V1","cost_natures":["goods_services"],"label":"사업·서비스 활동량형","expression":"수량 × 단가 × 연간 횟수","required_variables":["service_quantity","service_unit_cost","frequency_per_year"],"optional_variables":["growth_rate","duration"],"recurrence":"annual"},
    {"formula_key":"TRANSFER_RECIPIENT_V1","cost_natures":["transfers"],"label":"수혜자 지급형","expression":"대상자 수 × 참여율 × 1인당 지급액 × 연간 지급횟수","required_variables":["recipient_count","benefit_per_recipient"],"optional_variables":["participation_rate","payments_per_year","growth_rate"],"recurrence":"annual"},
    {"formula_key":"TRANSFER_SUBSIDY_RATE_V1","cost_natures":["transfers"],"label":"보조율형","expression":"적격 사업비 × 보조율","required_variables":["project_cost","subsidy_rate"],"optional_variables":["participation_rate"],"recurrence":"annual"},
    {"formula_key":"CAPITAL_AREA_V1","cost_natures":["capital"],"label":"면적·공사단가형","expression":"면적 × 면적당 공사단가","required_variables":["required_area","construction_unit_cost"],"optional_variables":["design_supervision_rate","growth_rate"],"recurrence":"scheduled"},
    {"formula_key":"CAPITAL_ASSET_V1","cost_natures":["capital"],"label":"장비·자산형","expression":"자산 수량 × 자산 단가","required_variables":["asset_quantity","asset_unit_cost"],"optional_variables":["growth_rate"],"recurrence":"scheduled"},
    {"formula_key":"TAX_RATE_CHANGE_V1","cost_natures":["tax_expenditure"],"label":"세율 변화형","expression":"과세표준 × 세율 변화 × 적용률","required_variables":["tax_base","tax_rate_change"],"optional_variables":["take_up_rate","growth_rate"],"recurrence":"annual"},
    {"formula_key":"TAX_DEDUCTION_CHANGE_V1","cost_natures":["tax_expenditure"],"label":"공제 변화형","expression":"적용 인원 × 공제액 변화 × 적용률","required_variables":["taxpayer_count","deduction_change"],"optional_variables":["take_up_rate","growth_rate"],"recurrence":"annual"},
    {"formula_key":"NON_TAX_FEE_CHANGE_V1","cost_natures":["non_tax_revenue_loss"],"label":"수수료·부담금 변화형","expression":"대상 건수 × 건당 수입 감소액 × 적용률","required_variables":["transaction_count","fee_change_per_case"],"optional_variables":["exemption_rate","growth_rate"],"recurrence":"annual"},
    {"formula_key":"EQUITY_PROJECT_SHARE_V1","cost_natures":["equity_contribution"],"label":"사업비 분담형","expression":"총사업비 × 정부 분담률","required_variables":["project_cost","government_share"],"optional_variables":["duration"],"recurrence":"scheduled"},
    {"formula_key":"EQUITY_INSTITUTION_UNIT_V1","cost_natures":["equity_contribution"],"label":"기관별 출자·출연형","expression":"기관 수 × 기관당 출자·출연액","required_variables":["institution_count","contribution_per_institution"],"optional_variables":["growth_rate"],"recurrence":"scheduled"},
    {"formula_key":"DIRECT_ANNUAL_AMOUNT_V1","cost_natures":["personnel","goods_services","transfers","capital","tax_expenditure","non_tax_revenue_loss","equity_contribution"],"label":"직접 연간금액형","expression":"검증된 연간 금액","required_variables":["annual_amount"],"optional_variables":["growth_rate","duration","first_year_fraction"],"recurrence":"annual"},
)


def infer_formula_family(cost_nature: str, canonical_keys: set[str]) -> str:
    annual_amount_keys = {
        "annual_salary_amount", "annual_goods_amount", "annual_transfer_amount",
        "annual_capital_amount", "annual_tax_reduction", "annual_revenue_loss",
        "annual_non_tax_revenue_base", "annual_contribution_amount",
    }
    candidates = [
        row for row in FORMULA_DEFINITIONS
        if cost_nature in row["cost_natures"]
        and row["formula_key"] != "DIRECT_ANNUAL_AMOUNT_V1"
    ]
    scored: list[tuple[int, int, str]] = []
    for formula in candidates:
        required = set(formula["required_variables"])
        matched = len(required & canonical_keys)
        complete = int(required <= canonical_keys)
        scored.append((complete, matched, formula["formula_key"]))
    complete_rows = [row for row in scored if row[0]]
    if complete_rows:
        return max(complete_rows)[2]
    if canonical_keys & annual_amount_keys:
        return "DIRECT_ANNUAL_AMOUNT_V1"
    if not scored:
        return "REVIEW_REQUIRED"
    complete, matched, key = max(scored)
    return key if complete or matched else "REVIEW_REQUIRED"


def formula_readiness(
    formula_key: str, canonical_keys: set[str]
) -> tuple[str, list[str]]:
    if formula_key == "REVIEW_REQUIRED":
        return "unresolved", []
    if formula_key == "DIRECT_ANNUAL_AMOUNT_V1":
        annual_amount_keys = {
            "annual_salary_amount", "annual_goods_amount", "annual_transfer_amount",
            "annual_capital_amount", "annual_tax_reduction", "annual_revenue_loss",
            "annual_non_tax_revenue_base", "annual_contribution_amount",
        }
        return (
            ("ready", [])
            if canonical_keys & annual_amount_keys
            else ("partial", ["annual_amount"])
        )
    formula = next(
        (row for row in FORMULA_DEFINITIONS if row["formula_key"] == formula_key),
        None,
    )
    if formula is None:
        return "unresolved", []
    missing = sorted(set(formula["required_variables"]) - canonical_keys)
    return ("partial" if missing else "ready"), missing


def _load_raw(seed_dirs: Iterable[Path]) -> tuple[dict[str, dict[str, Any]], ...]:
    structures: dict[str, dict[str, Any]] = {}
    items: dict[str, dict[str, Any]] = {}
    variables: dict[str, dict[str, Any]] = {}
    amounts: dict[str, dict[str, Any]] = {}
    for directory in seed_dirs:
        for row in read_jsonl(directory / "cost_estimate_structures.jsonl"):
            key = str(row.get("struct_id") or "")
            if key:
                structures[key] = row
        for row in read_jsonl(directory / "cost_estimate_items.jsonl"):
            key = str(row.get("item_id") or "")
            if key:
                items[key] = row
        for index, row in enumerate(read_jsonl(directory / "cost_estimate_variables.jsonl")):
            key = stable_key(
                "rawvar", row.get("item_id"), row.get("variable_type"),
                row.get("variable_name"), row.get("variable_value"),
                row.get("variable_unit"), row.get("source_text"), index,
            )
            variables[key] = row
        for index, row in enumerate(read_jsonl(directory / "cost_estimate_amounts.jsonl")):
            key = stable_key(
                "rawamt", row.get("item_id"), row.get("year_label"),
                row.get("year_offset"), row.get("amount_thousand"),
                row.get("formula_text"), row.get("is_total"), index,
            )
            amounts[key] = row
    return structures, items, variables, amounts


def parse_reply_date(text: str) -> str | None:
    """Return the official cost-estimate reply date as ISO text.

    A historical estimate is not available on the bill proposal date.  The
    reply date printed in the estimate is therefore the earliest safe cutoff
    for holdout retrieval.  Missing dates remain missing instead of falling
    back to the proposal date.
    """
    match = _REPLY_DATE_RE.search(str(text or ""))
    if not match:
        return None
    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _load_reply_dates(seed_dirs: Iterable[Path]) -> dict[str, str]:
    dates: dict[str, str] = {}
    for directory in seed_dirs:
        for row in read_jsonl(directory / "chunks.jsonl"):
            document_type = str(
                row.get("documentType") or row.get("document_type") or ""
            )
            if document_type != "cost_estimate":
                continue
            bill_no = str(row.get("billNo") or row.get("bill_no") or "")
            if not bill_no or bill_no in dates:
                continue
            reply_date = parse_reply_date(str(row.get("text") or ""))
            if reply_date:
                dates[bill_no] = reply_date
    return dates


def build_document_profiles(manifest: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in read_jsonl(manifest):
        if row.get("status") != "complete":
            continue
        labels = list(row.get("categories") or [])
        natures = [LABEL_TO_COST_NATURE.get(label, "review_required") for label in labels]
        primary = LABEL_TO_COST_NATURE.get(str(row.get("primary_category") or ""), "review_required")
        rows.append(
            {
                "document_profile_key": stable_key("costdoc", row.get("bill_id"), row.get("bill_no")),
                "bill_id": row.get("bill_id"),
                "bill_no": row.get("bill_no"),
                "bill_name": row.get("bill_name"),
                "age": row.get("age"),
                "proposer": row.get("proposer"),
                "propose_date": row.get("propose_date"),
                "committee": row.get("committee"),
                "cost_natures": natures,
                "cost_nature_labels": labels,
                "primary_cost_nature": primary,
                "classification_source": row.get("classification_source"),
                "classification_status": row.get("classification_status"),
                "item_extraction_status": "pending",
                "schema_version": SCHEMA_VERSION,
            }
        )
    return rows


def build_sidecar(
    *,
    manifest: Path,
    seed_dirs: Iterable[Path],
    excluded_bill_ids: set[str] | None = None,
    excluded_bill_nos: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    excluded_bill_ids = set(excluded_bill_ids or ())
    excluded_bill_nos = set(excluded_bill_nos or ())
    document_profiles = build_document_profiles(manifest)
    doc_by_bill_id = {str(row.get("bill_id") or ""): row for row in document_profiles}
    seed_dirs = tuple(seed_dirs)
    structures, items, variables, amounts = _load_raw(seed_dirs)
    reply_dates = _load_reply_dates(seed_dirs)

    variables_by_item: dict[str, list[dict[str, Any]]] = {}
    for row in variables.values():
        variables_by_item.setdefault(str(row.get("item_id") or ""), []).append(row)
    amounts_by_item: dict[str, list[dict[str, Any]]] = {}
    for row in amounts.values():
        amounts_by_item.setdefault(str(row.get("item_id") or ""), []).append(row)

    profiles: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    structured_bill_ids: set[str] = set()

    for item_id, item in sorted(items.items()):
        raw_variables = variables_by_item.get(item_id, [])
        raw_amounts = amounts_by_item.get(item_id, [])
        bill_id = str(item.get("bill_id") or "")
        structure = structures.get(str(item.get("struct_id") or ""), {})
        document = doc_by_bill_id.get(bill_id, {})
        bill_no = str(structure.get("bill_no") or document.get("bill_no") or "")
        if bill_id in excluded_bill_ids or bill_no in excluded_bill_nos:
            continue
        document_natures = list(document.get("cost_natures") or [])
        nature, confidence, reason = classify_cost_nature(
            item,
            variables=raw_variables,
            amounts=raw_amounts,
            document_natures=document_natures,
        )
        component = classify_component(nature, item)
        profile_key = stable_key("costitem", item_id)
        canonical_keys: set[str] = set()
        available_keys: set[str] = set()
        normalized_values_by_key: dict[str, set[tuple[float | int, str]]] = {}
        staged_evidence: list[dict[str, Any]] = []

        for raw in raw_variables:
            canonical_key, mapping_confidence = infer_canonical_key(nature, component, raw)
            normalized_value, normalized_unit, unit_status, flags = normalize_value_unit(
                canonical_key, raw.get("variable_value"), str(raw.get("variable_unit") or "")
            )
            source_text = str(raw.get("source_text") or "")
            years = sorted({int(value) for value in _YEAR_RE.findall(source_text)})
            source_class = infer_source_class(source_text)
            policy = infer_transfer_policy(canonical_key, source_class, normalized_value)
            if canonical_key:
                canonical_keys.add(canonical_key)
                if normalized_value is not None:
                    available_keys.add(canonical_key)
                    normalized_values_by_key.setdefault(canonical_key, set()).add(
                        (normalized_value, str(normalized_unit or ""))
                    )
            if len(years) != 1:
                flags.append("basis_year_missing" if not years else "multiple_basis_years")
            if mapping_confidence != "high":
                flags.append("mapping_not_high_confidence")
            fingerprint = stable_key(
                "rawvar", item_id, raw.get("variable_type"), raw.get("variable_name"),
                raw.get("variable_value"), raw.get("variable_unit"), source_text,
            )
            staged_evidence.append(
                {
                    "evidence_key": stable_key("costev", fingerprint),
                    "profile_key": profile_key,
                    "raw_variable_fingerprint": fingerprint,
                    "canonical_key": canonical_key,
                    "raw_variable_type": raw.get("variable_type"),
                    "raw_variable_name": str(raw.get("variable_name") or ""),
                    "raw_value": _number(raw.get("variable_value")),
                    "raw_unit": raw.get("variable_unit"),
                    "normalized_value": normalized_value,
                    "normalized_unit": normalized_unit,
                    "source_class": source_class,
                    "transfer_policy": policy,
                    "source_text": source_text,
                    "basis_year_candidates": years,
                    "basis_year": years[0] if len(years) == 1 else None,
                    "mapping_confidence": mapping_confidence,
                    "normalization_status": "mapped" if canonical_key else "unmapped",
                    "unit_status": unit_status,
                    "review_status": "candidate",
                    "quality_flags": sorted(set(flags)),
                    "transform_version": MAPPER_VERSION,
                }
            )

        formula_family = infer_formula_family(nature, canonical_keys)
        # Several role-specific values under one canonical operand cannot be
        # collapsed by picking an arbitrary row. A later grouped-operand
        # mapper may sum them, but the flat sidecar must remain non-executable.
        ambiguous_keys = {
            key for key, values in normalized_values_by_key.items()
            if key in {"headcount", "salary_per_person"} and len(values) > 1
        }
        readiness, missing_formula_variables = formula_readiness(
            formula_family, available_keys - ambiguous_keys
        )
        profiles.append(
            {
                "profile_key": profile_key,
                "source_item_key": item_id,
                "raw_structure_key": item.get("struct_id"),
                "bill_id": bill_id or None,
                "bill_no": structure.get("bill_no") or document.get("bill_no"),
                "bill_name": structure.get("bill_name") or document.get("bill_name"),
                "propose_date": structure.get("propose_date") or document.get("propose_date"),
                "available_date": reply_dates.get(
                    str(structure.get("bill_no") or document.get("bill_no") or "")
                ),
                "committee": structure.get("committee") or document.get("committee"),
                "item_name": str(item.get("item_name") or ""),
                "raw_item_category": item.get("item_category"),
                "trigger_ref": item.get("trigger_ref"),
                "cost_nature": nature,
                "component": component,
                "formula_family": formula_family,
                "formula_readiness": readiness,
                "missing_formula_variables": missing_formula_variables,
                "classification_confidence": confidence,
                "classification_reason": reason,
                "classifier_version": CLASSIFIER_VERSION,
                "review_status": "candidate",
                "raw_attributes": {
                    "age": structure.get("age") or document.get("age"),
                    "item_order": item.get("item_order"),
                },
            }
        )
        evidence.extend(staged_evidence)
        structured_bill_ids.add(bill_id)

        for raw in raw_amounts:
            observations.append(
                {
                    "observation_key": stable_key(
                        "costamt", item_id, raw.get("year_label"), raw.get("year_offset"),
                        raw.get("amount_thousand"), raw.get("formula_text"), raw.get("is_total"),
                    ),
                    "profile_key": profile_key,
                    "year_label": raw.get("year_label"),
                    "year_offset": raw.get("year_offset"),
                    "amount_thousand": raw.get("amount_thousand"),
                    "formula_text": raw.get("formula_text"),
                    "is_total": bool(raw.get("is_total")),
                    "review_status": "candidate",
                    "transform_version": SCHEMA_VERSION,
                }
            )

    for row in document_profiles:
        if str(row.get("bill_id") or "") in structured_bill_ids:
            row["item_extraction_status"] = "structured_candidate"

    summary = {
        "schema_version": SCHEMA_VERSION,
        "document_profiles": len(document_profiles),
        "structured_documents": sum(
            1 for row in document_profiles if row["item_extraction_status"] == "structured_candidate"
        ),
        "structured_documents_all_seed_ages": len(
            {str(row.get("bill_id") or "") for row in structures.values() if row.get("bill_id")}
        ),
        "pending_item_extraction": sum(
            1 for row in document_profiles if row["item_extraction_status"] == "pending"
        ),
        "item_profiles": len(profiles),
        "variable_evidence": len(evidence),
        "amount_observations": len(observations),
        "cost_nature": dict(Counter(row["cost_nature"] for row in profiles)),
        "component": dict(Counter(row["component"] for row in profiles)),
        "formula_family": dict(Counter(row["formula_family"] for row in profiles)),
        "formula_readiness": dict(Counter(row["formula_readiness"] for row in profiles)),
        "canonical_key": dict(Counter(row.get("canonical_key") or "unmapped" for row in evidence)),
        "unit_status": dict(Counter(row["unit_status"] for row in evidence)),
        "transfer_policy": dict(Counter(row["transfer_policy"] for row in evidence)),
        "review_status": "all_candidate",
        "validation_holdout_documents": max(
            len(excluded_bill_ids), len(excluded_bill_nos)
        ),
    }
    return document_profiles, profiles, evidence, observations, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--validation-manifest", type=Path, default=DEFAULT_VALIDATION_MANIFEST
    )
    parser.add_argument("--include-validation-holdout", action="store_true")
    parser.add_argument("--seed-dir", action="append", type=Path, dest="seed_dirs")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    excluded_bill_ids: set[str] = set()
    excluded_bill_nos: set[str] = set()
    if not args.include_validation_holdout:
        excluded_bill_ids, excluded_bill_nos = load_validation_holdout(
            args.validation_manifest
        )
    document_profiles, profiles, evidence, observations, summary = build_sidecar(
        manifest=args.manifest,
        seed_dirs=tuple(args.seed_dirs or DEFAULT_SEED_DIRS),
        excluded_bill_ids=excluded_bill_ids,
        excluded_bill_nos=excluded_bill_nos,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "document_profiles.jsonl", document_profiles)
    write_jsonl(args.output_dir / "item_profiles.jsonl", profiles)
    write_jsonl(args.output_dir / "variable_evidence.jsonl", evidence)
    write_jsonl(args.output_dir / "amount_observations.jsonl", observations)
    write_jsonl(args.output_dir / "formula_definitions.jsonl", FORMULA_DEFINITIONS)
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
