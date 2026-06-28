# Multi-stage build: frontend → backend
# 평가자가 `docker build` + `docker run` 한 번으로 백엔드 + 정적 프론트를 띄울 수 있게 함

# ── 1. Frontend build ────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund

COPY frontend ./
RUN npm run build

# ── 2. Backend runtime ───────────────────────────────────────────────────
FROM python:3.12-slim AS runtime
WORKDIR /app

# 시스템 패키지 (PyMuPDF 빌드용)
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY --from=frontend-builder /app/frontend/dist ./frontend_dist

ENV BACKEND_PORT=8010
ENV PYTHONUNBUFFERED=1
EXPOSE 8010

CMD ["python", "-m", "backend.server"]
