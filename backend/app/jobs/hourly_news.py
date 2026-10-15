"""
⏰ 每小時排程：抓新聞 → 情緒分析 → AI 摘要 → 記錄訊號 → 記錄投資組合市值

三種執行方式
------------
1. 內建排程（預設）：啟動 API 時 APScheduler 會每小時整點自動執行（見 main.py）。
2. 手動執行一次（適合 crontab / 測試）：
       cd backend && python -m app.jobs.hourly_news
   Linux crontab 範例（每小時第 0 分）：
       0 * * * * cd /path/to/backend && .venv/bin/python -m app.jobs.hourly_news >> cron.log 2>&1
3. 外部服務呼叫 API（Vercel Cron / GitHub Actions / Cloud Scheduler）：
       curl -X POST https://your-api/api/jobs/refresh-news -H "X-Cron-Secret: <CRON_SECRET>"

設計重點
--------
- 每檔股票獨立 try/except：一檔失敗（例如 RSS 逾時）不會讓整個排程中斷。
- 新聞依 URL 雜湊去重複；新聞組合沒變就不重新呼叫 AI（省錢）。
- 兩次請求之間稍微停頓，對免費的新聞來源保持禮貌，避免被封鎖。
"""

import logging
import threading
import time
from dataclasses import asdict, dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal, init_db
from ..models import Holding, Portfolio, PortfolioSnapshot, SignalSnapshot, User, WatchlistItem
from ..services.analysis import display_name, news_score_of, signal_for
from ..services.catalog import BLUE_CHIPS
from ..services.market_data import get_fx_rate, get_quotes
from ..services.news_pipeline import latest_digest, refresh_symbol_news
from ..services.portfolio import aggregate, position_metrics

log = logging.getLogger(__name__)
POLITE_DELAY_SECONDS = 1.0

# 防止同一個 process 內同時跑兩次（例如排程觸發時剛好有人手動呼叫 API）
_job_lock = threading.Lock()


@dataclass
class JobReport:
    symbols: int = 0
    new_articles: int = 0
    digests_created: int = 0
    llm_calls: int = 0
    signals_recorded: int = 0
    portfolio_snapshots: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


def tracked_symbols(db: Session) -> list[str]:
    """需要更新的股票 = 所有人的持股 ∪ 所有人的 Watchlist ∪ 推薦區藍籌股。"""
    held = db.scalars(select(Holding.symbol).distinct())
    starred = db.scalars(select(WatchlistItem.symbol).distinct())
    return list(dict.fromkeys([*held, *starred, *(c.symbol for c in BLUE_CHIPS)]))


def _snapshot_portfolios(db: Session) -> int:
    count = 0
    for portfolio in db.scalars(select(Portfolio)):
        base = db.get(User, portfolio.user_id).base_currency
        holdings = list(portfolio.holdings)
        if not holdings:
            continue
        quotes = get_quotes([h.symbol for h in holdings])
        priced = []
        for h in holdings:
            q = quotes.get(h.symbol)
            if q is None:
                continue
            try:
                fx = get_fx_rate(h.currency, base)
            except Exception:
                continue
            priced.append((position_metrics(h.shares, h.avg_cost, q.price, q.prev_close), fx))
        t = aggregate(priced)
        db.add(PortfolioSnapshot(portfolio_id=portfolio.id, currency=base, market_value=t.market_value,
                                 cost_basis=t.cost_basis, unrealized_pnl=t.unrealized_pnl, day_pnl=t.day_pnl))
        count += 1
    db.commit()
    return count


def run_hourly_job() -> JobReport:
    if not _job_lock.acquire(blocking=False):
        log.info("hourly job already running; skip")
        return JobReport(errors=["job already running"])

    started = time.monotonic()
    report = JobReport()
    polite = get_settings().data_provider != "demo"
    try:
        with SessionLocal() as db:
            symbols = tracked_symbols(db)
            report.symbols = len(symbols)
            for i, sym in enumerate(symbols):
                # ① 新聞 + 情緒 + 摘要
                try:
                    r = refresh_symbol_news(db, sym, display_name(sym))
                    report.new_articles += r.new_articles
                    report.digests_created += int(r.digest_created)
                    report.llm_calls += int(r.llm_called)
                except Exception as exc:
                    db.rollback()
                    report.errors.append(f"news {sym}: {exc}")
                    log.exception("news refresh failed for %s", sym)

                # ② 記錄當下的買賣訊號（之後可拿來回測準確度）
                sig = signal_for(sym, news_score_of(latest_digest(db, sym)))
                if sig is not None:
                    db.add(SignalSnapshot(
                        symbol=sym, close=sig.price, rsi=sig.rsi, percent_b=sig.percent_b,
                        buy_zone_low=sig.buy_zone_low, buy_zone_high=sig.buy_zone_high,
                        take_profit=sig.take_profit, stop_loss=sig.stop_loss, trailing_stop=sig.trailing_stop,
                        action=sig.action, score=sig.score,
                    ))
                    db.commit()
                    report.signals_recorded += 1

                if polite and i < len(symbols) - 1:
                    time.sleep(POLITE_DELAY_SECONDS)

            # ③ 記錄投資組合市值（畫歷史走勢圖用）
            try:
                report.portfolio_snapshots = _snapshot_portfolios(db)
            except Exception as exc:
                db.rollback()
                report.errors.append(f"portfolio snapshot: {exc}")
                log.exception("portfolio snapshot failed")
    finally:
        report.duration_seconds = round(time.monotonic() - started, 2)
        _job_lock.release()

    log.info("hourly job done: %s", asdict(report))
    return report


if __name__ == "__main__":
    # python -m app.jobs.hourly_news → 手動執行一次
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_db()
    print(json.dumps(asdict(run_hourly_job()), ensure_ascii=False, indent=2))
