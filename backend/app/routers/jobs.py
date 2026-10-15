"""
手動觸發排程的 API（給外部 Cron 服務呼叫）。

POST /api/jobs/refresh-news
Header: X-Cron-Secret: <與 .env 的 CRON_SECRET 相同>

安全設計：
- CRON_SECRET 沒設定 → 直接 404，等於這個 API 不存在。
- 用 secrets.compare_digest 比對密鑰：比較時間固定，防止「計時攻擊（timing attack）」
  一個字元一個字元地猜出密鑰。
"""

import secrets
from dataclasses import asdict

from fastapi import APIRouter, Header, HTTPException, status

from ..config import get_settings
from ..jobs.hourly_news import run_hourly_job
from ..schemas import JobReportOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("/refresh-news", response_model=JobReportOut)
def trigger_refresh(x_cron_secret: str | None = Header(default=None)):
    expected = get_settings().cron_secret
    if not expected:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    if not x_cron_secret or not secrets.compare_digest(x_cron_secret, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid cron secret")
    return JobReportOut(**asdict(run_hourly_job()))
