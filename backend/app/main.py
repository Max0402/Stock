"""
FastAPI 主程式。

啟動：
    cd backend
    uvicorn app.main:app --reload --port 8000
API 文件（自動產生，可直接在網頁上測試）：
    http://localhost:8000/docs
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import init_db
from .jobs.hourly_news import run_hourly_job
from .routers import jobs, portfolio, stocks, watchlist
from .security import security_middleware
from .services.llm import llm_enabled

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db()
    log.info("data provider=%s, AI summary=%s", settings.data_provider, "Claude" if llm_enabled() else "rule-based")
    if not settings.app_password:
        log.warning("⚠️ 沒有設定 APP_PASSWORD：任何人都能開啟這個網站。部署到網路上前請務必設定！")
    elif len(settings.app_password) < 12:
        log.warning("⚠️ APP_PASSWORD 太短（< 12 字元），容易被暴力破解，建議換成隨機長密碼。")

    scheduler = None
    if settings.enable_scheduler:
        # BackgroundScheduler 在獨立執行緒執行，不會卡住 API 請求
        scheduler = BackgroundScheduler(timezone="UTC")
        scheduler.add_job(
            run_hourly_job,
            CronTrigger(minute=settings.news_refresh_minute),  # 每小時第 N 分鐘
            id="hourly_news",
            max_instances=1,                  # 上一次還沒跑完就不要重疊執行
            coalesce=True,                    # 伺服器睡著錯過好幾次 → 醒來只補跑一次
            next_run_time=datetime.now(timezone.utc),  # 啟動時先跑一次，讓畫面馬上有資料
        )
        scheduler.start()
        log.info("scheduler started: hourly at minute %d", settings.news_refresh_minute)
        # ⚠️ 如果用多個 worker（uvicorn --workers 4），每個 worker 都會各跑一份排程！
        #    多 worker 部署時請設 ENABLE_SCHEDULER=false，改用外部 cron 呼叫 /api/jobs/refresh-news。

    yield

    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Stock Tracker API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

# 密碼保護 + 安全性標頭（最後加入的 middleware 最先執行 → 未登入的請求在這裡就被擋下）
app.middleware("http")(security_middleware)

app.include_router(portfolio.router)
app.include_router(watchlist.router)
app.include_router(stocks.router)
app.include_router(jobs.router)


@app.get("/api/health")
def health():
    s = get_settings()
    sources = [n for n in s.news_sources if n != "finnhub" or s.finnhub_api_key]
    return {
        "status": "ok",
        "data_provider": s.data_provider,
        "news_sources": ["demo"] if s.data_provider == "demo" else sources,
        "news_trusted_only": s.news_trusted_only,
        "ai_summary": "claude" if llm_enabled() else "rule",
    }


# ── 部署模式：同一個服務也提供前端網頁 ───────────────────────────────
# 必須放在檔案「最後面」：掛在 "/" 的靜態檔會接住所有沒被上面 API 路由處理的網址。
_static = get_settings().static_dir
if _static and Path(_static).is_dir():
    app.mount("/", StaticFiles(directory=_static, html=True), name="frontend")
    log.info("serving frontend from %s", _static)
