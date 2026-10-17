"""TAG 항목 이름을 미리 임베딩해 캐시(의미 검색용). 한 번만 실행."""
from __future__ import annotations

import json
from pathlib import Path

from backend.analyzer_v2 import embed_batch
from backend.estimator.tag_db import _load

OUT = Path("backend/generated/tag_item_embeddings.jsonl")


def main() -> None:
    data = _load()
    items = data["items"]
    ids = list(items.keys())
    print(f"TAG 항목 {len(ids)}개 임베딩 시작...")
    done = 0
    with open(OUT, "w", encoding="utf-8") as f:
        batch_size = 100
        for i in range(0, len(ids), batch_size):
            chunk = ids[i:i + batch_size]
            texts = [items[iid]["name"] + " " + items[iid].get("category", "") for iid in chunk]
            vecs = embed_batch(texts)
            for iid, vec in zip(chunk, vecs):
                if vec:
                    f.write(json.dumps({"item_id": iid, "emb": vec}) + "\n")
                    done += 1
            print(f"  {min(i + batch_size, len(ids))}/{len(ids)} (임베딩 성공 {done})")
    print(f"완료: {done}건 → {OUT}")


if __name__ == "__main__":
    main()
