"""Blind NABO-style estimate for bill 2203602 (기초연금법 일부개정법률안, 주호영의원 등 14인).

Only sources public on/before 2024-09-03. Run from project root:
  python3 docs/nabo_style/compare_2203602/nabo_blind_calc.py
"""
import json
from pathlib import Path

OUT = Path(__file__).parent
YEARS = [2025, 2026, 2027, 2028, 2029, 2030]

V = {}  # variable registry


def var(name, value, unit, as_of, source, published_at, ref, grade, note=""):
    V[name] = dict(name=name, value=value, unit=unit, as_of=as_of, source=source,
                   published_at=published_at, ref=ref, grade=grade, note=note)
    return value


pop65 = var("pop65", {2025: 10513907, 2026: 11125016, 2027: 11597067, 2028: 12125349,
                      2029: 12521322, 2030: 12980219}, "명", "연도별(중위추계)",
            "통계청 「장래인구추계: 2022~2072년」 중위추계 65세 이상 인구", "2023-12-14",
            "ledger erce:kosis_202312:age65_population:total:2026-2030:common / https://kosis.kr", "공식통계")
base_2024 = var("base_pension_2024", 334810, "원/월", "2024-01-01",
                "보건복지부 「2024년 기초연금 기준연금액 고시」(단독가구 기준연금액)", "2024-01 (고시)",
                "ledger erce:mohw:disability_basic_monthly:2024 (기초급여 기준액=기준연금액 동일) / https://www.mohw.go.kr",
                "공식통계")
cpi = var("cpi", {2024: 0.026, 2025: 0.022, 2026: 0.022, 2027: 0.021, 2028: 0.021, 2029: 0.021, 2030: 0.020},
          "연간 상승률", "NABO 전망(2024년 하반기 인용분)",
          "국회예산정책처 소비자물가상승률 전망(타 법안 비용추계서 인용)", "2024-07-24",
          "ledger nabo_support:2202164:13 (2024~2030), nabo_support:2201110:11 (2024-08-23 동일값)", "NABO인용",
          "2024년 값(2.6%)은 2025년 기준연금액 조정에 쓰이는 전망치 — 실적 미확정(기준일 이전)")
legal_special = var("special_base_amount", {"<=30%:2026": 400000, "<=50%:2027": 400000}, "원/월", "법안",
                    "개정안 제5조의2제1항제1호·제2호", "2024-09-03", "bill_text.pdf p.3", "법안명시")
recip_rate = var("take_up_vs_70pct", round(0.675 / 0.70, 4), "비율", "2022년말",
                 "보건복지부 기초연금 통계(2022): 수급률 67.5% ÷ 선정목표 70%", "2023 (공개일 추정, 확인 필요)",
                 "보건복지부 「2022년 기초연금 통계」(수급자 623.8만명, 65세 이상 925.0만명)", "공식통계",
                 "소득구간별 수급률 자료가 없어 하위30%·50% 구간에도 동일 적용(가정)")
couple2_share = var("couple_both_share", round(2694 / 6238, 4), "비율", "2022년말",
                    "보건복지부 기초연금 통계(2022): 부부 2인 수급자 269.4만명 ÷ 전체 623.8만명",
                    "2023 (공개일 추정, 확인 필요)", "보건복지부 「2022년 기초연금 통계」", "공식통계",
                    "부부 2인 수급 시 각 20% 감액(법 제8조①). 하위 구간에도 동일 비율 가정")
couple_cut = var("couple_reduction", 0.20, "비율", "현행법", "기초연금법 제8조제1항", "현행법",
                 "기초연금법 제8조①", "법안명시")
ns = var("national_share", 0.8276, "비율", "2024년 예산",
         "평균 국고보조율 82.76%(2024년 예산기준) — NABO 추계서 인용값", "2024-02-06",
         "NABO 24C0078 (의안 2126323, 생계급여-기초연금 동시수급자 추계)", "NABO인용",
         "해당 추계서는 기초연금액 관련 추계에 적용. 기초연금 자체 보조율로 동일 가정")
var("start_year", 2026, "연도", "가정", "부칙 제1조(공포 후 1년) + 개정조문이 2026·2027년 금액 명시", "-", "-", "가정",
    "2024년 말~2025년 중 공포 시 2025년 하반기~2026년 시행 → 금액 조항은 2026.1.부터 적용, 추계기간 2026~2030")
var("post2027_indexing", "CPI", "-", "가정",
    "2028년 이후 특례 기준연금액(40만원)도 제5조제3항(전년도 물가변동률 반영) 방식으로 조정된다고 가정", "-", "-", "가정",
    "민감도: 40만원 명목 고정 시 결과 별도 제시")

# 현행법 기준연금액 경로: t년 = (t-1)년 × (1 + CPI_{t-1})
base = {2024: base_2024}
for y in range(2025, 2031):
    base[y] = round(base[y - 1] * (1 + cpi[y - 1]))


def special_path(index=True):
    s30, s50 = {}, {}
    for y in YEARS:
        if y == 2026:
            s30[y] = 400000
        elif y == 2027:
            s30[y] = s50[y] = 400000
        elif y >= 2028:
            s30[y] = s50[y] = round(s30[y - 1] * (1 + cpi[y - 1])) if index else 400000
    return s30, s50


pay_factor = 1 - couple_cut * couple2_share  # 부부감액 반영 평균 지급비율


def run(index=True):
    s30, s50 = special_path(index)
    res = {}
    for y in YEARS:
        n30 = pop65[y] * 0.30 * recip_rate
        n3050 = pop65[y] * 0.20 * recip_rate
        d30 = max(0, s30.get(y, base[y]) - base[y])
        d3050 = max(0, s50.get(y, base[y]) - base[y])
        c30 = n30 * d30 * 12 * pay_factor
        c3050 = n3050 * d3050 * 12 * pay_factor
        tot = c30 + c3050
        res[y] = dict(baseline_monthly=base[y], special_monthly_le30=s30.get(y), special_monthly_30_50=s50.get(y),
                      recipients_le30=round(n30) if d30 else 0, recipients_30_50=round(n3050) if d3050 else 0,
                      monthly_increment_le30=d30, monthly_increment_30_50=d3050,
                      cost_le30=round(c30), cost_30_50=round(c3050), total=round(tot),
                      national=round(tot * ns), local=round(tot * (1 - ns)))
    return res


main = run(True)
alt = run(False)
total = sum(r["total"] for r in main.values())

clauses = [
    dict(id="안 제3조제3항", quote="제1항에도 불구하고 대통령령으로 정하는 사람 중 19세 이후 국내에 7년 이상 거주하지 아니한 사람에게는 기초연금을 지급하지 아니한다.", effect="지출 감소(수급 제외)"),
    dict(id="안 제5조의2제1항", quote="제5조제2항 전단에도 불구하고 65세 이상인 사람 중 소득인정액이 일정비율 이하인 사람에게 적용하는 기준연금액은 다음 각 호의 구분에 따른다. 1. 소득인정액이 100분의 30 이하인 사람에 대한 2026년의 기준연금액: 40만원 2. 소득인정액이 100분의 50 이하인 사람에 대한 2027년의 기준연금액: 40만원", effect="지출 증가(추계)"),
    dict(id="안 제10조제3항", quote="기초연금 수급희망자와 그 배우자는 제1항에 따른 신청을 할 때 국외에 소득 또는 재산을 보유한 경우에는 이를 신고하여야 한다.", effect="행정절차(재정영향 미미/추정곤란)"),
    dict(id="법률 제16868호 부칙 제2조 삭제", quote="법률 제16868호 기초연금법 일부개정법률 부칙 제2조를 삭제한다.", effect="제5조의2 유효기간(2020.12.31.) 삭제 — 특례 상시화, 독립 재정효과 없음(제5조의2 개정효과에 포함)"),
    dict(id="부칙 제1조", quote="이 법은 공포 후 1년이 경과한 날부터 시행한다.", effect="추계기간 결정"),
]
not_estimated = [
    dict(id="안 제3조제3항", reason="적용대상('대통령령으로 정하는 사람', 예: 복수국적자·장기 해외거주 후 입국자)이 하위법령에 위임되어 있고, 19세 이후 국내 거주기간 7년 미만인 65세 이상 신규 신청자 수에 관한 공개 자료가 없음. 부칙 제2조에 따라 시행 후 최초 신청자부터 적용되므로 기존 수급자 영향 없음. 재정 감소요인이나 규모 추정 곤란"),
    dict(id="안 제10조제3항", reason="국외 소득·재산 신고의무 신설은 신청절차 규정으로 직접 지출을 수반하지 않음. 신고에 따른 부정수급 감소(지출 절감) 효과는 국외 보유 소득·재산 규모 자료가 없어 추정 곤란"),
    dict(id="소득역전방지 감액(현행 제8조제3항)·국민연금 연계감액(제5조·제6조)", reason="40만원 특례 경계구간(30%·50% 부근) 수급자의 감액 및 국민연금 연계감액은 소득구간별 미시자료가 없어 반영하지 못함 → 본 추계는 과대 가능성"),
    dict(id="행정비용(시스템 개편 등)", reason="기존 기초연금 전산 내 기준연금액 구분 적용으로 처리 가능하다고 보아 제외"),
]
formula = ("추가재정소요_t = Σ_g [ 65세이상인구_t × 구간비율_g × (수급률/70%) × (특례기준연금액_g,t − 현행기준연금액_t) × 12 × (1 − 0.2 × 부부2인수급자비율) ], "
           "g ∈ {하위30%(2026~), 30~50%(2027~)}; 현행기준연금액_t = 기준연금액_{t-1} × (1+CPI_{t-1}); 2028~ 특례액도 CPI 연동(가정); 국비 = 총액 × 82.76%")
out = dict(bill_no="2203602", bill_name="기초연금법 일부개정법률안(주호영의원 등 14인)", propose_date="2024-09-03",
           cutoff="2024-09-03", estimation_period="2026~2030 (2025년 재정소요 0)",
           clauses=clauses, not_estimated=not_estimated, formula=formula,
           derived=dict(baseline_monthly_path=base, pay_factor=round(pay_factor, 4)),
           variables=list(V.values()), results_by_year_won=main, total_2026_2030_won=total,
           total_national_won=sum(r["national"] for r in main.values()),
           total_local_won=sum(r["local"] for r in main.values()),
           sensitivity_fixed_400k_after_2027=dict(by_year={y: r["total"] for y, r in alt.items()},
                                                  total=sum(r["total"] for r in alt.values())),
           answer_exposure="없음 — 금지 파일·NABO 24C3532 결과를 열람하지 않음")
(OUT / "nabo_blind_run.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
for y, r in main.items():
    print(y, r)
print("TOTAL", total, "alt", out["sensitivity_fixed_400k_after_2027"])
