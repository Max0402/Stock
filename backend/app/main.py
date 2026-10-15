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

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db
from .jobs.hourly_news import run_hourly_job
from .routers import jobs, portfolio, stocks, watchlist
from .services.llm import llm_enabled

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db()
    log.info("data provider=%s, AI summary=%s", settings.data_provider, "Claude" if llm_enabled() else "rule-based")

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

app.include_router(portfolio.router)
app.include_router(watchlist.router)
app.include_router(stocks.router)
app.include_router(jobs.router)


@app.get("/api/health")
def health():
    s = get_settings()
    return {"status": "ok", "data_provider": s.data_provider, "ai_summary": "claude" if llm_enabled() else "rule"}
