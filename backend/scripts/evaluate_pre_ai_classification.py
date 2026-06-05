from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import fitz

from backend.analyzer_v2 import (
    _article_title,
    _detect_doc_type,
    _extract_pdf_text_from_bytes,
    _rule_cost_trigger,
    split_articles,
    split_articles_from_revision_table_pdf,
    strip_appendices,
)


BASE_DIR = Path("backend/generated/assembly_rag_seed_age21_50/files")


def _pdf_text(path: Path) -> str:
    with fitz.open(path) as doc:
        return "\n".join(page.get_text() for page in doc)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _article_ref(value: str) -> str | None:
    compact = _compact(value)
    match = re.search(r"제\d+조(?:의\d+)?", compact)
    if match:
        return match.group(0)
    match = re.search(r"별표\d*", compact)
    if match:
        return match.group(0) or "별표"
    return None


def _extract_official_refs(cost_text: str) -> list[str]:
    """비용추계서 앞부분의 재정수반/추계 표에서 언급되는 안 제N조/별표 후보."""
    head = cost_text[:9000]
    refs: list[str] = []
    for match in re.finditer(r"안\s*(제\s*\d+\s*조(?:의\s*\d+)?|(?:\[\s*)?별표\s*\d*\]?)", head):
        ref = _article_ref(match.group(1))
        if ref and ref not in refs:
            refs.append(ref)
    for match in re.finditer(r"\[\s*별표\s*\d+\s*\]", head):
        ref = _article_ref(match.group(0))
        if ref and ref not in refs:
            refs.append(ref)
    return refs


def _extract_official_categories(cost_text: str) -> list[str]:
    compact = _compact(cost_text[:7000])
    checks = [
        ("위원회/회의수당", r"(위원회|심의위원회|자문위원회|분과위원회).{0,80}(수당|회의|운영|설치)"),
        ("조직/인력", r"(사무처|지원단|담당관|소요인력|증원|인건비|직원)"),
        ("센터/전담기관", r"(지원센터|전담기관|센터).{0,80}(설치|운영|지정|위탁)"),
        ("직접지원/급여", r"(보육료|인건비를추가지급|선지급|지원금|보조금|수당|크레딧|기숙사지원)"),
        ("전산시스템", r"(전산|정보시스템|시스템|정보망|데이터베이스|플랫폼).{0,80}(구축|운영)"),
        ("시설/기관신설", r"(고등법원|고등검찰청|법원|검찰청|청사|시설비|공사비|기숙사)"),
        ("계획/조사/교육", r"(기본계획|종합계획|실태조사|보수교육|홍보|교육|연구용역)"),
        ("연금/보험", r"(국민연금|보험료|가입기간|크레딧)"),
    ]
    out: list[str] = []
    for name, pattern in checks:
        if re.search(pattern, compact):
            out.append(name)
    return out


def _pre_ai_articles(bill_pdf: Path) -> tuple[str, str, list[dict[str, Any]]]:
    pdf_bytes = bill_pdf.read_bytes()
    raw_text = _extract_pdf_text_from_bytes(pdf_bytes)
    text = strip_appendices(raw_text)
    doc_type = _detect_doc_type(raw_text)
    source = "body"
    articles: list[dict[str, Any]] = []
    if doc_type == "일부개정안":
        articles = split_articles_from_revision_table_pdf(pdf_bytes)
        if articles:
            source = "revision_table"
    if not articles:
        articles, doc_type = split_articles(text)
        source = "body_fallback"
    return doc_type, source, articles


def _classify_pre_ai(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for article in articles:
        text = str(article.get("text") or "")
        hit = _rule_cost_trigger(text)
        if not hit:
            continue
        no = str(article.get("no") or "")
        hits.append({
            "no": no,
            "ref": _article_ref(no),
            "title": _article_title(no) or no,
            "change_type": str(article.get("change_type") or ""),
            "trigger_type": hit["trigger_type"],
            "rule": hit["rule"],
            "candidate_strength": hit.get("candidate_strength"),
            "estimate_feasibility": hit.get("estimate_feasibility"),
            "non_attachment_risk": hit.get("non_attachment_risk"),
            "matched_text": hit.get("matched_text"),
        })
    return hits


def _compare_refs(official_refs: list[str], detected_hits: list[dict[str, Any]]) -> dict[str, Any]:
    detected_refs = []
    for hit in detected_hits:
        ref = hit.get("ref")
        if ref and ref not in detected_refs:
            detected_refs.append(ref)
    official_set = set(official_refs)
    detected_set = set(detected_refs)
    matched = [ref for ref in official_refs if ref in detected_set]
    missed = [ref for ref in official_refs if ref not in detected_set]
    extra = [ref for ref in detected_refs if ref not in official_set]
    recall = round(len(matched) / len(official_refs), 3) if official_refs else None
    precision = round(len(matched) / len(detected_refs), 3) if detected_refs else None
    return {
        "official_refs": official_refs,
        "detected_refs": detected_refs,
        "matched_refs": matched,
        "missed_official_refs": missed,
        "extra_detected_refs": extra,
        "recall_by_ref": recall,
        "precision_by_ref": precision,
    }


def _strength_summary(hits: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"strong": 0, "medium": 0, "weak": 0, "unknown": 0, "non_attachment_review": 0}
    refs = {"strong": [], "medium": [], "weak": []}
    for hit in hits:
        strength = str(hit.get("candidate_strength") or "unknown")
        if strength not in counts:
            strength = "unknown"
        counts[strength] += 1
        if hit.get("estimate_feasibility") == "non_attachment_review":
            counts["non_attachment_review"] += 1
        if strength in refs and hit.get("ref") and len(refs[strength]) < 12:
            refs[strength].append(hit["ref"])
    return {"counts": counts, "refs": refs}


def evaluate_one(bill_dir: Path) -> dict[str, Any]:
    bill_no = bill_dir.name
    bill_pdf = bill_dir / "bill_text_의안원문.pdf"
    cost_pdf = bill_dir / "cost_estimate_비용추계서.pdf"
    cost_text = _pdf_text(cost_pdf)
    doc_type, source, articles = _pre_ai_articles(bill_pdf)
    hits = _classify_pre_ai(articles)
    official_refs = _extract_official_refs(cost_text)
    return {
        "bill_no": bill_no,
        "doc_type": doc_type,
        "article_source": source,
        "article_count": len(articles),
        "official_categories": _extract_official_categories(cost_text),
        "detected_hits_count": len(hits),
        "candidate_strength_summary": _strength_summary(hits),
        "detected_hits": hits[:20],
        "ref_compare": _compare_refs(official_refs, hits),
    }


def main() -> None:
    rows = [evaluate_one(path.parent) for path in sorted(BASE_DIR.glob("*/cost_estimate_비용추계서.pdf"))]
    exact_or_good = 0
    weak = 0
    for row in rows:
        compare = row["ref_compare"]
        recall = compare["recall_by_ref"]
        precision = compare["precision_by_ref"]
        if recall is not None and recall >= 0.7 and (precision is None or precision >= 0.4):
            exact_or_good += 1
        else:
            weak += 1
    summary = {
        "source_dir": str(BASE_DIR),
        "count": len(rows),
        "rough_score": {
            "good_or_usable": exact_or_good,
            "weak_or_needs_review": weak,
            "note": "조문번호 기준의 거친 비교입니다. 정답지에 조문번호가 없거나 별표/시나리오형이면 수동 확인이 필요합니다.",
        },
        "rows": rows,
    }
    out = Path("/private/tmp/assembly_pre_ai_classification_eval.json")
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
