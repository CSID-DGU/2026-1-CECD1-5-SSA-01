"""What an analyst reads off a bill before looking for precedents.

- law: the amended act's name (same-law past estimates are the first place to look)
- ministry: the competent ministry, matched against a canonical list
- targets: concrete names created or referenced in the clauses, per item type
  (○○위원회, ○○기본계획, ○○실태조사, ○○센터 ...)
"""
from __future__ import annotations

import json
import re
from collections import Counter
from functools import lru_cache

import fitz

from backend.nabo_style.reference_miner import ROOT

BILLS = ROOT / "generated/assembly_22_pdfs/by_bill"
CACHE = ROOT / "generated/nabo_style/bill_features.json"

MINISTRIES = (
    "기획재정부", "재정경제부", "기획예산처", "교육부", "과학기술정보통신부", "외교부", "통일부", "법무부",
    "국방부", "행정안전부", "국가보훈부", "문화체육관광부", "농림축산식품부", "산업통상자원부", "산업통상부",
    "보건복지부", "환경부", "기후에너지환경부", "고용노동부", "여성가족부", "성평등가족부", "국토교통부",
    "해양수산부", "중소벤처기업부", "인사혁신처", "법제처", "식품의약품안전처", "국세청", "관세청", "조달청",
    "통계청", "국가데이터처", "경찰청", "소방청", "산림청", "특허청", "지식재산처", "기상청", "질병관리청",
    "농촌진흥청", "문화재청", "국가유산청", "해양경찰청", "병무청", "방위사업청", "재외동포청", "우주항공청",
    "행정중심복합도시건설청", "새만금개발청", "금융위원회", "공정거래위원회", "원자력안전위원회",
    "개인정보보호위원회", "방송통신위원회", "방송미디어통신위원회", "국민권익위원회", "국무조정실",
    "국가인권위원회", "감사원", "대법원", "법원행정처", "국회사무처", "중앙선거관리위원회",
)
TARGET_PATTERNS = {
    "위원회": r"[가-힣·ㆍ]{2,30}(?:위원회|협의체|협의회|심의회|자문단)",
    "기본·종합계획": r"[가-힣·ㆍ]{2,30}(?:기본계획|종합계획|시행계획)",
    "실태조사": r"[가-힣·ㆍ]{2,30}(?:실태조사|현황조사)",
    "기관·센터 운영": r"[가-힣·ㆍ]{2,30}(?:센터|진흥원|전담기관|지원기관)",
    "교육·홍보": r"[가-힣·ㆍ]{2,30}(?:교육|홍보|인식개선)",
    "행사·기념일": r"[가-힣·ㆍ]{2,20}(?:의\s?날|주간)",
}
_LEAD = re.compile(r"^.*(?:하기위하여|위하여|소속으로|에관한|에따른|에따라|으로|에서|에게|에|의|를|을|는|은|및|과|와)(?=[가-힣])")
_GENERIC = re.compile(r"^(?:이|그|해당|각|다음|관계|소관|위|동|같은|이하|및|또는|등)")
_SUFFIX = re.compile(r"\s*(?:일부개정법률안|전부개정법률안|폐지법률안|법률안|안)$")


def law_name(bill_name: str) -> str:
    return re.sub(r"\s+", "", _SUFFIX.sub("", bill_name or ""))


def _extract(bill_no: str) -> dict:
    try:
        raw = "".join(p.get_text() for p in fitz.open(BILLS / bill_no / "bill_text.pdf"))
    except Exception:
        return {"ministry": "", "targets": {}}
    text = re.sub(r"\s+", "", raw)
    counts = Counter({m: text.count(m) for m in MINISTRIES if m in text})
    targets = {}
    for item, pattern in TARGET_PATTERNS.items():
        names = Counter(_LEAD.sub("", n) for n in re.findall(pattern, text))
        names = Counter({n: c for n, c in names.items() if not _GENERIC.match(n) and len(n) >= 5})
        targets[item] = [n for n, _ in names.most_common(3)]
    return {"ministry": counts.most_common(1)[0][0] if counts else "", "targets": targets}


@lru_cache(maxsize=1)
def _cache() -> dict:
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def features(bill_no: str) -> dict:
    cache = _cache()
    if bill_no not in cache:
        cache[bill_no] = _extract(bill_no)
    return cache[bill_no]


def save_cache() -> None:
    CACHE.write_text(json.dumps(_cache(), ensure_ascii=False), encoding="utf-8")
