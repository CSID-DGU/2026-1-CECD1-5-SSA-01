from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import GEMINI_MODEL
from backend.gemini_client import GeminiClient


def main() -> None:
    client = GeminiClient()
    result = client.healthcheck()
    print(
        json.dumps(
            {
                "status": result.get("status", "ok"),
                "requestedModel": GEMINI_MODEL,
                "response": result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
