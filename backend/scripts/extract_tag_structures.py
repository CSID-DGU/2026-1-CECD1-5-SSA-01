"""extract_tag_structures.py

비용추계서/미첨부사유서/의안원문 텍스트를 Gemini로 분석하여
TAG 구조화 데이터를 JSONL 파일로 저장한다.

출력 파일:
  - bill_cost_triggers.jsonl
  - cost_estimate_structures.jsonl
  - cost_estimate_items.jsonl
  - cost_estimate_variables.jsonl
  - cost_estimate_amounts.jsonl
  - non_attachment_classifications.jsonl

사용법:
    python -m backend.scripts.extract_tag_structures \\
        --seed-dir backend/generated/assembly_rag_seed_age21_50
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import GENERATED_DIR, get_env

DEFAULT_SEED_DIR = GENERATED_DIR / "assembly_rag_seed"

# ── Gemini API ────────────────────────────────────────────────────────────────

GEMINI_API_KEY   = get_env("GEMINI_API_KEY")
GEMINI_MODEL     = get_env("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_BASE_URL  = "https://generativelanguage.googleapis.com/v1beta/models"


def call_gemini_json(prompt: str, *, api_key: str = GEMINI_API_KEY) -> dict | None:
    """Gemini API 호출 → JSON 파싱 결과 반환."""
    import urllib.error, urllib.request

    url = f"{GEMINI_BASE_URL}/{GEMINI_MODEL}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1,
        },
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req  = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        # Gemini가 list 반환 시 첫 dict 추출
        if isinstance(parsed, list):
            parsed = next((x for x in parsed if isinstance(x, dict)), None)
        if not isinstance(parsed, dict):
            return None
        return parsed
    except Exception as exc:  # noqa: BLE001
        print(f"    [Gemini 오류] {exc}", file=sys.stderr)
        return None


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"  → 저장: {path} ({len(rows)}건)")


def group_chunks_by_doc(chunks: list[dict]) -> dict[str, list[dict]]:
    """chunkId 기준으로 (billId, documentType) 별로 그룹핑."""
    groups: dict[str, list[dict]] = {}
    for c in chunks:
        key = f"{c.get('billId')}::{c.get('documentType')}"
        groups.setdefault(key, []).append(c)
    for v in groups.values():
        v.sort(key=lambda x: x.get("chunkIndex", 0))
    return groups


# ── 1. 비용 유발 조문 추출 (bill_text) ────────────────────────────────────────

COST_TRIGGER_PROMPT = """당신은 지방의회 법안 비용추계 전문가입니다.
다음 법안 조문에서 비용 유발 여부를 분석하세요.

[조문 텍스트]
{text}

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "article_no": "제N조 (또는 빈 문자열)",
  "cost_trigger": true 또는 false,
  "trigger_type": "직접지원|사업수행|조직설치|위탁대행|시설구축|대상확대|의무부과|없음",
  "obligation_strength": "mandatory|semi_mandatory|discretionary|aspirational",
  "budget_clause": true 또는 false,
  "cost_items": ["비용항목1", "비용항목2"],
  "confidence": 0.0~1.0 사이 숫자,
  "reason": "판단 이유 한 줄"
}}"""


def extract_cost_triggers(
    bill_id: str,
    bill_no: str | None,
    document_id_hint: str,
    chunks: list[dict],
    sleep: float,
) -> list[dict]:
    results = []
    for chunk in chunks:
        text = chunk.get("text", "").strip()
        if not text:
            continue
        prompt = COST_TRIGGER_PROMPT.format(text=text[:3000])
        parsed = call_gemini_json(prompt)
        time.sleep(sleep)
        if not parsed:
            continue
        results.append({
            "bill_id":             bill_id,
            "bill_no":             bill_no,
            "article_no":          parsed.get("article_no", ""),
            "article_title":       "",
            "article_text":        text[:2000],
            "cost_trigger":        bool(parsed.get("cost_trigger", False)),
            "trigger_type":        parsed.get("trigger_type", ""),
            "obligation_strength": parsed.get("obligation_strength", ""),
            "budget_clause":       bool(parsed.get("budget_clause", False)),
            "cost_items":          parsed.get("cost_items", []),
            "confidence":          float(parsed.get("confidence", 0.5)),
            "status":              "candidate",
            "reason":              parsed.get("reason", ""),
        })
    return results


# ── 2. 비용추계서 TAG 구조화 (cost_estimate) ──────────────────────────────────

TAG_EXTRACT_PROMPT = """당신은 지방의회 비용추계서를 분석하는 전문가입니다.
다음 비용추계서 텍스트에서 비용 산출 구조를 추출하세요.

중요: amount_thousand 필드는 반드시 천원(千원) 단위 정수입니다.
예) 1억원 = 100,000 / 10억원 = 1,000,000 / 100억원 = 10,000,000

[비용추계서 텍스트]
{text}

반드시 아래 JSON 형식으로만 응답하세요. 값이 없으면 null 또는 빈 배열을 사용하세요:
{{
  "total_years": 5,
  "cost_items": [
    {{
      "item_category": "인건비|운영비|사업비|지원금|위탁비",
      "item_name": "항목명",
      "trigger_ref": "근거 조문 (예: 제7조)",
      "variables": [
        {{
          "variable_type": "target_count|unit_cost|frequency|rate|period|other",
          "variable_name": "변수명 (예: 대상자 수)",
          "variable_value": 숫자 또는 null,
          "variable_unit": "단위 (예: 명, 원, %)",
          "needs_kosis_lookup": true 또는 false,
          "source_text": "원문 근거 텍스트"
        }}
      ],
      "amounts": [
        {{
          "year_label": "1차년도",
          "year_offset": 0,
          "amount_thousand": 천원단위정수 또는 null,
          "formula_text": "산식 텍스트",
          "is_total": false
        }}
      ]
    }}
  ]
}}"""


def extract_cost_estimate_structure(
    bill_id: str,
    bill_no: str | None,
    bill_name: str | None,
    age: int | None,
    committee: str | None,
    propose_date: str | None,
    full_text: str,
    sleep: float,
) -> dict | None:
    prompt = TAG_EXTRACT_PROMPT.format(text=full_text[:6000])
    parsed = call_gemini_json(prompt)
    time.sleep(sleep)
    if not parsed:
        return None
    return {
        "bill_id":      bill_id,
        "bill_no":      bill_no,
        "bill_name":    bill_name,
        "age":          age,
        "committee":    committee,
        "propose_date": propose_date,
        "total_years":  parsed.get("total_years", 5),
        "status":       "structured_candidate",
        "cost_items":   parsed.get("cost_items", []),
    }


# ── 3. 미첨부 사유서 분류 (non_attachment_reason) ────────────────────────────

NON_ATTACH_PROMPT = """당신은 지방의회 비용추계 미첨부 사유서를 분석하는 전문가입니다.
다음 미첨부 사유서 텍스트의 유형을 분류하세요.

유형 기준:
A: 비용을 수반하지 않는 경우 (정의 조항, 선언적 규정, 명칭 변경 등)
B: 추계가 기술적으로 곤란한 경우 (대상자 산정 불가, 시행 여부 불확실 등)
C: 기존 예산 범위 내에서 집행 가능한 경우 (기존 사업으로 흡수 가능)

[미첨부 사유서 텍스트]
{text}

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "reason_type": "A|B|C",
  "reason_text": "핵심 사유 한 줄 요약",
  "evidence_text": "원문에서 근거가 되는 핵심 문구",
  "confidence": 0.0~1.0 사이 숫자
}}"""


def classify_non_attachment(
    bill_id: str,
    bill_no: str | None,
    full_text: str,
    sleep: float,
) -> dict | None:
    prompt = NON_ATTACH_PROMPT.format(text=full_text[:4000])
    parsed = call_gemini_json(prompt)
    time.sleep(sleep)
    if not parsed:
        return None
    return {
        "bill_id":      bill_id,
        "bill_no":      bill_no,
        "reason_type":  parsed.get("reason_type", "A"),
        "reason_text":  parsed.get("reason_text", ""),
        "evidence_text":parsed.get("evidence_text", ""),
        "confidence":   float(parsed.get("confidence", 0.5)),
        "status":       "candidate",
    }


# ── 메인 ─────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TAG 구조화 + 분류 추출 스크립트")
    parser.add_argument("--seed-dir", type=Path, default=DEFAULT_SEED_DIR)
    parser.add_argument("--sleep",    type=float, default=1.0, help="API 호출 간격(초)")
    parser.add_argument("--limit",    type=int, default=0,   help="처리할 의안 수 (0=전체)")
    parser.add_argument("--bill-id",   type=str, help="특정 bill_id 1건만 처리")
    parser.add_argument("--only-with-cost-estimate", action="store_true",
                        help="추계서 있는 의안만 처리 (bills.jsonl 의 hasCostEstimate=true)")
    parser.add_argument("--skip-bill-text", action="store_true",
                        help="의안원문 처리 스킵 (bill_cost_triggers 안 채움)")
    parser.add_argument("--skip-existing", action="store_true",
                        help="이미 처리된 bill_id는 건너뜀 (JSONL에 있는 bill_id)")
    parser.add_argument("--parallel", type=int, default=1,
                        help="Gemini 의안 단위 병렬 처리 개수 (1=순차)")
    parser.add_argument("--skip-non-attachment", action="store_true",
                        help="미첨부사유서 분류 건너뜀 (Gemini API 비용 절감)")
    return parser.parse_args()


def process_one_bill(bill_id: str, bill_meta_map: dict, groups: dict,
                     skip_bill_text: bool, sleep: float,
                     skip_non_attachment: bool = False) -> dict:
    """의안 1건 처리. 결과를 dict로 반환 (병렬 처리용)."""
    meta = bill_meta_map.get(bill_id, {})
    bill_no      = meta.get("billNo")
    bill_name    = meta.get("billName")
    age          = meta.get("age")
    committee    = meta.get("committee")
    propose_date = meta.get("proposeDate")

    out = {
        "bill_id": bill_id, "bill_no": bill_no, "bill_name": bill_name,
        "cost_triggers": [], "cost_structures": [],
        "cost_items": [], "cost_variables": [], "cost_amounts": [],
        "non_attach_classes": [],
    }

    # ── 의안원문 분석 (옵션) ──
    if not skip_bill_text:
        bt_chunks = groups.get(f"{bill_id}::bill_text", [])
        if bt_chunks:
            out["cost_triggers"] = extract_cost_triggers(
                bill_id, bill_no, f"{bill_id}::bill_text", bt_chunks, sleep,
            )

    # ── 비용추계서 TAG 구조화 ──
    ce_chunks = groups.get(f"{bill_id}::cost_estimate", [])
    if ce_chunks:
        full_text = "\n\n".join(c.get("text", "") for c in ce_chunks)
        structure = extract_cost_estimate_structure(
            bill_id, bill_no, bill_name, age, committee, propose_date,
            full_text, sleep,
        )
        if structure:
            struct_id = f"{bill_id}::cost_estimate"
            out["cost_structures"].append({
                "struct_id":    struct_id,
                "bill_id":      structure["bill_id"],
                "bill_no":      structure["bill_no"],
                "bill_name":    structure["bill_name"],
                "age":          structure["age"],
                "committee":    structure["committee"],
                "propose_date": structure["propose_date"],
                "total_years":  structure["total_years"],
                "status":       structure["status"],
            })
            for item_idx, item in enumerate(structure.get("cost_items", []), 1):
                item_id = f"{struct_id}::item{item_idx}"
                out["cost_items"].append({
                    "item_id":       item_id,
                    "struct_id":     struct_id,
                    "bill_id":       bill_id,
                    "item_category": item.get("item_category", ""),
                    "item_name":     item.get("item_name", ""),
                    "item_order":    item_idx,
                    "trigger_ref":   item.get("trigger_ref", ""),
                })
                for var in item.get("variables", []):
                    out["cost_variables"].append({
                        "item_id":           item_id,
                        "struct_id":         struct_id,
                        "variable_type":     var.get("variable_type", "other"),
                        "variable_name":     var.get("variable_name", ""),
                        "variable_value":    var.get("variable_value"),
                        "variable_unit":     var.get("variable_unit", ""),
                        "needs_kosis_lookup":bool(var.get("needs_kosis_lookup", False)),
                        "source_text":       var.get("source_text", ""),
                    })
                for amt in item.get("amounts", []):
                    out["cost_amounts"].append({
                        "item_id":         item_id,
                        "struct_id":       struct_id,
                        "year_label":      amt.get("year_label", ""),
                        "year_offset":     amt.get("year_offset", 0),
                        "amount_thousand": amt.get("amount_thousand"),
                        "formula_text":    amt.get("formula_text", ""),
                        "is_total":        bool(amt.get("is_total", False)),
                    })

    # ── 미첨부사유서 분류 ──
    if not skip_non_attachment:
        na_chunks = groups.get(f"{bill_id}::non_attachment_reason", [])
        if na_chunks:
            full_text = "\n\n".join(c.get("text", "") for c in na_chunks)
            cls_result = classify_non_attachment(bill_id, bill_no, full_text, sleep)
            if cls_result:
                out["non_attach_classes"].append(cls_result)
    return out


def main() -> None:
    args = parse_args()

    if not GEMINI_API_KEY:
        raise SystemExit("GEMINI_API_KEY가 .env에 없습니다.")

    # 데이터 로드
    chunks_path = args.seed_dir / "chunks.jsonl"
    if not chunks_path.exists():
        chunks_path = args.seed_dir / "chunks_with_local_vectors.jsonl"
    chunks = load_jsonl(chunks_path)
    bill_text_path = args.seed_dir / "bill_text_for_tag.jsonl"
    if bill_text_path.exists() and not args.skip_bill_text:
        chunks = chunks + load_jsonl(bill_text_path)
    bills = load_jsonl(args.seed_dir / "bills.jsonl")

    bill_meta_map = {b["billId"]: b for b in bills}
    groups = group_chunks_by_doc(chunks)

    # 처리 대상 결정
    all_bill_ids = list({c.get("billId") for c in chunks if c.get("billId")})
    if args.bill_id:
        all_bill_ids = [args.bill_id] if args.bill_id in all_bill_ids else []
    elif args.only_with_cost_estimate:
        ce_ids = {b["billId"] for b in bills if b.get("hasCostEstimate")}
        all_bill_ids = [bid for bid in all_bill_ids if bid in ce_ids]

    # 이미 처리된 의안 스킵 (cost_structures 또는 non_attach 파일에 있으면)
    if args.skip_existing:
        existing: set[str] = set()
        for fn in ("cost_estimate_structures.jsonl",
                   "non_attachment_classifications.jsonl"):
            p = args.seed_dir / fn
            if p.exists():
                for row in load_jsonl(p):
                    existing.add(row.get("bill_id"))
        before = len(all_bill_ids)
        all_bill_ids = [bid for bid in all_bill_ids if bid not in existing]
        print(f"[skip-existing] {before - len(all_bill_ids)}건 스킵, 남은 {len(all_bill_ids)}건")

    if args.limit:
        all_bill_ids = all_bill_ids[:args.limit]

    total = len(all_bill_ids)
    print(f"처리 대상: {total}건  병렬: {args.parallel}  skip-bill-text: {args.skip_bill_text}")

    # 결과 수집기
    cost_triggers, cost_structures = [], []
    cost_items_all, cost_variables_all, cost_amounts_all = [], [], []
    non_attach_classes = []

    from concurrent.futures import ThreadPoolExecutor, as_completed
    completed = 0
    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        futures = {
            pool.submit(process_one_bill, bid, bill_meta_map, groups,
                        args.skip_bill_text, args.sleep,
                        args.skip_non_attachment): bid
            for bid in all_bill_ids
        }
        for fut in as_completed(futures):
            bid = futures[fut]
            completed += 1
            try:
                r = fut.result()
            except Exception as exc:
                print(f"  [{completed}/{total}] ERROR {bid}: {exc}", file=sys.stderr)
                continue
            cost_triggers.extend(r["cost_triggers"])
            cost_structures.extend(r["cost_structures"])
            cost_items_all.extend(r["cost_items"])
            cost_variables_all.extend(r["cost_variables"])
            cost_amounts_all.extend(r["cost_amounts"])
            non_attach_classes.extend(r["non_attach_classes"])
            tag_summary = []
            if r["cost_triggers"]: tag_summary.append(f"trig={len(r['cost_triggers'])}")
            if r["cost_structures"]: tag_summary.append(f"struct=O({len(r['cost_items'])}항목)")
            if r["non_attach_classes"]: tag_summary.append(
                f"NA={r['non_attach_classes'][0].get('reason_type','?')}"
            )
            tag = " ".join(tag_summary) or "empty"
            print(f"  [{completed}/{total}] {r['bill_no']} {tag}")

    # 결과 저장 - --skip-existing 모드면 기존 결과에 추가
    out = args.seed_dir
    if args.skip_existing:
        cost_triggers      = load_jsonl(out / "bill_cost_triggers.jsonl") + cost_triggers
        cost_structures    = load_jsonl(out / "cost_estimate_structures.jsonl") + cost_structures
        cost_items_all     = load_jsonl(out / "cost_estimate_items.jsonl") + cost_items_all
        cost_variables_all = load_jsonl(out / "cost_estimate_variables.jsonl") + cost_variables_all
        cost_amounts_all   = load_jsonl(out / "cost_estimate_amounts.jsonl") + cost_amounts_all
        non_attach_classes = load_jsonl(out / "non_attachment_classifications.jsonl") + non_attach_classes

    write_jsonl(out / "bill_cost_triggers.jsonl",             cost_triggers)
    write_jsonl(out / "cost_estimate_structures.jsonl",       cost_structures)
    write_jsonl(out / "cost_estimate_items.jsonl",            cost_items_all)
    write_jsonl(out / "cost_estimate_variables.jsonl",        cost_variables_all)
    write_jsonl(out / "cost_estimate_amounts.jsonl",          cost_amounts_all)
    write_jsonl(out / "non_attachment_classifications.jsonl", non_attach_classes)

    summary = {
        "cost_triggers":      len(cost_triggers),
        "cost_structures":    len(cost_structures),
        "cost_items":         len(cost_items_all),
        "cost_variables":     len(cost_variables_all),
        "cost_amounts":       len(cost_amounts_all),
        "non_attach_classes": len(non_attach_classes),
    }
    print("\n완료:", json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
