"""Azure OpenAI 임베딩 연결 테스트 스크립트."""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import get_env

api_key  = get_env("AZURE_OPENAI_API_KEY")
endpoint = get_env("AZURE_OPENAI_ENDPOINT").rstrip("/")
model    = get_env("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

print(f"ENDPOINT : {endpoint}")
print(f"MODEL    : {model}")
print(f"KEY      : {'설정됨' if api_key else '❌ 없음'}")

url = f"{endpoint}/openai/deployments/{model}/embeddings?api-version=2024-02-01"
print(f"REQUEST  : POST {url}\n")

payload = {"input": ["비용 유발 조문을 자동으로 추출합니다."]}
body    = json.dumps(payload, ensure_ascii=False).encode("utf-8")
headers = {"api-key": api_key, "Content-Type": "application/json"}

req = urllib.request.Request(url, data=body, headers=headers, method="POST")
try:
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    vec = data["data"][0]["embedding"]
    print(f"✅ 성공! 벡터 차원: {len(vec)}")
    print(f"   첫 5개 값: {[round(v, 6) for v in vec[:5]]}")
except urllib.error.HTTPError as exc:
    body_err = exc.read().decode("utf-8", errors="ignore")
    print(f"❌ HTTP {exc.code}: {body_err}")
    sys.exit(1)
except Exception as exc:
    print(f"❌ 오류: {exc}")
    sys.exit(1)
