"""
KOSIS 변수 자동 조회 모듈

새 변수 추가 방법:
  1. https://kosis.kr 에서 통계표 검색
  2. 표 선택 후 상단 '공유' → 'Open API' 클릭
  3. 표시된 orgId, tblId 복사
  4. KOSIS_MAP 에 항목 추가
"""
import requests
import json

API_KEY = "YjZhMGE3YTNlNThlZmU1ODA2Yjc4YzQwOWY4YTdiM2Y="
BASE_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"

# ── 정부 고시값 (KOSIS에 없는 경우 직접 입력) ─────────────────────────
STATIC_VALUES = {
    "공무원임금상승률": {
        "source": "인사혁신처 공무원보수규정",
        "unit": "%",
        "data": {
            "2020": 0.9, "2021": 0.9, "2022": 1.4,
            "2023": 1.7, "2024": 2.5, "2025": 3.0,
        },
    },
}

# ── KOSIS API 매핑 테이블 ──────────────────────────────────────────────
KOSIS_MAP = {
    "소비자물가상승률": {
        "orgId": "101",
        "tblId": "DT_1J22003",       # 소비자물가지수(2020=100)
        "itmId": "ALL", "objL1": "ALL", "objL2": "",
        "prdSe": "Y",
        "filter": lambda d: d.get("C1") == "T10" and d.get("ITM_ID") == "T",
        "calc": "yoy_rate",
        "unit": "%",
    },
    "명목임금상승률": {
        "orgId": "118",
        "tblId": "DT_118N_LCE0001",  # 고용형태별 임금 및 근로시간
        "itmId": "ALL", "objL1": "ALL", "objL2": "",
        "prdSe": "Y",
        "filter": lambda d: d.get("C1_NM") == "전체근로자" and d.get("ITM_NM") == "월급여액",
        "calc": "yoy_rate",
        "unit": "%",
    },
    "주민등록인구": {
        "orgId": "101",
        "tblId": "DT_1B04005N",      # 행정구역(읍면동)별/5세별 주민등록인구
        "itmId": "T2", "objL1": "00", "objL2": "0",
        "prdSe": "Y",
        "filter": lambda d: d.get("C1") == "00" and d.get("C2") == "0",
        "calc": "direct",
        "unit": "명",
    },
    "65세이상인구": {
        "orgId": "101",
        "tblId": "DT_1B04005N",      # 행정구역(읍면동)별/5세별 주민등록인구
        "itmId": "T2", "objL1": "00", "objL2": "ALL",
        "prdSe": "Y",
        "filter": lambda d: d.get("C1") == "00" and d.get("C2") in {
            "70","75","80","85","90","95","100","105"
        },
        "calc": "sum",
        "unit": "명",
    },
    "영유아인구": {
        "orgId": "101",
        "tblId": "DT_1B04005N",      # 0~4세 (영유아보육법 기준 6세 미만 근사)
        "itmId": "T2", "objL1": "00", "objL2": "ALL",
        "prdSe": "Y",
        "filter": lambda d: d.get("C1") == "00" and d.get("C2") in {"5"},
        "calc": "sum",
        "unit": "명",
    },
    "아동인구": {
        "orgId": "101",
        "tblId": "DT_1B04005N",      # 0~19세 (아동복지법 기준 18세 미만 근사)
        "itmId": "T2", "objL1": "00", "objL2": "ALL",
        "prdSe": "Y",
        "filter": lambda d: d.get("C1") == "00" and d.get("C2") in {"5","10","15","20"},
        "calc": "sum",
        "unit": "명",
    },
    "청년인구": {
        "orgId": "101",
        "tblId": "DT_1B04005N",      # 20~39세 (경기도 청년기본조례 기준 19~39세 근사)
        "itmId": "T2", "objL1": "00", "objL2": "ALL",
        "prdSe": "Y",
        "filter": lambda d: d.get("C1") == "00" and d.get("C2") in {"25","30","35","40"},
        "calc": "sum",
        "unit": "명",
    },
    "등록장애인수": {
        "orgId": "110",
        "tblId": "DT_110001_A045",   # 국민기초생활보장수급자 및 등록장애인
        "itmId": "00", "objL1": "ALL", "objL2": "ALL",
        "objL3": "", "objL4": "", "objL5": "", "objL6": "", "objL7": "", "objL8": "",
        "prdSe": "Y",
        "filter": lambda d: d.get("C1") == "A001" and d.get("C2") == "H005",
        "calc": "direct",
        "unit": "명",
    },
    "기초생활수급자수": {
        "orgId": "110",
        "tblId": "DT_110001_A045",   # 국민기초생활보장수급자 및 등록장애인
        "itmId": "00", "objL1": "ALL", "objL2": "ALL",
        "objL3": "", "objL4": "", "objL5": "", "objL6": "", "objL7": "", "objL8": "",
        "prdSe": "Y",
        "filter": lambda d: d.get("C1") == "A001" and d.get("C2") == "H002",
        "calc": "direct",
        "unit": "명",
    },
}


def _fetch_kosis(cfg: dict, n_years: int = 6) -> list:
    params = {
        "method": "getList",
        "apiKey": API_KEY,
        "orgId": cfg["orgId"],
        "tblId": cfg["tblId"],
        "itmId": cfg["itmId"],
        "objL1": cfg["objL1"],
        "objL2": cfg["objL2"],
        "format": "json",
        "jsonVD": "Y",
        "prdSe": cfg["prdSe"],
        "newEstPrdCnt": str(n_years),
    }
    for key in ("objL3","objL4","objL5","objL6","objL7","objL8"):
        if key in cfg:
            params[key] = cfg[key]
    r = requests.get(BASE_URL, params=params, timeout=15)
    data = r.json()
    if isinstance(data, dict) and "err" in data:
        raise ValueError(f"KOSIS API 오류: {data['errMsg']}")
    return data


def _calc_yoy(rows: list) -> list:
    rows = sorted(rows, key=lambda x: x["PRD_DE"])
    result = []
    for i, row in enumerate(rows):
        year = row["PRD_DE"]
        val = float(row["DT"])
        if i == 0:
            result.append({"year": year, "value": None, "raw": val})
        else:
            prev = float(rows[i - 1]["DT"])
            rate = round((val - prev) / prev * 100, 2)
            result.append({"year": year, "value": rate, "raw": val})
    return result


def _calc_sum(rows: list) -> list:
    from collections import defaultdict
    by_year = defaultdict(float)
    for row in rows:
        by_year[row["PRD_DE"]] += float(row["DT"])
    return [{"year": yr, "value": round(val)} for yr, val in sorted(by_year.items())]


def get_variable(variable_name: str, year: str = None) -> dict:
    """
    변수명과 연도를 입력하면 해당 값을 반환합니다.

    Args:
        variable_name: "소비자물가상승률", "명목임금상승률", "65세이상인구" 등
        year: "2024" 형식. None이면 전체 연도 반환.
    """
    # 1) 정적 고시값
    if variable_name in STATIC_VALUES:
        entry = STATIC_VALUES[variable_name]
        if year:
            val = entry["data"].get(year)
            return {"variable": variable_name, "year": year, "value": val,
                    "unit": entry["unit"], "source": entry["source"]}
        return {"variable": variable_name, "all": entry["data"],
                "unit": entry["unit"], "source": entry["source"]}

    # 2) KOSIS API 조회
    if variable_name not in KOSIS_MAP:
        return {"error": f"'{variable_name}' 은(는) 매핑되지 않은 변수입니다."}

    cfg = KOSIS_MAP[variable_name]
    raw = _fetch_kosis(cfg)
    filtered = [d for d in raw if cfg["filter"](d)]

    if cfg["calc"] == "yoy_rate":
        rows = _calc_yoy(filtered)
    elif cfg["calc"] == "sum":
        rows = _calc_sum(filtered)
    else:
        rows = [{"year": d["PRD_DE"], "value": float(d["DT"])}
                for d in sorted(filtered, key=lambda x: x["PRD_DE"])]

    if year:
        matched = next((r for r in rows if r["year"] == year), None)
        if matched is None and rows:
            matched = max(rows, key=lambda r: r["year"])
            return {"variable": variable_name, "year": matched["year"],
                    "value": matched["value"],
                    "unit": cfg["unit"], "source": f"KOSIS {cfg['tblId']}",
                    "note": f"{year}년 데이터 없음 → {matched['year']}년으로 대체"}
        return {"variable": variable_name, "year": year,
                "value": matched["value"] if matched else None,
                "unit": cfg["unit"], "source": f"KOSIS {cfg['tblId']}"}

    return {"variable": variable_name, "all": rows,
            "unit": cfg["unit"], "source": f"KOSIS {cfg['tblId']}"}


# ── 실행 테스트 ────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_cases = [
        ("소비자물가상승률", "2024"),
        ("명목임금상승률",   "2024"),
        ("공무원임금상승률", "2024"),
        ("주민등록인구",     "2024"),
        ("65세이상인구",     "2025"),
        ("등록장애인수",     "2023"),
        ("기초생활수급자수", "2023"),
    ]

    print("=" * 52)
    print("  KOSIS 변수 자동 조회 테스트")
    print("=" * 52)

    results = {}
    for var, yr in test_cases:
        res = get_variable(var, yr)
        val = res.get("value")
        unit = res.get("unit", "")
        src = res.get("source", "")
        val_str = f"{val:,.0f}" if isinstance(val, float) and val > 1000 else str(val)
        print(f"\n[{var}] {yr}년")
        print(f"  값    : {val_str} {unit}")
        print(f"  출처  : {src}")
        results[var] = res

    with open("lookup_result.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print("\n\nlookup_result.json 저장 완료")
