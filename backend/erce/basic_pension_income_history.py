"""Checked annual income/household margins, not invented joint benefit records."""
import re
import json
from pathlib import Path
import fitz

from backend.erce.reviewed_variable_rows import evidence_row

SOURCE=Path("backend/generated/erce_official_sources/mohw_basic_pension_2023.pdf")


def extract_income_history():
    with fitz.open(SOURCE) as pdf:
        def chunk(page,year,n):
            text=pdf[page-1].get_text().split(str(year)+"년\n",1)[1]
            end=text.find(str(year+1)+"년")
            text=text[:end] if end>=0 else text.split("대도시")[0]
            values=[int(x.replace(",","")) for x in text.splitlines() if re.fullmatch(r"[0-9][0-9,]*",x)]
            if len(values)<n:raise ValueError("incomplete official income table")
            return values[:n]
        result=[]
        for year,limit,total in ((2021,1690000,5973059),(2022,1800000,6238798),(2023,2020000,6508574)):
            single=chunk(62,year,10)+chunk(63,year,12)
            couple=chunk(64,year,11)+chunk(65,year,11)+chunk(66,year,13)
            if sum(single[1:])!=single[0] or sum(couple[1:])!=couple[0] or single[0]+couple[0]!=total:
                raise ValueError("official income margins do not reconcile")
            result.append(dict(year=year,total_recipients=total,
                single=dict(total=single[0],counts=single[1:],upper_income_bounds=[0]+list(range(100000,1900001,100000))+[2020000],actual_selection_limit=limit),
                couple=dict(total=couple[0],counts=couple[1:],upper_income_bounds=[0]+list(range(100000,3200001,100000))+[3232000],actual_selection_limit=round(limit*1.6))))
        return result


def income_history_row(history):
    return evidence_row(evidence_key="mohw_pension_2023:income_household_history:2021-2023",
        variable_key="pension_income_household_history",value=history,unit="income_household_history",
        source_bill_no="public:mohw:pension_statistics_2023",available_at="2024-12-06",reviewed_at="2026-10-06",
        source_ref="보건복지부 통계로본2023년기초연금 PDF62~66쪽 가구유형별소득인정액분포",
        source_url="https://www.mohw.go.kr/board.es?mid=a10411010100&bid=0019&act=view&list_no=1483858",
        agency="보건복지부",policy_domain="기초연금",scope="전국2021~2023단독/부부가구소득분포",
        service_function="historical_pension_income_household_margins",variable_role="historical_distribution",
        source_class="official_standard",independently_verified=True,requires_applicability_note=True,
        pension_history_usage="historical_distribution_only",observation_years=[2021,2022,2023],
        limitation="소득구간단독/부부가구합계만확보.부부1인/2인·국민연금연계·실제지급액까지결합한교차자료아님.표시구간끝값은2023표기이며실제연도선정한도별도보존.구간내순위배분이나가구소득정규화자동가정금지")


def basic_pension_income_rows():
    path=Path(__file__).parent/"data/basic_pension_income_household_2021_2023.json"
    row=json.loads(path.read_text())
    for r in row["value"]:
        for kind in ("single","couple"):
            h=r[kind]
            if len(h["counts"])!=len(h["upper_income_bounds"]) or sum(h["counts"])!=h["total"]:
                raise ValueError("cached pension income table does not reconcile")
        if r["single"]["total"]+r["couple"]["total"]!=r["total_recipients"]:
            raise ValueError("cached pension recipient sum mismatch")
    return [row]
