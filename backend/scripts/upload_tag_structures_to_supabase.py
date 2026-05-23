"""upload_tag_structures_to_supabase.py

extract_tag_structures.py 가 생성한 JSONL 파일들을 Supabase TAG 테이블에 업로드한다.

업로드 순서:
  1. bill_cost_triggers
  2. non_attachment_reason_classifications
  3. cost_estimate_structures → items → variables / amounts  (ID 매핑 필요)

이미 같은 bill_id 데이터가 있으면 삭제 후 재삽입(idempotent).

사용법:
    python -m backend.scripts.upload_tag_structures_to_supabase \
        --seed-dir backend/generated/assembly_rag_seed
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import GENERATED_DIR, get_env

DEFAULT_SEED_DIR = GENERATED_DIR / "assembly_rag_seed"

EMBED_MODEL    = get_env("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
AZURE_API_VER  = "2024-02-01"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TAG 구조화 데이터를 Supabase에 업로드한다.")
    parser.add_argument("--seed-dir", type=Path, default=DEFAULT_SEED_DIR)
    parser.add_argument("--skip-embedding", action="store_true",
                        help="article_embedding 생성 건너뜀")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Supabase에 이미 있는 bill_id는 건너뜀 (누락분만 추가)")
    parser.add_argument("--skip-non-attachment", action="store_true",
                        help="non_attachment_reason_classifications 업로드 건너뜀")
    return parser.parse_args()


def get_azure_config() -> tuple[str, str]:
    key = get_env("AZURE_OPENAI_API_KEY")
    endpoint = get_env("AZURE_OPENAI_ENDPOINT").rstrip("/")
    if not (key and endpoint):
        raise SystemExit("AZURE_OPENAI_API_KEY / AZURE_OPENAI_ENDPOINT 가 .env에 필요합니다.")
    return key, endpoint


def embed_texts(texts: list[str], azure_key: str, azure_endpoint: str) -> list[list[float]]:
    """Azure OpenAI Embeddings — 비용유발 조문을 임베딩."""
    url = (f"{azure_endpoint}/openai/deployments/{EMBED_MODEL}"
           f"/embeddings?api-version={AZURE_API_VER}")
    body = json.dumps({"input": texts}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"api-key": azure_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Azure {exc.code}: {exc.read().decode()}") from exc
    return [it["embedding"] for it in sorted(data["data"], key=lambda x: x["index"])]


def get_supabase_config() -> tuple[str, str]:
    url = get_env("SUPABASE_URL").rstrip("/")
    if not url:
        ref = input("SUPABASE project ref: ").strip()
        url = f"https://{ref}.supabase.co"
    key = get_env("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        key = getpass.getpass("SUPABASE_SERVICE_ROLE_KEY: ").strip()
    if not key:
        raise SystemExit("SUPABASE_SERVICE_ROLE_KEY 가 필요합니다.")
    return url, key


def _call(
    url: str,
    key: str,
    method: str,
    payload: Any = None,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='ignore')}") from exc


def delete_by_bill_ids(base_url: str, key: str, table: str, bill_ids: list[str],
                       batch_size: int = 50) -> None:
    if not bill_ids:
        return
    for i in range(0, len(bill_ids), batch_size):
        batch = bill_ids[i:i + batch_size]
        ids_csv = ",".join(batch)
        url = f"{base_url}/rest/v1/{table}?bill_id=in.({urllib.parse.quote(ids_csv)})"
        _call(url, key, "DELETE")


def insert_batch(base_url: str, key: str, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    for i in range(0, len(rows), 100):
        _call(
            f"{base_url}/rest/v1/{table}",
            key, "POST", rows[i:i + 100],
            extra_headers={"Prefer": "return=minimal"},
        )


def insert_one(base_url: str, key: str, table: str, row: dict) -> dict | None:
    result = _call(
        f"{base_url}/rest/v1/{table}",
        key, "POST", [row],
        extra_headers={"Prefer": "return=representation"},
    )
    return result[0] if result else None


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        print(f"  [없음] {path.name}")
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def fetch_existing_bill_ids(base_url: str, key: str, table: str) -> set[str]:
    """Supabase 테이블에서 이미 존재하는 bill_id 목록 조회."""
    existing: set[str] = set()
    offset = 0
    limit = 1000
    while True:
        req = urllib.request.Request(
            f"{base_url}/rest/v1/{table}?select=bill_id&limit={limit}&offset={offset}",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                rows = json.loads(resp.read().decode("utf-8"))
        except Exception:
            break
        if not rows:
            break
        for r in rows:
            if r.get("bill_id"):
                existing.add(r["bill_id"])
        if len(rows) < limit:
            break
        offset += limit
    return existing


def main() -> None:
    args = parse_args()
    base_url, key = get_supabase_config()
    d = args.seed_dir

    triggers     = load_jsonl(d / "bill_cost_triggers.jsonl")
    non_attach   = load_jsonl(d / "non_attachment_classifications.jsonl")
    structures   = load_jsonl(d / "cost_estimate_structures.jsonl")
    items_all    = load_jsonl(d / "cost_estimate_items.jsonl")
    vars_all     = load_jsonl(d / "cost_estimate_variables.jsonl")
    amounts_all  = load_jsonl(d / "cost_estimate_amounts.jsonl")

    # ── skip-existing: Supabase에 없는 bill_id만 필터 ────────────────────────
    if args.skip_existing:
        existing_struct_ids = fetch_existing_bill_ids(base_url, key, "cost_estimate_structures")
        existing_na_ids     = fetch_existing_bill_ids(base_url, key, "non_attachment_reason_classifications")
        existing_trig_ids   = fetch_existing_bill_ids(base_url, key, "bill_cost_triggers")

        before = len(structures)
        structures = [s for s in structures if s.get("bill_id") not in existing_struct_ids]
        print(f"cost_estimate_structures: {before}건 중 {len(structures)}건 신규 (스킵 {before - len(structures)}건)")

        before = len(non_attach)
        non_attach = [n for n in non_attach if n.get("bill_id") not in existing_na_ids]
        print(f"non_attachment: {before}건 중 {len(non_attach)}건 신규 (스킵 {before - len(non_attach)}건)")

        before = len(triggers)
        triggers = [t for t in triggers if t.get("bill_id") not in existing_trig_ids]
        print(f"bill_cost_triggers: {before}건 중 {len(triggers)}건 신규 (스킵 {before - len(triggers)}건)")

        # items/variables/amounts는 신규 structures의 struct_id에 해당하는 것만
        new_struct_ids = {s["struct_id"] for s in structures}
        items_all   = [i for i in items_all   if i.get("struct_id") in new_struct_ids]
        vars_all    = [v for v in vars_all    if v.get("struct_id") in new_struct_ids]
        amounts_all = [a for a in amounts_all if a.get("struct_id") in new_struct_ids]
    else:
        # 기존 방식: 삭제 후 재삽입
        all_bill_ids = list({
            r["bill_id"] for r in triggers + non_attach + structures
            if r.get("bill_id")
        })
        for table in (
            "bill_cost_triggers",
            "non_attachment_reason_classifications",
            "cost_estimate_structures",
        ):
            delete_by_bill_ids(base_url, key, table, all_bill_ids)

    # ── 1. bill_cost_triggers (article_embedding 같이 생성) ──────────────────
    valid_triggers = [t for t in triggers if t.get("article_text", "").strip()]

    if valid_triggers and not args.skip_embedding:
        azure_key, azure_endpoint = get_azure_config()
        # 100건씩 배치 임베딩
        for i in range(0, len(valid_triggers), 100):
            batch = valid_triggers[i:i+100]
            texts = [t["article_text"][:8000] for t in batch]
            try:
                vectors = embed_texts(texts, azure_key, azure_endpoint)
                for t, v in zip(batch, vectors):
                    t["article_embedding"] = v
                print(f"  article_embedding 배치 {i//100+1} ({len(batch)}건) 완료")
            except Exception as exc:
                print(f"  [WARN] embedding 배치 실패 ({i}-{i+len(batch)}): {exc}",
                      file=sys.stderr)

    insert_batch(base_url, key, "bill_cost_triggers", valid_triggers)
    print(f"bill_cost_triggers        : {len(valid_triggers)}건")

    # ── 2. non_attachment_reason_classifications ──────────────────────────────
    if args.skip_non_attachment:
        print(f"non_attachment_classifications: 스킵")
    else:
        insert_batch(base_url, key, "non_attachment_reason_classifications", non_attach)
        print(f"non_attachment_classifications: {len(non_attach)}건")

    # ── 3. cost_estimate_structures ──────────────────────────────────────────
    struct_id_map: dict[str, int] = {}   # "BILL_ID::cost_estimate" → db bigint id
    for s in structures:
        row = {
            "bill_id":      s["bill_id"],
            "bill_no":      s.get("bill_no"),
            "bill_name":    s.get("bill_name"),
            "age":          s.get("age"),
            "committee":    s.get("committee"),
            "propose_date": s.get("propose_date") or None,
            "total_years":  s.get("total_years", 5),
            "status":       s.get("status", "structured_candidate"),
        }
        result = insert_one(base_url, key, "cost_estimate_structures", row)
        if result and result.get("id"):
            struct_id_map[s["struct_id"]] = result["id"]
    print(f"cost_estimate_structures  : {len(struct_id_map)}건")

    # ── 4. cost_estimate_items ────────────────────────────────────────────────
    item_id_map: dict[str, int] = {}    # "...::item1" → db bigint id
    for item in items_all:
        sid = struct_id_map.get(item.get("struct_id", ""))
        if sid is None:
            continue
        row = {
            "structure_id":  sid,
            "bill_id":       item["bill_id"],
            "item_category": item.get("item_category", ""),
            "item_name":     item.get("item_name", ""),
            "item_order":    item.get("item_order"),
            "trigger_ref":   item.get("trigger_ref", ""),
        }
        result = insert_one(base_url, key, "cost_estimate_items", row)
        if result and result.get("id"):
            item_id_map[item["item_id"]] = result["id"]
    print(f"cost_estimate_items       : {len(item_id_map)}건")

    # ── 5. cost_estimate_variables ────────────────────────────────────────────
    var_rows = []
    for v in vars_all:
        iid = item_id_map.get(v.get("item_id", ""))
        sid = struct_id_map.get(v.get("struct_id", ""))
        if iid is None or sid is None:
            continue
        raw_val = v.get("variable_value")
        try:
            num_val = float(raw_val) if raw_val is not None else None
        except (TypeError, ValueError):
            num_val = None
        var_rows.append({
            "item_id":            iid,
            "structure_id":       sid,
            "variable_type":      v.get("variable_type", "other"),
            "variable_name":      v.get("variable_name", ""),
            "variable_value":     num_val,
            "variable_unit":      v.get("variable_unit", ""),
            "needs_kosis_lookup": bool(v.get("needs_kosis_lookup", False)),
            "source_text":        v.get("source_text", ""),
        })
    insert_batch(base_url, key, "cost_estimate_variables", var_rows)
    print(f"cost_estimate_variables   : {len(var_rows)}건")

    # ── 6. cost_estimate_amounts ──────────────────────────────────────────────
    amt_rows = []
    for a in amounts_all:
        iid = item_id_map.get(a.get("item_id", ""))
        sid = struct_id_map.get(a.get("struct_id", ""))
        if iid is None or sid is None:
            continue
        raw_amt = a.get("amount_thousand")
        try:
            num_amt = int(float(raw_amt)) if raw_amt is not None else None
        except (TypeError, ValueError):
            num_amt = None
        amt_rows.append({
            "item_id":          iid,
            "structure_id":     sid,
            "year_label":       a.get("year_label", ""),
            "year_offset":      a.get("year_offset", 0),
            "amount_thousand":  num_amt,
            "formula_text":     a.get("formula_text", ""),
            "is_total":         bool(a.get("is_total", False)),
        })
    insert_batch(base_url, key, "cost_estimate_amounts", amt_rows)
    print(f"cost_estimate_amounts     : {len(amt_rows)}건")

    print("\n완료")


if __name__ == "__main__":
    main()
