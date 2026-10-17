"""Official national observations and explicit proxies, not band-specific facts."""
from backend.erce.common_population_evidence import population_series
from backend.erce.reviewed_variable_rows import evidence_row

BASIS="national_2021_2023_average_proxy"


def basic_pension_proxy_rows():
    counts=[5973059,6238798,6508574]
    populations=population_series("age65_population",2021,3)
    payments=[265571,271852,284804];standards=[300000,307500,323180]
    uptake=sum(n/(p*.7) for n,p in zip(counts,populations))/3
    factor=sum(a/b for a,b in zip(payments,standards))/3
    rows=[]
    for band in ("lower30","between30_50"):
        for variable,value,pages,formula in (
            ("pension_take_up",uptake,"PDF11쪽·KOSIS동일버전연앙인구",
             "mean(2021~2023실제수급자/(공식전망65세이상인구×70%))"),
            ("pension_delta_payment_factor",factor,"PDF42쪽 평균연금액·2021~2023기준액",
             "mean(전국평균수령액/해당연도기준액)을증액차액에준용하는후보"),
        ):
            rows.append(evidence_row(evidence_key=f"mohw_pension_2023:{band}:{variable}:proxy",
                variable_key=variable,value=value,unit="ratio",source_bill_no="public:mohw:pension_statistics_2023",
                available_at="2024-12-06",reviewed_at="2026-10-06",
                source_ref=f"보건복지부 통계로본2023년기초연금 {pages}; {formula}",
                source_url="https://www.mohw.go.kr/board.es?mid=a10411010100&bid=0019&act=view&list_no=1483858",
                agency="보건복지부·통계청",policy_domain="기초연금",scope="전국평균2021~2023을소득구간에준용하는후보",
                service_function="basic_pension_staged_increase",variable_role="proxy_assumption",
                support_derivation="basic_pension_staged_increase",pension_income_band=band,
                pension_rate_basis=BASIS,allowed_routes=["transfer_recipient_delta"],
                valid_from_year=2026,valid_to_year=2030,requires_applicability_note=True,
                independently_verified=False,obtained_from="official_observations_derived_proxy",
                historical_years=[2021,2022,2023],observed_recipients=counts,
                denominator_population=populations,observed_mean_payments=payments,
                reference_monthly_amounts=standards,calculation=formula,
                raw_source_file="backend/generated/erce_official_sources/mohw_basic_pension_2023.pdf",
                limitation="전국평균을소득구간별미관측값에준용하는명시적가정후보.평균급여수준비율은기준액인상시한계지급비율과같다고검증되지않음.자동확정·정답역산금지.신규추계에사용전최신버전및대상범위검토"))
    return rows
