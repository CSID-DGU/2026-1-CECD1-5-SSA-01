"""OpenAI 임베딩 연결 테스트.

backend/.env의 OPENAI_API_KEY를 읽어서 text-embedding-3-small 호출만 검증한다.
키 값은 출력하지 않는다.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import get_env


def main() -> None:
    api_key = get_env("OPENAI_API_KEY")
    model = get_env("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    print(f"MODEL: {model}")
    print(f"KEY  : {'설정됨' if api_key else '없음'}")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY가 backend/.env에 필요합니다.")

    payload = {
        "model": model,
        "input": "비용 유발 조문을 자동으로 추출합니다.",
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="ignore")
        print(f"HTTP {exc.code}: {err}")
        raise SystemExit(1) from exc

    vector = data["data"][0]["embedding"]
    print(f"성공: 벡터 차원 {len(vector)}")


if __name__ == "__main__":
    main()
