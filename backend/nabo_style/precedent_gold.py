"""Extract which precedent NABO actually reused, per cost item.

Every "유사사례/준용/참고" sentence in an estimate is labelled with the cost
item type it supports, the kind of source it cites, and the cited name. The
result is a gold set for scoring precedent retrieval (did our top-k contain
what NABO used?) and for measuring how much our corpus can cover.
Run: python3 -m backend.nabo_style.precedent_gold
"""
from __future__ import annotations

import json
import re
from collections import Counter

from backend.nabo_style.reference_miner import ROOT, TEXTS

OUT = ROOT / "generated/nabo_style/precedent_citations.jsonl"

CUE = re.compile(r"유사\s?(?:사례|사업|위원회|기관|용역)|준용|(?:사례|실적)를?\s?(?:참고|참조)")
SPLIT = re.compile(r"(?=[❑◦－])|(?<=[다음함됨임])\.\s")

BOILERPLATE = re.compile(r"^[❑◦－]?\s?(?:본 추계(?: 결과)?는|제정안에 따른 추가재정소요는|개정안에 따른 추가재정소요는|추계 결과,)|"
                         r"(?:유사\s?사례를\s?(?:준용|참고)하여\s?추계)\s*(?:\d|―|$|[^가-힣]{0,6}$)|기술적으로 추계가")

ITEM_TYPES = [  # first match wins; ordered from specific to generic
    ("행사·기념일", r"기념일|기념행사|기념식|의 날|주간|행사"),
    ("조세·감면", r"소득세|법인세|취득세|재산세|부가가치세|세액|감면|비과세|공제"),
    ("위원회", r"위원회|협의체|심의회|자문단|민간위원|참석수당|회의수당"),
    ("기본·종합계획", r"기본계획|종합계획|시행계획|중장기|로드맵"),
    ("실태조사", r"실태조사|조사\s?비용|조사를\s?실시|표본|설문"),
    ("인건비·조직", r"인건비|정원|증원|직급|보수|연봉|사무처|사무국|기본경비"),
    ("정보시스템", r"시스템|전산|플랫폼|정보화|데이터베이스"),
    ("교육·홍보", r"교육|홍보|캠페인|인식개선|연수"),
    ("시설·장비", r"시설|건립|설치|장비|공사|임차"),
    ("기관·센터 운영", r"센터|기관.{0,6}운영|전담기관|지원기관|운영비"),
    ("급여·지원금", r"지원금|수당|급여|장려금|보조금|바우처|지원단가"),
    ("연구용역", r"연구용역|용역"),
]
SOURCE_KINDS = [
    ("NABO 과거추계", r"비용추계서|추계서|의안번호|기존\s?추계|과거\s?추계|국회예산정책처.{0,10}추계"),
    ("감면·집행 실적", r"조세지출|감면실적|지방세지출|집행실적|지급실적|감면액"),
    ("기존 위원회 운영", r"위원회.{0,40}(?:구성|운영|개최|민간위원|실적)|행정기관위원회"),
    ("연구용역 사례", r"연구용역|용역|나라장터|조달"),
    ("부처 기시행 사업", r"(?:기시행|현행|기존)\s?사업|세부사업|사업\s?예산|보조율|국고보조|예산(?:안)?\s?(?:설명|편성)"),
    ("지자체 사례", r"지방자치단체|시·도|특별자치도|광역시|[가-힣]{1,4}시의|[가-힣]{1,4}도의"),
    ("기존 기관·조직 현황", r"소속\s?공무원|직급별\s?(?:정원|보수)|유사\s?기관|기\s?설치|정원.{0,20}(?:사례|준용)|기관의\s?(?:현황|사례)|[가-힣]+(?:부|청|처|원|단)의\s?사례"),
    ("부처 제출·유사사업 사례", r"(?:부|청|처|공단|원)(?:가|이|에서)?\s?제출|제출자료|유사\s?사업|사업비.{0,10}평균|평균\s?(?:사업비|예산)|유사사례의\s?(?:평균|실적)"),
    ("법령·지침 단가", r"규정|지침|고시|기준\s?단가"),
]
NAME = re.compile(r"[「“\"‘']([^」”\"’']{3,60})[」”\"’']")


def _label(table, text):
    for name, pattern in table:
        if re.search(pattern, text):
            return name
    return "기타"


def extract() -> list[dict]:
    rows, seen = [], set()
    for line in TEXTS.open(encoding="utf-8"):
        doc = json.loads(line)
        text = re.sub(r"\s+", " ", doc["text"])
        offset = 0
        for sentence in SPLIT.split(text):
            start = text.find(sentence, offset)
            offset = max(offset, start)
            sentence = sentence.strip()
            if not (20 <= len(sentence) <= 400) or not CUE.search(sentence) or BOILERPLATE.search(sentence):
                continue
            key = (doc["bill_no"], sentence[:120])
            if key in seen:
                continue
            seen.add(key)
            context = text[max(0, start - 250):start] + " " + sentence
            names = [n for n in NAME.findall(sentence) if not n.startswith(("안 제", "제"))]
            rows.append(dict(
                bill_no=doc["bill_no"], bill_name=doc["bill_name"],
                reply_date=max(d for d in (doc["reply_date"], doc.get("propose_date")) if d),  # public date
                item_type=_label(ITEM_TYPES, sentence) if _label(ITEM_TYPES, sentence) != "기타"
                else _label(ITEM_TYPES, context),
                source_kind=_label(SOURCE_KINDS, sentence),
                cited_names=names, sentence=sentence))
    return rows


def main() -> None:
    rows = extract()
    with OUT.open("w", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    bills = {r["bill_no"] for r in rows}
    print(f"citations {len(rows)} in {len(bills)} estimates -> {OUT}")
    print("item_type:", Counter(r["item_type"] for r in rows).most_common())
    print("source_kind:", Counter(r["source_kind"] for r in rows).most_common())


if __name__ == "__main__":
    main()
