# syntax=docker/dockerfile:1
# ════════════════════════════════════════════════════════════════════
# 一個映像檔 = 整個 App（前端網頁 + 後端 API），部署後只有一個網址。
#   docker build -t stock-tracker .
#   docker run -p 8000:8000 -e APP_PASSWORD=<密碼> -e DATABASE_URL=<資料庫> stock-tracker
# ════════════════════════════════════════════════════════════════════

# ── 第 1 階段：把 Next.js 前端 build 成純靜態檔（out/）──────────────
FROM node:22-slim AS frontend
WORKDIR /web
# 先只複製 package*.json：套件沒變時，Docker 會重用快取，不用每次重新 npm ci
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ENV NEXT_TELEMETRY_DISABLED=1 NEXT_OUTPUT=export
RUN npm run build

# ── 第 2 階段：Python 執行環境（最後的映像檔不含 Node，比較小）────────
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /web/out ./static

ENV STATIC_DIR=/app/static \
    PORT=8000

# 資安：不要用 root 執行。就算程式有漏洞被入侵，攻擊者也只有一般使用者權限
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
# 雲端平台會用 $PORT 告訴我們要聽哪個 port；--proxy-headers 讓 FastAPI 知道原始請求是 https
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
