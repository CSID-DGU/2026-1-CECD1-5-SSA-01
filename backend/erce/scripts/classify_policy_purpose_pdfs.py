"""Add a separate, conservative policy-purpose view of 22nd Assembly PDFs.

The existing seven cost-nature category folders and metadata are never changed.
These are unreviewed, multi-label *candidate* tags based on the bill title and
the first pages of its cost estimate, not ERCE formula routes or gold labels.
Only development_manifest.jsonl is read; the reserved validation holdout stays
outside this derived view.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re

import fitz


SOURCE = Path(__file__).resolve().parents[2] / "generated/assembly_22_pdfs"
OUTPUT_NAME = "by_policy_purpose_v1"

# The excerpt supplied by the user covers only these three expenditure groups.
# Do not force tax/revenue-only or unrelated measures into one of them.
TAXONOMY = {
    "조직구성_행정지원": (
        "조직신설_확대", "위원회_협의회", "정보시스템", "기타행정지원"),
    "사회보장_교육지원": (
        "사회보장급여", "사회보험", "보상", "교육지원"),
    "사업진흥_기반조성": (
        "재정지원", "서비스지원", "건설"),
}

INDUSTRY = re.compile(
    r"산업|기업|소상공인|중소기업|창업|벤처|상공인|농어업|농업|어업|임업|"
    r"농어민|농촌|어촌|마을기업|사회적기업|관광|물류|특구|지역개발|"
    r"도시개발|산업단지|지역경제|발명진흥"
)
REVENUE_LAW = re.compile(
    r"조세특례제한법|지방세특례제한법|소득세법|법인세법|부가가치세법|"
    r"상속세 및 증여세법|종합부동산세법|지방세법|관세법|개별소비세법"
)
TITLE_SUBTYPES = {
    ("사회보장_교육지원", "사회보장급여"): re.compile(
        r"아동수당|농어민수당|기초연금|기초생활보장|참전유공자|국가유공자|"
        r"보훈보상대상자|장애인활동 지원|아이돌봄 지원|양육비 대지급|청소년복지지원"
    ),
    ("사회보장_교육지원", "사회보험"): re.compile(
        r"국민건강보험|고용보험|산업재해보상보험|국민연금|사회보험|노인장기요양보험"
    ),
    ("사회보장_교육지원", "교육지원"): re.compile(
        r"장학재단|장학금|학자금|무상교육|무상급식|교육급여|교육비 지원"
    ),
}

RULES = {
    ("조직구성_행정지원", "조직신설_확대"): (
        r"(?:행정기관|지원기관|법원|사무소|센터|본부|부서|전담조직|지원단|전담기구).{0,18}(?:신설|설치|확대|증원)",
        r"(?:신설|설치|확대|증원).{0,18}(?:행정기관|지원기관|법원|사무소|센터|본부|부서|전담조직|공무원|지원인력)",
    ),
    ("조직구성_행정지원", "위원회_협의회"): (
        r"(?:위원회|협의회|협의체).{0,20}(?:신설|설치|구성|운영|회의|수당)",
        r"(?:신설|설치|구성|운영|회의|수당).{0,20}(?:위원회|협의회|협의체)",
    ),
    ("조직구성_행정지원", "정보시스템"): (
        r"(?:정보시스템|전산시스템|전산망|정보망|통합플랫폼|데이터베이스).{0,24}(?:구축|개발|운영|유지|고도화)",
        r"(?:구축|개발|운영|유지|고도화).{0,24}(?:정보시스템|전산시스템|전산망|정보망|통합플랫폼|데이터베이스)",
    ),
    ("조직구성_행정지원", "기타행정지원"): (
        r"(?:기본계획|종합계획|실태조사|현황조사).{0,24}(?:수립|실시|용역|비용|예산)",
        r"(?:수립|실시|용역).{0,24}(?:기본계획|종합계획|실태조사|현황조사)",
    ),
    ("사회보장_교육지원", "사회보장급여"): (
        r"(?:기초생활|생계급여|아동수당|농어민수당|기초연금|양육비|아이돌봄|장애인활동|노인장기요양|참전명예수당|"
        r"보훈급여|사회보장급여|자립정착금|의료급여|돌봄급여|복지급여).{0,28}(?:지급|지원|인상|확대|감면|면제|급여)",
        r"(?:지급|지원|인상|확대|감면|면제).{0,28}(?:기초생활|생계급여|아동수당|농어민수당|기초연금|양육비|아이돌봄|"
        r"장애인활동|참전명예수당|보훈급여|사회보장급여|자립정착금|의료급여|돌봄급여)",
    ),
    ("사회보장_교육지원", "사회보험"): (
        r"(?:건강보험|고용보험|산재보험|국민연금|사회보험).{0,35}(?:급여|보험료(?:의)?(?: 일부를)? 지원|국고지원|재정지원|보조)",
        r"(?:급여|보험료(?:의)?(?: 일부를)? 지원|국고지원|재정지원|보조).{0,24}(?:건강보험|고용보험|산재보험|국민연금|사회보험)",
    ),
    ("사회보장_교육지원", "보상"): (
        r"(?:손실보상|피해보상|재해보상|피해배상|보상금|배상금).{0,20}(?:지급|지원|확대|신설|비용)",
        r"(?:지급|지원|확대|신설).{0,20}(?:손실보상|피해보상|재해보상|피해배상|보상금|배상금)",
    ),
    ("사회보장_교육지원", "교육지원"): (
        r"(?:무상교육|무상급식|교육급여|교육비|학자금|장학금|국가장학금|학교급식).{0,24}(?:지원|지급|확대|면제|감면|신설)",
        r"(?:지원|지급|확대|면제|감면|신설).{0,24}(?:무상교육|무상급식|교육급여|교육비|학자금|장학금|학교급식)",
    ),
    ("사업진흥_기반조성", "재정지원"): (
        r"(?:기업|사업자|농어업인|산업|지역주민).{0,80}(?:보조금|융자|출연금|재정적 지원|재정지원|사업비 지원)",
        r"(?:보조금|융자|출연금|재정적 지원|재정지원|사업비 지원).{0,30}(?:기업|사업자|농어업인|산업|지역주민)",
    ),
    ("사업진흥_기반조성", "서비스지원"): (
        r"(?:컨설팅|법률자문|전문적 자문|역량강화|판로지원|기술개발|연구개발|직업훈련|교육 훈련).{0,30}(?:지원|사업|비용|예산)",
        r"(?:지원|사업|비용|예산).{0,30}(?:컨설팅|법률자문|전문적 자문|역량강화|판로지원|기술개발|연구개발|직업훈련|교육 훈련)",
    ),
    ("사업진흥_기반조성", "건설"): (
        r"(?:부지매입|부지매수|기반시설|시설건립|시설조성|공사비|설계비|건설비).{0,25}(?:지원|설치|건설|조성|사업|비용|예산)",
        r"(?:지원|설치|건설|조성|사업).{0,25}(?:부지매입|기반시설|시설건립|시설조성|공사비|설계비|건설비)",
    ),
}
COMPILED = {key: tuple(re.compile(pattern) for pattern in patterns)
            for key, patterns in RULES.items()}


def _text(path: Path, pages: int = 3) -> str:
    with fitz.open(path) as pdf:
        return re.sub(r"\s+", " ", " ".join(page.get_text() for page in pdf[:pages]))


def classify(title: str, cost_text: str) -> list[dict]:
    """Return only rule-supported subtype candidates, possibly multiple."""
    title = re.sub(r"\s+", " ", title)
    # Cost-estimate opening pages contain the fiscal factors; title alone is
    # insufficient for multi-component bills, but a body-only match is weak.
    matches = []
    for (group, subtype), patterns in COMPILED.items():
        title_hits = [match.group() for pattern in patterns
                      if (match := pattern.search(title))]
        if title_rule := TITLE_SUBTYPES.get((group, subtype)):
            if match := title_rule.search(title):
                title_hits.append(match.group())
        body_hits = [match.group() for pattern in patterns
                     if (match := pattern.search(cost_text))]
        if not title_hits and not body_hits:
            continue
        if group == "사업진흥_기반조성" and not INDUSTRY.search(title):
            # A court building or a benefit recipient is not automatically an
            # industry-promotion/construction bill just because it has a cost.
            continue
        matches.append({"group": group, "subtype": subtype,
                        "score": 3 * len(title_hits) + len(body_hits),
                        "title_match": title_hits[:2], "cost_match": body_hits[:2]})
    return sorted(matches, key=lambda item: (-item["score"], item["group"], item["subtype"]))


def build(source: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite an existing classification: {output}")
    manifest = source / "development_manifest.jsonl"
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line]
    output.mkdir(parents=True)
    counts = Counter()
    results = []
    for row in rows:
        if row.get("status") != "complete":
            continue
        bill_no = row["bill_no"]
        bill_dir = source / "by_bill" / bill_no
        if not all((bill_dir / name).is_file() for name in ("bill_text.pdf", "cost_estimate.pdf")):
            continue
        try:
            cost_text = _text(bill_dir / "cost_estimate.pdf")
        except Exception as exc:
            matches = []
            issue = f"pdf_read_error: {type(exc).__name__}"
        else:
            matches = classify(str(row.get("bill_name") or ""), cost_text)
            issue = "" if matches else (
                "revenue_law_outside_supplied_expenditure_excerpt"
                if REVENUE_LAW.search(str(row.get("bill_name") or ""))
                else "outside_excerpt_or_ambiguous")
        tags = sorted({match["group"] for match in matches})
        status = "candidate" if matches else (
            "out_of_scope" if issue == "revenue_law_outside_supplied_expenditure_excerpt"
            else "review_required")
        result = {"bill_no": bill_no, "bill_name": row.get("bill_name"),
                  "source_bill_dir": str(bill_dir.relative_to(source)),
                  "status": status, "issue": issue, "policy_groups": tags,
                  "policy_subtypes": matches,
                  "method": "title_and_first_3_cost_estimate_pages_regex_v1",
                  "reviewed": False}
        results.append(result)
        locations = {(match["group"], match["subtype"]) for match in matches}
        if not locations:
            locations = {("90_수입법안_제시범위밖", "") if status == "out_of_scope"
                         else ("99_분류검토", "")}
        for group, subtype in locations:
            target_dir = output / group / subtype if subtype else output / group
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / bill_no).symlink_to(
                os.path.relpath(bill_dir, target_dir), target_is_directory=True)
            counts[f"{group}/{subtype}" if subtype else group] += 1
    (output / "manifest.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in results), encoding="utf-8")
    summary = {"source": str(source), "total": len(results),
               "candidate_bills": sum(row["status"] == "candidate" for row in results),
               "out_of_scope_bills": sum(row["status"] == "out_of_scope" for row in results),
               "review_required_bills": sum(row["status"] == "review_required" for row in results),
               "links_by_subtype": dict(sorted(counts.items())),
               "holdout_excluded": True, "existing_seven_categories_unchanged": True,
               "classification_status": "unreviewed_candidate"}
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.source / OUTPUT_NAME
    print(json.dumps(build(args.source, output), ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
