"""정답지(NABO 비용추계서)와 같은 형식의 초안 문서 생성.

계산된 항목은 숫자로, 확인이 필요한 항목(위원회 등)은 산식 + 명시적 전제
질문으로 채운다. NABO 공식 문서도 각주에 "가정하여 산출"을 명시하는 것과
같은 방식 — 빈칸을 남기지 않고, 자동계산과 전제를 구분해서 보여준다.
"""
from __future__ import annotations

from .types import EstimateResult, RowStatus

DRAFT_DOCUMENT_VERSION = "draft-document-v1"


def render_draft_document(result: EstimateResult, *, years: int = 5) -> str:
    lines: list[str] = []
    lines.append(f"# {result.bill_name} 비용추계서(초안)")
    lines.append("")
    lines.append("## Ⅰ. 비용추계 결과")
    lines.append("")

    computed_rows = [r for r in result.rows if r.status == RowStatus.COMPUTED_REVIEW]
    review_rows = [r for r in result.rows if r.status != RowStatus.COMPUTED_REVIEW]

    computed_total = sum(r.total_thousand for r in computed_rows) / 1000
    lines.append(
        f"자동 계산된 항목의 추가재정소요는 {years}년간 총 {computed_total:,.1f}백만원입니다. "
        f"({len(review_rows)}개 항목은 아래 '확인 필요 전제'를 사람이 확정해야 총액이 완성됩니다.)"
    )
    lines.append("")

    if computed_rows:
        lines.append("### 자동 계산 항목")
        lines.append("")
        lines.append("| 항목 | 5년 합계(백만원) | 근거 |")
        lines.append("|---|---:|---|")
        for row in computed_rows:
            amount = row.total_thousand / 1000
            lines.append(
                f"| {row.event.object} | {amount:,.1f} | {row.selection_method} |"
            )
        lines.append("")

    if review_rows:
        lines.append("### 확인 필요 항목 (산식은 확정, 전제값만 필요)")
        lines.append("")
        for row in review_rows:
            lines.append(f"**{row.event.object}**")
            if row.formula:
                lines.append(f"- 산식: `{row.formula}`")
            lines.append(f"- 사유: {row.reason}")
            lines.append("")

    lines.append("## Ⅱ. 비용추계의 전제")
    lines.append("")
    lines.append(
        "본 초안은 자동 계산 가능한 항목만 확정했으며, 확인 필요 항목은 "
        "산식(구조)까지만 자동 도출하고 실제 수치는 사람이 확인한 전제를 "
        "반영해야 완성됩니다. (NABO 공식 추계서와 동일하게, 전제는 명시하고 "
        "숨기지 않습니다.)"
    )
    for warning in result.warnings:
        lines.append(f"- {warning}")
    return "\n".join(lines)
