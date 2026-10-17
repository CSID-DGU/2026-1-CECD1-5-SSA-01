"""Partial independently sourced recipient age history; no missing-year fill."""
from backend.erce.reviewed_variable_rows import evidence_row


def disability_recipient_history_rows():
    rows=[]
    for key,value,groups in (
        ("historical_disability_age18_64",225337,dict(home=112635,near_poor=15196,above_near_poor=75648,facility=21858)),
        ("historical_disability_age65plus",139375,dict(home=33971,near_poor=19343,above_near_poor=80164,facility=5897)),
    ):
        rows.append(evidence_row(evidence_key=f"nabo_public_assistance_2019:{key}:2018",
            variable_key=key,value=value,unit="person",source_bill_no="public:nabo:33315795",
            available_at="2026-10-06",reviewed_at="2026-10-06",
            source_ref="국회예산정책처 공공부조제도의 현안 및 재정소요 추계 PDF65쪽(본문41쪽) 연령·유형별2018수급자",
            source_url="https://nabo.go.kr/board/file/down.do?fid=33315795",
            agency="국회예산정책처·보건복지부",policy_domain="장애인연금",
            scope="전국2018년연말 장애인연금수급자",service_function="historical_disability_recipient_age",
            variable_role="historical_actual",value_years=[2018],observation_year=2018,
            obtained_from="official_public_report",independently_verified=True,
            component_counts=groups,total_recipients_2018=364712,
            limitation="2018실측분류만확보.2019~2022평균으로전용·연도복사금지.보고서정확공개일별도미확인으로자료이용가능일은확인일"))
    return rows
