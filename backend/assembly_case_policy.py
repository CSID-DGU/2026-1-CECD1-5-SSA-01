from __future__ import annotations

import re
from typing import Any


# Validation provenance only. Runtime decisions never branch on bill numbers.
VALIDATED_CASES = {
    "legislative_special_committee_bundle": {
        "confirmed": ["2126636", "2212534", "2213195", "2214994", "2215199"],
        "lesson": "국회 특별위원회는 인건비, 기관부담금, 기본경비, 자산취득비와 사업비를 분리한다.",
    },
    "simple_committee_meeting_cost": {
        "confirmed": ["2126640"],
        "lesson": "별도 사무조직이 없는 심의위원회는 회의횟수, 수당대상 인원과 수당 단가를 우선 적용한다.",
    },
    "delegated_scope_technical_difficulty": {
        "confirmed": ["2126641"],
        "lesson": "사업 범위와 수행 방식이 하위규정에 전부 위임되면 기술적 곤란을 우선 검토한다.",
    },
    "institution_establishment_composite": {
        "confirmed": ["2126648", "2215954"],
        "lesson": "기관 신설은 인력, 기본경비, 자산, 시설과 운영비를 복합 비용으로 분리한다.",
    },
    "research_service_analogy": {
        "confirmed": ["2217814"],
        "lesson": "실태조사는 조사 주기와 범위가 같은 사례만 단가 근거로 사용한다.",
    },
    "transfer_payment_variables": {
        "confirmed": ["2212022"],
        "lesson": "직접지원은 대상 수, 증분 단가, 지급 횟수와 집행률을 분리한다.",
    },
    "minor_existing_program_expansion": {
        "failed_then_learned": ["2126664"],
        "lesson": "기존 사업의 대상 범위 문구 변경과 안내 의무만으로 대규모 신규 사업을 가정하지 않는다.",
    },
}


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def apply_validated_case_policy(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply reusable policies learned from answer-sheet comparisons."""
    for article in articles:
        text = _compact(article.get("text"))
        rule = article.get("rule_cost_trigger") or {}

        if (
            article.get("trigger_type") in {"대상확대", "의무부과"}
            and re.search(r"(적극적으로)?안내하여야|알려야|홍보하여야", text)
            and not re.search(r"(지급|지원금|급여|수당|보조금|비용을지원)", text)
        ):
            article["cost_candidate_strength"] = "weak"
            article["estimate_feasibility"] = "minor_or_absorbable"
            article["case_policy"] = "minor_existing_program_expansion"
            article["reason"] = (
                "기존 사업의 안내·홍보 의무로서 통상적인 행정운영 범위에서 집행될 가능성이 높아 "
                "독립적인 대규모 비용항목으로 보지 않습니다."
            )
            continue

        if (
            article.get("trigger_type") == "대상확대"
            and not re.search(r"(지급|지원금|급여|수당|보조금|비용을지원|지원한다|지원하여야)", text)
        ):
            article["cost_candidate_strength"] = "weak"
            article["estimate_feasibility"] = "minor_or_absorbable"
            article["case_policy"] = "minor_existing_program_expansion"
            article["reason"] = (
                "적용 대상 범위는 변경되지만 조문 자체에 신규 급여·지원 단가 또는 별도 사업 의무가 없어 "
                "기존 사업 내 흡수 가능성과 소액 미첨부 여부를 우선 검토합니다."
            )
            continue

        if (
            rule.get("estimate_feasibility") == "non_attachment_review"
            and re.search(r"(구체적|필요한사항).{0,45}(대통령령|부령|장관이정한다)", text)
            and not re.search(r"(매월|연1회|매년|\d+명|\d+개소|\d+원|\d+만원)", text)
        ):
            article["case_policy"] = "delegated_scope_technical_difficulty"
    return articles
