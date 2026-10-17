"""Scoped aliases of existing population evidence, no new gold quantities.

The count variable here is a person stock for each year. Original person/year
labels describe annual rows, not annual newborn flows. Sources/versions remain.
"""
from backend.erce.child_allowance_evidence import child_allowance_rows
from backend.erce.parent_benefit_evidence import parent_benefit_rows

ALIAS_KEYS = (
    "2200147:under18_population:2025-2029:child_net",
    "2200147:under8_population:2025-2029:child_net",
    "kosis_202312:age0_population:2025-2029:child_net",
    "kosis_202312:age1_population:2025-2029:child_net",
    "2200147:child_allowance_payment_rate:2024:child_net",
)


def child_allowance_net_rows():
    lookup={r["evidence_key"]:r for r in child_allowance_rows()+parent_benefit_rows()}
    names=("under18_population","under8_population","age0_population","age1_population","child_payment_rate")
    rows=[]
    for alias,key in zip(ALIAS_KEYS,names):
        original=lookup[alias.removesuffix(":child_net")]
        rows.append({**original,"evidence_key":alias,"variable_key":key,
            "unit":"ratio" if key=="child_payment_rate" else "person",
            "allowed_routes":["transfer_population_amount_delta"],
            "support_derivation":"child_allowance_net_population",
            "child_allowance_scenario":"under2_parent_only",
            "child_population_geography":"전국",
            "alias_of":original["evidence_key"],"reviewed_at":"2026-10-04",
            "geography":"전국","refresh_policy":"원통계 버전·연령·기간의 일치 여부를 확인하고 새 버전 추가",
            "limitation":original["limitation"]+"; 같은2023년12월 중위전망에서 전국2~17세와0~7세를 비교. 부모급여 유지·2세미만 기본 아동수당 제외는 별도 확인."})
    return rows
