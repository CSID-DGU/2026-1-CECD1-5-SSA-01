"""Never describe an exact subtotal as a completed whole-bill estimate."""

RESOLVED={"estimated","grounded_non_estimation","direct_scope_reviewed"}


def scope_status(items,*,covered_amount_thousand=None,covered_error_percent=None):
    if not items or len({i["key"] for i in items})!=len(items):
        raise ValueError("scope review needs nonempty uniquely identified items")
    for item in items:
        if item["status"] not in RESOLVED|{"needs_review"}:
            raise ValueError("unknown scope status")
        if not str(item.get("source_ref") or "").strip():
            raise ValueError("each scope judgement needs provenance")
    pending=[i["key"] for i in items if i["status"]=="needs_review"]
    unresolved_amount=[i["key"] for i in items if i["status"] in {"needs_review","grounded_non_estimation"}]
    full_numeric=not unresolved_amount and covered_amount_thousand is not None
    return dict(overall_status="whole_numeric_complete" if full_numeric else
                "partial_pending_review" if pending else "scope_review_complete_partial_estimate",
        scope_review_complete=not pending,whole_numeric_complete=full_numeric,
        resolved_scope_count=len(items)-len(pending),scope_count=len(items),pending_scope_keys=pending,
        covered_amount_thousand=covered_amount_thousand,covered_error_percent=covered_error_percent,
        whole_bill_amount_thousand=covered_amount_thousand if full_numeric else None,
        whole_bill_error_percent=covered_error_percent if full_numeric else None)
