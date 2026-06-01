from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .analyzer import analyze_document
from .analyzer_v2 import analyze_v2
from .form_renderer import render_form
from .config import GENERATED_DIR, GEMINI_API_KEY, HOST, PORT


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "EstimateAutomationHTTP/0.1"

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def _send_json(self, payload: dict[str, object], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, file_path: Path) -> None:
        if not file_path.exists() or not file_path.is_file():
            self._send_json({"error": "파일을 찾을 수 없습니다."}, status=404)
            return

        content_type = "text/html; charset=utf-8"
        if file_path.suffix == ".json":
            content_type = "application/json; charset=utf-8"
        elif file_path.suffix == ".docx":
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif file_path.suffix == ".hwpx":
            content_type = "application/haansofthwpx"

        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._send_json(
                {
                    "status": "ok",
                    "llmConfigured": bool(GEMINI_API_KEY),
                }
            )
            return

        if parsed.path.startswith("/generated/"):
            relative_name = parsed.path.removeprefix("/generated/")
            file_path = GENERATED_DIR / unquote(relative_name)
            self._send_file(file_path)
            return

        self._send_json({"error": "지원하지 않는 경로입니다."}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path not in ("/api/analyze", "/api/analyze_v2", "/api/render"):
            self._send_json({"error": "지원하지 않는 경로입니다."}, status=404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json({"error": "JSON 요청 본문이 필요합니다."}, status=400)
            return

        # ── /api/render: 양식 HTML 반환 ──
        if parsed.path == "/api/render":
            result = payload.get("result")
            fmt    = payload.get("format", "gyeonggi")
            if not isinstance(result, dict):
                self._send_json({"error": "result 객체가 필요합니다."}, status=400)
                return
            try:
                html = render_form(result, format=fmt)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
                return
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        filename = str(payload.get("filename") or "").strip()
        content = str(payload.get("content") or "").strip()
        if not filename or not content:
            self._send_json({"error": "filename과 content가 필요합니다."}, status=400)
            return

        if "," in content and content.startswith("data:"):
            content = content.split(",", 1)[1]

        try:
            if parsed.path == "/api/analyze_v2":
                form_type = str(payload.get("formType") or "gyeonggi").strip()
                if form_type not in ("gyeonggi", "assembly"):
                    form_type = "gyeonggi"
                result = analyze_v2(filename, content, form_type=form_type)
            else:
                result = analyze_document(filename, content)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
            return
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)
            return

        self._send_json(result, status=HTTPStatus.OK)


def run() -> None:
    server = ThreadingHTTPServer((HOST, PORT), ApiHandler)
    print(f"Backend listening on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run()
