"""
個股資料 API。

GET /api/stocks/{symbol}/chart?interval=1d|1wk   K 線 + 技術指標 + 買賣標記 + 目前訊號
GET /api/stocks/{symbol}/news                    AI 新聞摘要 + 新聞列表
GET /api/recommendations                         藍籌股推薦區
"""

import logging
import math
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import NewsArticle, User, WatchlistItem
from ..schemas import ChartOut, NewsArticleOut, NewsOut, StockCardOut
from ..services.analysis import (
    analyze_symbols,
    display_name,
    news_score_of,
    quote_out,
    sentiment_out,
    signal_out,
)
from ..services.catalog import BLUE_CHIPS
from ..services.indicators import add_indicators
from ..services.market_data import get_history
from ..services.news_pipeline import latest_digest, refresh_symbol_news
from ..services.signals import InsufficientDataError, compute_signal, signal_markers
from ..services.symbols import InvalidSymbolError, normalize_symbol, symbol_info

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["stocks"])

INDICATOR_COLUMNS = ["ma5", "ma20", "ma60", "bb_upper", "bb_mid", "bb_lower", "rsi"]


def _symbol_or_422(raw: str) -> str:
    try:
        return normalize_symbol(raw)
    except InvalidSymbolError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None


def _series_points(s: pd.Series) -> list[dict]:
    # NaN（指標暖機期）不能放進 JSON，直接略過
    return [
        {"time": ts.strftime("%Y-%m-%d"), "value": round(float(v), 4)}
        for ts, v in s.items()
        if not math.isnan(v)
    ]


@router.get("/stocks/{symbol}/chart", response_model=ChartOut)
def read_chart(
    symbol: str,
    interval: Literal["1d", "1wk"] = Query("1d", description="1d = 日K，1wk = 週K"),
    db: Session = Depends(get_db),
):
    sym = _symbol_or_422(symbol)
    try:
        df = get_history(sym, interval)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"無法取得 {sym} 的 K 線資料：{exc}") from None

    ind = add_indicators(df)
    candles = [
        {
            "time": ts.strftime("%Y-%m-%d"),
            "open": round(float(r.open), 4), "high": round(float(r.high), 4),
            "low": round(float(r.low), 4), "close": round(float(r.close), 4),
            "volume": float(r.volume),
        }
        for ts, r in df.iterrows()
    ]
    try:
        signal = compute_signal(df, news_score_of(latest_digest(db, sym)))
    except InsufficientDataError:
        signal = None

    return ChartOut(
        symbol=sym,
        name=display_name(sym),
        interval=interval,
        candles=candles,
        indicators={col: _series_points(ind[col]) for col in INDICATOR_COLUMNS},
        markers=signal_markers(ind),
        signal=signal_out(signal),
    )


@router.get("/stocks/{symbol}/news", response_model=NewsOut)
def read_news(symbol: str, db: Session = Depends(get_db)):
    sym = _symbol_or_422(symbol)
    digest = latest_digest(db, sym)
    if digest is None:
        # 第一次查詢這檔股票（還沒被排程處理過）→ 現場抓一次
        try:
            refresh_symbol_news(db, sym, display_name(sym))
            digest = latest_digest(db, sym)
        except Exception as exc:
            db.rollback()
            log.warning("on-demand news refresh failed for %s: %s", sym, exc)

    articles = db.scalars(
        select(NewsArticle).where(NewsArticle.symbol == sym).order_by(NewsArticle.published_at.desc()).limit(12)
    )
    return NewsOut(
        symbol=sym,
        digest=sentiment_out(digest),
        articles=[
            NewsArticleOut(
                title=a.title, url=a.url, source=a.source, published_at=a.published_at,
                sentiment_label=a.sentiment_label, sentiment_score=a.sentiment_score, importance=a.importance,
            )
            for a in articles
        ],
    )


@router.get("/recommendations", response_model=list[StockCardOut])
def read_recommendations(
    market: Literal["ALL", "US", "TW"] = "ALL",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entries = [c for c in BLUE_CHIPS if market == "ALL" or symbol_info(c.symbol).market == market]
    starred = set(db.scalars(select(WatchlistItem.symbol).where(WatchlistItem.user_id == user.id)))
    analyses = analyze_symbols(db, [c.symbol for c in entries])
    return [
        StockCardOut(
            symbol=c.symbol, name=c.name, market=symbol_info(c.symbol).market, currency=symbol_info(c.symbol).currency,
            quote=quote_out(analyses[c.symbol].quote), signal=signal_out(analyses[c.symbol].signal),
            sentiment=sentiment_out(analyses[c.symbol].digest), starred=c.symbol in starred,
            sector=c.sector, description=c.description,
        )
        for c in entries
    ]
