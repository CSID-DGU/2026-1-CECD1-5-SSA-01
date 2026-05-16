"""Vercel Python serverless 진입점.

기존 backend/server.py 의 ApiHandler 를 그대로 사용한다.
Vercel은 'handler' 라는 이름의 BaseHTTPRequestHandler 클래스를 자동으로 찾는다.
"""
import os
import sys
from pathlib import Path

# 프로젝트 루트를 PYTHONPATH에 추가 (backend 모듈 import 가능하도록)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.server import ApiHandler as handler  # noqa: E402,F401
