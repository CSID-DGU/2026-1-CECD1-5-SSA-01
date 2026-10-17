"""Versioned official age/sex population stock, reusable across ERCE profiles."""
import json
from pathlib import Path

from backend.erce.reviewed_variable_rows import evidence_row

POPULATION_FILE = Path(__file__).parent / "data/kosis_population_202312_2017_2030.json"
COHORTS = {
    "total_population":(0,101), "under18_population":(0,18),
    "under8_population":(0,8), "under13_population":(0,13), "age0_population":(0,1), "age1_population":(1,2),
    "adult_population":(18,101), "age18_64_population":(18,65), "age65_population":(65,101),
}


def single_age_population_matrix(age_min,age_max,start_year,years):
    """Reuse the stored official vintage without broadening a benefit's age scope."""
    if any(isinstance(x,bool) or not isinstance(x,int) for x in (age_min,age_max,start_year,years)) or not 0<=age_min<=age_max<=100 or years<1:
        raise ValueError("invalid single-age population scope")
    records={r["year"]:r for r in json.loads(POPULATION_FILE.read_text())["years"]}
    supplement=json.loads(POPULATION_FILE.with_name("kosis_population_2031_202312.json").read_text())
    if supplement.get("vintage")!="2023-12" or supplement.get("scenario")!="222":
        raise ValueError("population supplement vintage mismatch")
    records[2031]=supplement
    out={str(age):[] for age in range(age_min,age_max+1)}
    for year in range(start_year,start_year+years):
        if year not in records:raise ValueError("population year outside stored vintage")
        row=records[year]
        if len(row["male"])!=101 or len(row["female"])!=101:raise ValueError("incomplete single-age population")
        for age in range(age_min,age_max+1):
            vals=[row["male"][age],row["female"][age]]
            if any(isinstance(x,bool) or not isinstance(x,int) or x<0 for x in vals):raise ValueError("invalid population")
            out[str(age)].append(sum(vals))
    return out


def population_series(variable, start_year, years, sex="total"):
    if variable not in COHORTS or sex not in {"total","male","female"}:
        raise ValueError("unsupported population cohort or sex")
    if isinstance(start_year,bool) or isinstance(years,bool) or years<1:
        raise ValueError("invalid population period")
    data=json.loads(POPULATION_FILE.read_text())
    records={r["year"]:r for r in data["years"]}
    extra_path=Path(__file__).parent/"data/kosis_population_2031_202312.json"
    if extra_path.exists():
        extra=json.loads(extra_path.read_text())
        if extra.get("year")!=2031 or extra.get("vintage")!="2023-12" or extra.get("scenario")!="222":
            raise ValueError("population supplement vintage mismatch")
        records[2031]=extra
    low,high=COHORTS[variable];values=[]
    for year in range(start_year,start_year+years):
        if year not in records:raise ValueError("population year outside stored vintage")
        r=records[year]
        if len(r["male"])!=101 or len(r["female"])!=101:
            raise ValueError("incomplete age data")
        counts=[a+b for a,b in zip(r["male"],r["female"])] if sex=="total" else r[sex]
        if any(isinstance(v,bool) or not isinstance(v,int) or v<0 for v in counts):
            raise ValueError("invalid official population count")
        values.append(sum(counts[low:high]))
    return values


def common_population_rows():
    rows=[]
    for start,years in ((2025,5),(2019,5),(2017,7),(2027,5),(2026,5)):
        for variable,(low,high) in COHORTS.items():
            for sex in ("total","male","female"):
                rows.append(evidence_row(
                    evidence_key=f"kosis_202312:{variable}:{sex}:{start}-{start+years-1}:common",
                    variable_key=variable,value=population_series(variable,start,years,sex),unit="person",
                    source_bill_no="official:kosis:DT_1BPA001:202312",available_at="2023-12-14",
                    source_ref="KOSIS 성·연령별 추계인구 전국 DT_1BPA001, 중위시나리오222,2023.12버전",
                    source_url="https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1BPA001",
                    agency="통계청",policy_domain="공통인구",scope=f"전국 {low}세~{high-1 if high<101 else '100세이상'} {sex}",
                    service_function="official_population_stock",variable_role="population",
                    source_class="official_standard",reviewed_at="2026-10-06",
                    value_years=list(range(start,start+years)),population_geography="전국",
                    statistical_sex=sex,population_vintage="2023-12",population_age_min=low,
                    population_age_max=high-1,last_age_is_open_ended=high==101,
                    independently_verified=True,requires_applicability_note=True,
                    obtained_from="official_public_data",raw_data_file=str(POPULATION_FILE),
                    refresh_policy="새 발표버전 별도적재; 정답재현은 당시버전, 신규추계는 적용가능한 최신버전 검토",
                    limitation="7월1일 내국인·외국인 포함 추계인구. 주민등록인구·연금수급자수와다름.2023.12버전이며최신2026관측치아님"))
    return rows
