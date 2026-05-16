from __future__ import annotations

import json
import urllib.error
import urllib.request

from .config import GEMINI_API_KEY, GEMINI_MODEL


class GeminiClient:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or GEMINI_API_KEY
        self.model = model or GEMINI_MODEL

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def generate_sections(self, prompt: str) -> dict[str, object]:
        if not self.enabled:
            raise RuntimeError("GEMINI_API_KEY is not configured.")

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt,
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Gemini HTTP {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Gemini request failed: {exc.reason}") from exc

        candidates = raw.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini response did not contain candidates.")

        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts).strip()
        if not text:
            raise RuntimeError("Gemini response text was empty.")

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Gemini response was not valid JSON: {text}") from exc

    def healthcheck(self) -> dict[str, object]:
        if not self.enabled:
            raise RuntimeError("GEMINI_API_KEY is not configured.")

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                'Return JSON only: {"status":"ok","model":"<model>"}'
                            )
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Gemini HTTP {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Gemini request failed: {exc.reason}") from exc

        candidates = raw.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini response did not contain candidates.")

        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {"status": "ok", "raw": text}
        data["requestedModel"] = self.model
        return data
