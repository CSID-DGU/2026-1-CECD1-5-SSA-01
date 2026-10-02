"""Pre-2024-06-10 public inputs for spouse-childbirth-leave grant scenarios.

The 2024 statutory cap is a ceiling, not observed average payment. It may be
used only when the caller explicitly chooses a maximum-payment scenario.
"""
from backend.erce.reviewed_variable_rows import evidence_row


def spouse_leave_rows():
    common = dict(
        policy_domain="모성보호", service_function="우선지원대상기업 배우자 출산휴가 급여",
        allowed_routes=["transfer_spouse_leave_extension"], reviewed_at="2026-09-28",
        obtained_from="retrospective_pre_cutoff_source_research",
    )
    return [
        evidence_row(
            evidence_key="official:kostat:medium_births:2025-2029",
            variable_key="annual_births", value=[218000, 229000, 239000, 248000, 257000],
            unit="birth/year", source_bill_no="official:kostat:population_projection_2023",
            available_at="2023-12-14",
            source_ref="통계청 장래인구추계(2022~2072), p.59 출생아수 중위추계(천명)",
            source_url="https://mods.go.kr/boardDownload.es?bid=207&list_no=428476&seq=6",
            agency="고용노동부", publisher="통계청", scope="전국 출생아 중위추계",
            variable_role="official_forecast", source_class="official_standard",
            reuse_policy="same_scope", value_years=[2025, 2026, 2027, 2028, 2029],
            limitation="천 명 단위 반올림된 전망치. 실제 출생아 수가 아님", **common),
        evidence_row(
            evidence_key="official:nabo:spouse_leave_recipients:2022",
            variable_key="historical_leave_recipients", value=16168,
            unit="person/year", source_bill_no="official:nabo:2023_fiscal_issues",
            available_at="2023-09-30",
            source_ref="국회예산정책처 2023 정기국회·국정감사 재정·경제 주요 이슈, p.229 표(고용노동부 자료)",
            source_url="https://www.nabo.go.kr/board/file/down.do?fid=33317671",
            agency="고용노동부", scope="2022년 배우자 출산휴가 급여 수급자",
            variable_role="historical_actual", source_class="official_standard",
            reuse_policy="same_scope", observation_year=2022,
            availability_note="보고서는 2023년 9월 발간으로만 표기되어 월말을 보수적 공개일로 사용",
            limitation="2022년 실적을 미래 수급률의 분자로 유지하는 것은 추계 가정", **common),
        evidence_row(
            evidence_key="official:kostat:births:2022",
            variable_key="historical_births", value=249186,
            unit="birth/year", source_bill_no="official:kostat:birth_statistics_2023",
            available_at="2023-11-29",
            source_ref="통계청 2023년 9월 인구동향 보도자료, p.5 표1 2022년 출생아 수",
            source_url="https://mods.go.kr/boardDownload.es?bid=204&list_no=428277&seq=3",
            agency="고용노동부", publisher="통계청", scope="2022년 전국 출생아 실적",
            variable_role="historical_actual", source_class="official_standard",
            reuse_policy="same_scope", observation_year=2022,
            limitation="출생아 전체가 급여 수급 대상은 아님. 과거 수급자/출생아 비율 산정의 분모", **common),
        evidence_row(
            evidence_key="official:moel:spouse_leave_cap_5days:2024",
            variable_key="grant_cap_per_reference_period", value=401910,
            unit="KRW/5days", source_bill_no="official:moel:notice_2023_84",
            available_at="2023-12-29",
            source_ref="고용노동부고시 제2023-84호, 2024년 최초 5일분 상한액 401,910원",
            source_url="https://www.moel.go.kr/common/downloadFile.do?file_seq=20231203446&bbs_seq=20231202328&bbs_id=19&file_ext=pdf",
            agency="고용노동부", scope="우선지원대상기업 배우자 출산휴가 급여 2024년 5일 상한",
            variable_role="constraint", value_kind="upper_limit", source_class="official_standard",
            reuse_policy="same_scope", reference_year=2024,
            limitation="2024년 말까지 유효한 상한. 2025~2029년 동일액 지급 가정에는 별도 명시 필요", **common),
    ]
