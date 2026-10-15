"""
把「報價 + 技術訊號 + 新聞情緒」組合成前端需要的資料。

效能重點：多檔股票時用 ThreadPool 平行抓資料（網路 I/O 才是瓶頸，不是 CPU）。
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import NewsDigest
from ..schemas import QuoteOut, SentimentOut, SignalOut
from .catalog import CATALOG
from .market_data import Quote, get_history, get_name, get_quote
from .signals import TradeSignal, compute_signal
from .symbols import symbol_info

log = logging.getLogger(__name__)

DIGEST_MAX_AGE = timedelta(hours=48)  # 太舊的新聞情緒不列入訊號計算


@dataclass
class SymbolAnalysis:
    symbol: str
    name: str
    quote: Quote | None
    signal: TradeSignal | None
    digest: NewsDigest | None


def display_name(symbol: str) -> str:
    if symbol in CATALOG:
        return CATALOG[symbol].name
    try:
        return get_name(symbol) or symbol_info(symbol).code
    except Exception:
        return symbol_info(symbol).code


def latest_digests(db: Session, symbols: list[str]) -> dict[str, NewsDigest]:
    """一次查詢拿到多檔股票「最新一筆」摘要（避免 N+1 查詢）。"""
    if not symbols:
        return {}
    latest_ids = (
        select(func.max(NewsDigest.id).label("id"))
        .where(NewsDigest.symbol.in_(symbols))
        .group_by(NewsDigest.symbol)
        .subquery()
    )
    rows = db.scalars(select(NewsDigest).join(latest_ids, NewsDigest.id == latest_ids.c.id))
    return {d.symbol: d for d in rows}


def news_score_of(digest: NewsDigest | None) -> float | None:
    if digest is None or datetime.now(timezone.utc) - digest.generated_at > DIGEST_MAX_AGE:
        return None
    return digest.sentiment_score


def signal_for(symbol: str, news_score: float | None) -> TradeSignal | None:
    try:
        return compute_signal(get_history(symbol, "1d"), news_score)
    except Exception as exc:
        log.warning("signal failed for %s: %s", symbol, exc)
        return None


def analyze_symbols(db: Session, symbols: list[str]) -> dict[str, SymbolAnalysis]:
    digests = latest_digests(db, symbols)  # DB 查詢在主執行緒做（Session 不是 thread-safe）

    def work(sym: str) -> SymbolAnalysis:
        try:
            quote = get_quote(sym)
        except Exception as exc:
            log.warning("quote failed for %s: %s", sym, exc)
            quote = None
        digest = digests.get(sym)
        return SymbolAnalysis(sym, display_name(sym), quote, signal_for(sym, news_score_of(digest)), digest)

    unique = list(dict.fromkeys(symbols))
    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(zip(unique, pool.map(work, unique)))


# ── 轉成 API 輸出格式 ─────────────────────────────────────────────
def quote_out(q: Quote | None) -> QuoteOut | None:
    if q is None:
        return None
    return QuoteOut(price=q.price, prev_close=q.prev_close, change=q.change, change_pct=q.change_pct,
                    currency=q.currency, as_of=q.as_of)


def signal_out(s: TradeSignal | None) -> SignalOut | None:
    return SignalOut(**s.to_dict()) if s else None


def sentiment_out(d: NewsDigest | None) -> SentimentOut | None:
    if d is None:
        return None
    return SentimentOut(label=d.sentiment_label, score=d.sentiment_score, summary=d.summary, impact=d.impact,
                        method=d.method, article_count=d.article_count, generated_at=d.generated_at)
