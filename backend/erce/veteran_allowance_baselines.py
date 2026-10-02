"""Reusable historical atoms from earlier bill 2200169, not its projected answers."""
from backend.erce.reviewed_variable_rows import evidence_row


def veteran_allowance_baseline_rows():
    common = dict(
        agency="국가보훈부", policy_domain="참전유공자 예우",
        service_function="참전명예수당 지급 및 병급허용",
        allowed_routes=["transfer_recipient", "transfer_recipient_delta"],
        reviewed_at="2026-09-28", obtained_from="earlier_non_target_estimate",
    )
    precedent = dict(
        source_bill_no="2200169", available_at="2024-08-09",
        source_ref="의안 2200169 비용추계서(24D0536), PDF p.5~9, 2019~2024 국가보훈부 실적",
        source_url="backend/generated/assembly_22_pdfs/by_bill/2200169/cost_estimate.pdf",
        reuse_policy="comparable", source_class="precedent_assumption",
        requires_applicability_note=True,
        limitation="미래 전망치가 아닌 과거 관측치. 동일 참전유공자 집단과 병급제도에만 적용; 미래 증가율 유지 여부는 별도 가정",
        **common,
    )
    rows = []
    for key, value, year, unit, scope in (
        ("concurrent_excluded_2023", 94593, 2023, "person", "2023년 병급금지로 명예수당 미수급 참전유공자"),
        ("existing_recipients_2019", 190329, 2019, "person", "2019년 기존 참전명예수당 수급자"),
        ("existing_recipients_2023", 132479, 2023, "person", "2023년 기존 참전명예수당 수급자"),
        ("existing_monthly_benefit_2020", 320000, 2020, "KRW/person/month", "2020년 참전명예수당 월액"),
        ("existing_monthly_benefit_2024", 420000, 2024, "KRW/person/month", "2024년 참전명예수당 월액"),
    ):
        rows.append(evidence_row(evidence_key=f"2200169:raw:{key}", variable_key=key,
                                 value=value, unit=unit, scope=scope, observation_year=year,
                                 variable_role="historical_actual", **precedent))
    for key, value, year, available, ref, url in (
        ("median_income_2020", 1757194, 2020, "2020-08-01",
         "보건복지부 제60차 중앙생활보장위원회 발표, 2020년 1인가구 기준 중위소득",
         "https://www.mohw.go.kr/gallery.es?act=view&bid=0003&list_no=358829&mid=a10605040000"),
        ("median_income_2024", 2228445, 2024, "2023-07-28",
         "보건복지부 제70차 중앙생활보장위원회 보도자료, 2024년 1인가구 기준 중위소득",
         "https://www.mohw.go.kr/board.es?act=view&bid=0027&list_no=377507&mid=a10503000000"),
    ):
        rows.append(evidence_row(
            evidence_key=f"official:mohw:{key}", variable_key=key, value=value,
            unit="KRW/person/month", source_bill_no=f"official:mohw:{key}",
            available_at=available, source_ref=ref, source_url=url,
            agency="국가보훈부", publisher="보건복지부", policy_domain="참전유공자 예우",
            scope=f"{year}년 1인가구 기준 중위소득",
            service_function="기준중위소득 연동 참전명예수당", variable_role="official_historical_rate",
            reuse_policy="same_scope", source_class="official_standard",
            allowed_routes=["transfer_recipient", "transfer_recipient_delta"],
            observation_year=year, reviewed_at="2026-09-28",
            obtained_from="retrospective_pre_cutoff_source_research",
            limitation="과거 공식값. 미래 기준중위소득 증가율은 확정치가 아니라 추계 가정"))
    return rows
