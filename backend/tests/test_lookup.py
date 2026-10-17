"""
kosis_lookup.py 테스트
"""
from kosis_lookup import get_variable

PASS = "✅ PASS"
FAIL = "❌ FAIL"

results = []

def check(desc, result, expect_key, expect_val=None, expect_none=False):
    val = result.get(expect_key)
    if expect_none:
        ok = val is None
    elif expect_val is not None:
        ok = val == expect_val
    else:
        ok = val is not None
    status = PASS if ok else FAIL
    print(f"{status} {desc}")
    if not ok:
        print(f"     기대값: {expect_val if not expect_none else None}")
        print(f"     실제값: {val}")
    results.append(ok)


print("=" * 55)
print("  케이스 1: 정상 조회")
print("=" * 55)

r = get_variable("소비자물가상승률", "2024")
check("소비자물가상승률 2024년 값 존재", r, "value")
check("소비자물가상승률 2024년 단위 = %", r, "unit", "%")
print(f"     → {r.get('value')}%\n")

r = get_variable("명목임금상승률", "2024")
check("명목임금상승률 2024년 값 존재", r, "value")
print(f"     → {r.get('value')}%\n")

r = get_variable("공무원임금상승률", "2024")
check("공무원임금상승률 2024년 값 존재", r, "value")
check("출처가 고시값", r, "source", "인사혁신처 공무원보수규정")
print(f"     → {r.get('value')}%\n")

r = get_variable("주민등록인구", "2024")
check("주민등록인구 2024년 값 존재", r, "value")
print(f"     → {int(r.get('value')):,}명\n")

r = get_variable("65세이상인구", "2025")
check("65세이상인구 2025년 값 존재", r, "value")
print(f"     → {int(r.get('value')):,}명\n")

r = get_variable("등록장애인수", "2023")
check("등록장애인수 2023년 값 존재", r, "value")
print(f"     → {int(r.get('value')):,}명\n")

r = get_variable("기초생활수급자수", "2023")
check("기초생활수급자수 2023년 값 존재", r, "value")
print(f"     → {int(r.get('value')):,}명\n")


print("=" * 55)
print("  케이스 2: 없는 연도 → None 반환")
print("=" * 55)

r = get_variable("소비자물가상승률", "1990")
check("없는 연도 → value=None", r, "value", expect_none=True)
print(f"     → {r.get('value')}\n")


print("=" * 55)
print("  케이스 3: 없는 변수명 → error 반환")
print("=" * 55)

r = get_variable("존재하지않는변수", "2024")
check("없는 변수명 → error 키 존재", r, "error")
print(f"     → {r.get('error')}\n")


print("=" * 55)
print("  케이스 4: 연도 미입력 → 전체 연도 반환")
print("=" * 55)

r = get_variable("소비자물가상승률")
check("연도 없이 호출 → all 키 존재", r, "all")
all_data = r.get("all", [])
check("전체 연도가 2개 이상", {"cnt": len(all_data)}, "cnt") if False else None
ok = len(all_data) >= 2
print(f"  {'✅ PASS' if ok else '❌ FAIL'} 전체 연도 {len(all_data)}개 반환")
results.append(ok)
for row in all_data:
    print(f"     {row.get('year')}년: {row.get('value')}%")


print()
print("=" * 55)
total = len(results)
passed = sum(results)
print(f"  결과: {passed}/{total} 통과 {'✅ 전체 통과!' if passed == total else '❌ 일부 실패'}")
print("=" * 55)
